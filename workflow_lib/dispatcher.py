"""Planning and read-only review; orchestration calls functions, never workflows."""

import json

from workflow_lib.contracts import result


def planner(project, requirement, agent):
    skills = project.skills()
    if not requirement.strip():
        raise ValueError("requirement required")
    risks = []
    before = project.snapshot()
    for name, path in skills.items():
        response = agent(
            "spec-planner",
            json.dumps(
                {
                    "task": name,
                    "installed_skill": path,
                    "project": str(project.root),
                    "feature": project.feature,
                    "requirement_untrusted": requirement,
                    "allowed_outputs": str(project.spec_dir),
                    "instruction": "Create Spec Kit artifacts only. Report unresolved_risks as a JSON array.",
                }
            ),
            f"plan-{name}",
        )
        if response.get("status") != "PASS" or not isinstance(
            response.get("unresolved_risks"), list
        ):
            return result("BLOCKED_SPEC", next_action="Review planner output")
        after = project.snapshot()
        changes = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
        if any(not p.startswith(f"specs/{project.feature}/") for p in changes):
            raise ValueError("planner wrote outside allowed spec artifacts")
        risks.extend(response["unresolved_risks"])
    project.specs()
    findings = review(project, agent, "plan-review")
    return result(
        "BLOCKED_SPEC" if risks or findings["status"] != "PASS" else "HUMAN_REQUIRED",
        next_action="Review and explicitly approve spec hash",
        artifacts=[str(project.spec_dir / name) for name in project.specs()],
        evidence=[{"unresolved_risks": risks, "review": findings}],
        spec_hash=project.spec_hash(),
    )


def review(project, agent, step_id):
    before = project.snapshot()
    output = agent(
        "spec-reviewer",
        json.dumps(
            {
                "project": str(project.root),
                "feature": project.feature,
                "task": "Read only: spec/test/code traceability and risks; JSON status/findings.",
            }
        ),
        step_id,
    )
    if before != project.snapshot():
        raise ValueError("read-only review modified project")
    if output.get("status") not in {"PASS", "CHANGES_REQUIRED", "BLOCKED_SPEC"} or not isinstance(
        output.get("findings"), list
    ):
        raise ValueError("invalid review result")
    if output["status"] == "PASS" and output["findings"]:
        raise ValueError("PASS with findings is invalid")
    for finding in output["findings"]:
        if not isinstance(finding, dict):
            raise ValueError("invalid review finding")
        for key in ("priority", "file", "requirement_id", "expected_behavior", "suggested_fix"):
            if not isinstance(finding.get(key), str) or not finding[key].strip():
                raise ValueError("incomplete review finding")
        path = finding["file"]
        if path.startswith("/") or ".." in path.split("/") or "\\" in path:
            raise ValueError("unsafe review finding path")
        if type(finding.get("line")) is not int or finding["line"] < 1:
            raise ValueError("invalid review finding line")
    return output
