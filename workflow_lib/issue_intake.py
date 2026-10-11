"""Event provenance is tied to operator-owned receipts, never labels alone."""

import fnmatch
import hashlib
import json
import re
from pathlib import Path

from workflow_lib.contracts import validate

SENSITIVE = re.compile(
    r"(?i)(auth|secret|token|credential|infra|deploy|production|payment|billing|protected|\.github|\.git/|policy|approval|\.env|id_rsa|\.pem)"
)


def event_digest(event):
    return hashlib.sha256(
        json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def intake(event, policy):
    validate(event, "issue-event.schema.json")
    origin = policy.get("origins", {}).get(event["origin_id"], {})
    if (
        event["repo"] not in policy.get("repositories", [])
        or event["author"] not in policy.get("trusted_authors", [])
        or origin.get("event_id") != event["event_id"]
        or origin.get("digest") != event_digest(event)
        or not policy.get("auto_low_risk", False)
        or event["risk"] != "low"
        or not event["files"]
    ):
        return "HUMAN_REQUIRED"
    if SENSITIVE.search(event["body"]):
        return "HUMAN_REQUIRED"
    for name in event["files"]:
        if Path(name).is_absolute() or ".." in Path(name).parts or SENSITIVE.search(name):
            return "HUMAN_REQUIRED"
        if not any(
            fnmatch.fnmatchcase(name, pattern) for pattern in policy.get("allowed_files", [])
        ):
            return "HUMAN_REQUIRED"
    return "PASS"


def verify_remote_issue(event, api):
    actual = api.call("issue", {"number": event["issue_number"]})
    if (
        actual.get("pull_request")
        or actual.get("state") != "open"
        or actual.get("user", {}).get("login") != event["author"]
        or actual.get("body") != event["body"]
    ):
        raise ValueError("issue origin/content no longer matches receipt")
    return actual
