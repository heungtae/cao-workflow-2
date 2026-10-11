"""Thread state is confirmed remotely; CI/quality/SHA races block resolution."""

import hashlib
import json

from workflow_lib.contracts import result, validate


def open_threads(api, number):
    return [t for t in api.threads(number) if not t["is_resolved"]]


def apply_threads(api, number, state, fix, gates, push, *, required_checks, scope="apply"):

    pr = api.pr(number)
    context = state.get(scope + "-context")
    if context is None:
        context = {"initial": pr["head_sha"], "threads": open_threads(api, number)}
        state.put(scope + "-context", context)
    initial = context["initial"]
    outcomes = []
    threads = context["threads"]
    batch = (
        scope
        + "-"
        + hashlib.sha256(json.dumps([t["thread_id"] for t in threads]).encode()).hexdigest()[:16]
    )
    pushed = state.get(batch + "-push-" + initial)
    if pr["head_sha"] not in {initial, pushed}:
        return result("HUMAN_REQUIRED", pr_number=number, next_action="SHA race on resume")

    def entry(thread, status, **extra):
        value = {
            "thread_id": thread["thread_id"],
            "resolution_status": status,
            "fix_commit_sha": None,
            "test_evidence": [],
            "reply_comment_id": None,
            "github_is_resolved": False,
            **extra,
        }
        return validate(value, "pr-apply-result.schema.json")

    for thread in threads:
        state.check()
        if (
            thread["outdated"]
            or thread["head_sha"] != initial
            or not thread.get("line")
            or not thread["comments"]
        ):
            return result(
                "HUMAN_REQUIRED",
                pr_number=number,
                head_sha=initial,
                threads=outcomes + [entry(thread, "BLOCKED")],
                next_action="Outdated or incomplete thread needs re-review",
            )
        key = "thread-" + hashlib.sha256(thread["thread_id"].encode()).hexdigest()[:16]
        state.put(key + "-status", {"thread_id": thread["thread_id"], "status": "IN_PROGRESS"})
        value = state.once(
            key + "-fix-" + initial,
            lambda t=thread: fix(t),
            cache_if=lambda v: v.get("status") == "FIXED",
        )
        if value.get("status") in {"DISPUTED", "BLOCKED", "BLOCKED_SPEC", "REWORK_REQUIRED"}:
            status = "BLOCKED_SPEC" if value["status"] == "BLOCKED_SPEC" else "HUMAN_REQUIRED"
            return result(
                status,
                pr_number=number,
                threads=outcomes
                + [entry(thread, "DISPUTED" if value["status"] == "DISPUTED" else "BLOCKED")],
                next_action="Human or development orchestrator must address dispute/rework",
            )
        if value.get("status") != "FIXED":
            return result("FAILED", pr_number=number, threads=outcomes + [entry(thread, "BLOCKED")])
        outcomes.append(entry(thread, "FIXED"))
        state.put(key + "-status", outcomes[-1])
    if not threads:
        return result("PASS", pr_number=number, head_sha=initial, threads=[])
    evidence = state.once(
        batch + "-tests-" + initial,
        gates,
        cache_if=lambda v: bool(v) and all(e.get("exit_code") == 0 for e in v),
    )
    if (
        not evidence
        or any(v.get("exit_code") != 0 or v.get("errors") or v.get("failures") for v in evidence)
        or evidence[0].get("tests", 0) < 1
    ):
        return result(
            "CHANGES_REQUIRED",
            pr_number=number,
            threads=outcomes,
            next_action="Quality Gate failed",
        )
    if not pushed and api.pr(number)["head_sha"] != initial:
        return result(
            "HUMAN_REQUIRED", pr_number=number, threads=outcomes, next_action="SHA race before push"
        )
    sha = state.once(batch + "-push-" + initial, lambda: push(initial))
    if api.pr(number)["head_sha"] != sha:
        return result(
            "HUMAN_REQUIRED",
            pr_number=number,
            threads=outcomes,
            next_action="Pushed commit not latest PR HEAD",
        )
    if not api.ci(number, sha, required_checks):
        return result(
            "BLOCKED_ENVIRONMENT",
            pr_number=number,
            head_sha=sha,
            threads=outcomes,
            next_action="Required CI pending/failed",
        )
    for thread, value in zip(threads, outcomes, strict=True):
        state.check()
        key = "thread-" + hashlib.sha256(thread["thread_id"].encode()).hexdigest()[:16]
        body = (
            f"<!-- cao-fix:{thread['thread_id']}:{sha} -->\nFix commit: {sha}\nQuality Gate: "
            + json.dumps(evidence, sort_keys=True)
        )

        def reconcile_reply(thread=thread, body=body):
            actual = next(t for t in api.threads(number) if t["thread_id"] == thread["thread_id"])
            return next((c["databaseId"] for c in actual["comments"] if c["body"] == body), None)

        reply = state.once(
            key + "-reply-" + sha,
            lambda thread=thread, body=body: api.call(
                "reply", {"thread_id": thread["thread_id"], "body": body}
            ),
            reconcile=reconcile_reply,
        )
        value.update(fix_commit_sha=sha, test_evidence=evidence, reply_comment_id=reply)
        if api.pr(number)["head_sha"] != sha or not api.ci(number, sha, required_checks):
            return result(
                "HUMAN_REQUIRED",
                pr_number=number,
                head_sha=sha,
                threads=outcomes,
                next_action="SHA/CI changed before resolve",
            )
        actual = next(t for t in api.threads(number) if t["thread_id"] == thread["thread_id"])
        # A failed mutation is followed by an authoritative query, never assumed successful.
        if not actual["is_resolved"]:
            try:
                api.call("resolve", {"thread_id": thread["thread_id"]})
            except (PermissionError, ValueError):
                actual = next(
                    t for t in api.threads(number) if t["thread_id"] == thread["thread_id"]
                )
                value["github_is_resolved"] = actual["is_resolved"]
                if not actual["is_resolved"]:
                    return result(
                        "BLOCKED_ENVIRONMENT", pr_number=number, head_sha=sha, threads=outcomes
                    )
        actual = next(t for t in api.threads(number) if t["thread_id"] == thread["thread_id"])
        value["github_is_resolved"] = actual["is_resolved"]
        value["resolution_status"] = "RESOLVED" if actual["is_resolved"] else "FIXED"
        state.put(key + "-result-" + sha, value)
        if not actual["is_resolved"]:
            return result(
                "BLOCKED_ENVIRONMENT",
                pr_number=number,
                head_sha=sha,
                threads=outcomes,
                next_action="Resolve not confirmed remotely",
            )
    if api.pr(number)["head_sha"] != sha:
        return result(
            "HUMAN_REQUIRED",
            pr_number=number,
            head_sha=sha,
            threads=outcomes,
            next_action="SHA changed after resolve",
        )
    return result("PASS", pr_number=number, head_sha=sha, threads=outcomes, evidence=evidence)
