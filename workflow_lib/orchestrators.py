"""Function composition, bounded control flow, approved spec protection."""

from workflow_lib.approvals import verify
from workflow_lib.contracts import result
from workflow_lib.dispatcher import review
from workflow_lib.tdd import develop


def development(
    project, agent, gates, *, max_cycles=3, allow_policy=False, developer=develop, state=None
):
    if not 1 <= max_cycles <= 10:
        raise ValueError("development retry cap must be 1..10")
    try:
        verify(project, allow_policy=allow_policy)
    except ValueError as error:
        return result("BLOCKED_SPEC", next_action=str(error))
    evidence = []
    feedback = []
    for cycle in range(max_cycles):
        if state:
            state.check()
            state.set_status("DEVELOPING")
        value = developer(
            project,
            agent,
            gates,
            allow_policy=allow_policy,
            cycle=cycle,
            state=state,
            feedback=feedback,
        )
        evidence.extend(value["evidence"])
        if value["status"] != "PASS":
            return result(value["status"], evidence=evidence, next_action=value["next_action"])
        verify(project, allow_policy=allow_policy)
        findings = review(project, agent, f"internal-review-{cycle}")
        evidence.append({"review": findings, "cycle": cycle})
        feedback = findings["findings"]
        if findings["status"] == "PASS":
            return result(
                "COMPLETED", evidence=evidence, next_action="Human may manage PR lifecycle"
            )
        if findings["status"] == "BLOCKED_SPEC":
            return result(
                "BLOCKED_SPEC", evidence=evidence, next_action="Human must update and approve specs"
            )
    return result("MAX_RETRIES", evidence=evidence, next_action="Human review required")


def issue(event, policy, api, state, hooks, *, dry_run=True):
    from workflow_lib.issue_intake import intake

    verdict = intake(event, policy)
    identity = {"run_id": state.key, "repo": event["repo"], "issue_number": event["issue_number"]}
    if verdict != "PASS":
        return result(verdict, **identity, next_action="Human must review origin/risk/scope")
    if dry_run:
        return result(
            "DRY_RUN", **identity, next_action="Explicit execution authorization required"
        )
    cached = state.get("terminal-result")
    if cached:
        pr = api.pr(cached["pr_number"])
        if pr["head_sha"] != cached["head_sha"]:
            return result(
                "HUMAN_REQUIRED",
                **identity,
                next_action="PR changed after completed run; new review required",
            )
        if any(not t["is_resolved"] for t in api.threads(cached["pr_number"])):
            return result(
                "HUMAN_REQUIRED", **identity, next_action="New unresolved threads after completion"
            )
        if not api.ci(cached["pr_number"], cached["head_sha"], policy.get("required_checks", [])):
            return result(
                "BLOCKED_ENVIRONMENT", **identity, next_action="Required CI no longer passing"
            )
        return cached
    evidence = []
    for name, status in [
        ("plan", "PLANNING"),
        ("spec_gate", "SPEC_GATE"),
        ("develop", "DEVELOPING"),
    ]:
        state.set_status(status)
        value = state.once(
            name, hooks[name], cache_if=lambda v: v.get("status") in {"PASS", "COMPLETED"}
        )
        evidence.append({"stage": name, "result": value})
        if value.get("status") not in {"PASS", "COMPLETED"}:
            return result(
                value.get("status", "FAILED"),
                **identity,
                evidence=evidence,
                next_action="Human must inspect failed stage",
            )
    state.set_status("PR_CREATING")
    created = state.once("create", hooks["create"], reconcile=hooks.get("reconcile_create"))
    number = created["pr_number"]
    identity["pr_number"] = number
    limit = int(policy.get("max_pr_cycles", 3))
    if not 1 <= limit <= 10:
        raise ValueError("PR cycle cap must be 1..10")
    for cycle in range(limit):
        state.check()
        state.set_status("PR_REVIEW")
        state.put("current-cycle", cycle)
        sha = api.pr(number)["head_sha"]
        value = state.once(
            f"pr-review-{cycle}-{sha}", hooks["review"], reconcile=hooks.get("reconcile_review")
        )
        if value.get("head_sha") != sha or api.pr(number)["head_sha"] != sha:
            return result(
                "HUMAN_REQUIRED",
                **identity,
                head_sha=sha,
                next_action="SHA race; review new commit",
            )
        evidence.append({"cycle": cycle, "review": value})
        threads = [t for t in api.threads(number) if not t["is_resolved"]]
        if value.get("status") == "PASS" and not value.get("findings") and not threads:
            if not api.ci(number, sha, policy.get("required_checks", [])):
                return result(
                    "BLOCKED_ENVIRONMENT",
                    **identity,
                    head_sha=sha,
                    next_action="Wait for required CI and resume",
                )
            if api.pr(number)["head_sha"] != sha:
                return result(
                    "HUMAN_REQUIRED", **identity, next_action="SHA race before completion"
                )
            final = result(
                "AWAITING_HUMAN_MERGE",
                **identity,
                head_sha=sha,
                evidence=evidence,
                next_action="Human reviews and merges open PR",
            )
            state.set_status(final["status"])
            return state.put("terminal-result", final)
        if value.get("status") not in {"PASS", "CHANGES_REQUIRED"}:
            return result(
                "HUMAN_REQUIRED",
                **identity,
                head_sha=sha,
                next_action="Review requires human decision",
            )
        if not threads:
            return result(
                "HUMAN_REQUIRED",
                **identity,
                head_sha=sha,
                next_action="Inline findings not confirmed",
            )
        state.set_status("PR_APPLY")
        applied = state.once(
            f"pr-apply-{cycle}-{sha}",
            hooks["apply"],
            reconcile=hooks.get("reconcile_apply"),
            cache_if=lambda v: v.get("status") == "PASS",
        )
        if applied.get("status") != "PASS":
            return result(
                applied.get("status", "FAILED"),
                **identity,
                head_sha=sha,
                next_action="Inspect unverified/disputed threads",
            )
    state.set_status("HUMAN_REQUIRED")
    return result(
        "HUMAN_REQUIRED", **identity, evidence=evidence, next_action="max_pr_cycles reached"
    )
