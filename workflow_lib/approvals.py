"""Human approval is bound to spec content; automatic approval is separately gated."""

import hashlib
import json
import subprocess

from workflow_lib.installation import atomic


def approve(project, actor, source, *, unresolved_risks=()):
    if source not in {"manual", "policy"} or not actor or unresolved_risks:
        raise ValueError("approval requires known actor/source and no unresolved risk")
    spec_commit = None
    if source == "manual":
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(project.root),
                "log",
                "-1",
                "--format=%H",
                "--",
                str(project.spec_dir),
            ],
            capture_output=True,
            text=True,
        )
        spec_commit = proc.stdout.strip()
        if (
            proc.returncode
            or not spec_commit
            or committed_hash(project, spec_commit) != project.spec_hash()
        ):
            raise ValueError("BLOCKED_SPEC: human must commit specs before approval")
    record = {
        "spec_commit": spec_commit,
        "actor": actor,
        "source": source,
        "spec_hash": project.spec_hash(),
        "unresolved_risks": [],
    }
    atomic(project.spec_dir / "approval.json", json.dumps(record, sort_keys=True).encode())
    return record


def verify(project, *, allow_policy=False):
    try:
        record = json.loads((project.spec_dir / "approval.json").read_text())
    except (OSError, ValueError) as error:
        raise ValueError("BLOCKED_SPEC: missing approval") from error
    if (
        record.get("spec_hash") != project.spec_hash()
        or not record.get("actor")
        or record.get("unresolved_risks") != []
        or record.get("source") not in ({"manual", "policy"} if allow_policy else {"manual"})
    ):
        raise ValueError("BLOCKED_SPEC: approval changed, missing or unsafe")
    if record.get("source") == "manual" and (
        not record.get("spec_commit")
        or committed_hash(project, record["spec_commit"]) != project.spec_hash()
    ):
        raise ValueError("BLOCKED_SPEC: approved commit no longer matches specs")
    return record


def committed_hash(project, commit):
    import re

    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("invalid approval commit")
    values = []
    for name in ("spec.md", "plan.md", "tasks.md"):
        relative = str((project.spec_dir / name).relative_to(project.root))
        proc = subprocess.run(
            ["git", "-C", str(project.root), "show", commit + ":" + relative],
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise ValueError("BLOCKED_SPEC: spec not present in approved commit")
        values.append(name + "\0" + proc.stdout)
    return hashlib.sha256("".join(values).encode()).hexdigest()
