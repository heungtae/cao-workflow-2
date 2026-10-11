"""Authenticated ingress and bounded, deduplicated CAO submissions."""

import hashlib
import hmac
import json
import re
import subprocess
from pathlib import Path

WORKFLOWS = {"pr-review", "spec-planner"}


def pr_event(repo, number, sha):
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
        or not isinstance(number, int)
        or number < 1
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
    ):
        raise ValueError("invalid PR trigger metadata")
    return {
        "source": "github-pr",
        "workflow": "pr-review",
        "repo": repo,
        "pr_number": number,
        "head_sha": sha,
    }


def webhook_event(raw, signature, secret, event_name):
    if len(raw) > 1024 * 1024 or not secret:
        raise PermissionError("webhook secret/size gate rejected")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(expected, signature):
        raise PermissionError("webhook signature rejected")
    if event_name != "pull_request":
        return None
    value = json.loads(raw)
    if value.get("action") not in {"opened", "reopened", "synchronize", "ready_for_review"}:
        return None
    pr = value["pull_request"]
    repo = value["repository"]["full_name"]
    if pr.get("state") != "open" or pr["head"]["repo"]["full_name"] != repo:
        raise ValueError("only open same-repository PRs are automated")
    return pr_event(repo, pr["number"], pr["head"]["sha"])


def dispatch(
    event,
    binding,
    policy,
    state,
    launch,
    *,
    execute=False,
    authorize_publication=False,
    reconcile=None,
):
    if event.get("workflow") not in WORKFLOWS or event["workflow"] not in policy.get(
        "trigger_workflows", []
    ):
        raise ValueError("trigger workflow not approved")
    if event["source"] == "github-pr":
        pr_event(event["repo"], event["pr_number"], event["head_sha"])
        if event["repo"] not in policy.get("repositories", []):
            raise PermissionError("trigger repository not approved")
    elif event["source"] == "jira":
        if event["workflow"] != "spec-planner" or event["jira_key"].split("-")[0] not in policy.get(
            "jira_projects", []
        ):
            raise PermissionError("Jira triggers can only plan approved projects")
    else:
        raise ValueError("unknown trigger source")
    for name in ("project", "config", "policy"):
        if not Path(binding[name]).is_absolute():
            raise ValueError("trusted binding paths must be absolute")
    inputs = {
        "project": binding["project"],
        "feature": binding["feature"],
        "config": binding["config"],
        "policy": binding["policy"],
        "dry_run": False,
        "authorized": False,
    }
    if event["source"] == "github-pr":
        inputs["pr_number"] = event["pr_number"]
        if authorize_publication:
            if not policy.get("allow_trigger_publication", False):
                raise PermissionError("trigger publication policy required")
            inputs["authorized"] = True
    else:
        inputs["requirement"] = event["requirement"]
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "event": event,
                "binding": binding,
                "policy": policy,
                "publication": authorize_publication,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    request = {
        "workflow": event["workflow"],
        "run_id": "trigger-" + fingerprint[:24],
        "inputs": inputs,
    }
    if not execute:
        return {"status": "DRY_RUN", "request": request}

    def perform():
        value = launch(request)
        if value.get("run_id") != request["run_id"] or value.get("status") != "SUBMITTED":
            raise ValueError("CAO submission identity not confirmed")
        return value

    return state.once(
        "submit-" + fingerprint,
        perform,
        reconcile=(lambda: reconcile(request)) if reconcile else None,
    )


class CaoLauncher:
    def __init__(self, binary):
        self.binary = binary

    def __call__(self, request):
        if request["workflow"] not in WORKFLOWS:
            raise ValueError("workflow not allowlisted")
        argv = [
            self.binary,
            "workflow",
            "run",
            request["workflow"],
            "--run-id",
            request["run_id"],
            "--detach",
            "--json",
        ]
        for key, value in sorted(request["inputs"].items()):
            if not re.fullmatch(r"[a-z_]+", key):
                raise ValueError("invalid workflow input")
            encoded = str(value).lower() if isinstance(value, bool) else str(value)
            argv.extend(["--input", key + "=" + encoded])
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        if proc.returncode:
            raise RuntimeError("CAO submit failed; reconcile stable run ID before retry")
        value = json.loads(proc.stdout)
        if value.get("run_id") != request["run_id"]:
            raise ValueError("CAO returned different run ID")
        return {"run_id": request["run_id"], "status": "SUBMITTED"}

    def reconcile(self, request):
        proc = subprocess.run(
            [self.binary, "workflow", "status", request["run_id"], "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode:
            return None
        value = json.loads(proc.stdout)
        return (
            {"run_id": request["run_id"], "status": "SUBMITTED"}
            if value.get("run_id") == request["run_id"]
            else None
        )
