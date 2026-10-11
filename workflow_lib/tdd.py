import json

from harness.quality_gate import GateEvidence
from harness.spec_traceability import traceability
from workflow_lib.approvals import verify
from workflow_lib.contracts import result


def classify_red(value, expected):
    return (
        value.exit_code == 1
        and value.tests > 0
        and not value.errors
        and value.assertion_only
        and bool(value.failures)
        and bool(expected)
        and set(value.failures) == set(expected)
    )


def tests_snapshot(project):
    return {
        p: h
        for p, h in project.snapshot().items()
        if any(
            x in p.lower()
            for x in ("test", "spec.", "pytest", "conftest", "pom.xml", "package.json", "coverage")
        )
    }


def develop(
    project,
    agent,
    gates,
    *,
    allow_policy=False,
    cycle=0,
    state=None,
    feedback=None,
    max_green_attempts=None,
):
    if max_green_attempts is None:
        max_green_attempts = getattr(gates, "config", {}).get("max_green_attempts", 1)
    if not isinstance(max_green_attempts, int) or not 1 <= max_green_attempts <= 5:
        raise ValueError("GREEN attempt cap must be 1..5")
    verify(project, allow_policy=allow_policy)
    frozen_spec = project.spec_hash()
    frozen_approval = (project.spec_dir / "approval.json").read_bytes()
    prefix = f"tdd-{cycle}"
    if state:
        latest = next(
            (
                state.get(prefix + "-" + p)
                for p in ["refactor"]
                + ["green-retry-" + str(i) for i in reversed(range(1, max_green_attempts))]
                + ["green", "red"]
                if state.get(prefix + "-" + p)
            ),
            None,
        )
        if latest and latest["snapshot"] != project.snapshot():
            raise ValueError("source changed since TDD checkpoint; human recovery required")
    evidence = []

    def call(role, phase, attempt=0, failures=()):
        output = agent(
            role,
            json.dumps(
                {
                    "phase": phase,
                    "failed_gate_evidence_untrusted": list(failures),
                    "review_feedback_untrusted": feedback or [],
                    "project": str(project.root),
                    "feature": project.feature,
                    "instruction": "Preserve approved specs. Developer may not change tests. Return JSON status, expected_failures, traceability.",
                }
            ),
            f"dev-{cycle}-{phase}" + (f"-retry-{attempt}" if attempt else ""),
        )
        if (
            project.spec_hash() != frozen_spec
            or (project.spec_dir / "approval.json").read_bytes() != frozen_approval
        ):
            raise ValueError("BLOCKED_SPEC: agent modified approved specs")
        if output.get("status") != "PASS":
            raise ValueError("agent did not complete phase")
        return output

    def phase(role, name, protected=None, attempt=0, failures=()):
        key = name + (f"-retry-{attempt}" if attempt else "")

        def perform():
            baseline = tests_snapshot(project)
            if state:
                saved = state.get(prefix + "-" + key + "-baseline")
                if saved is None:
                    state.put(prefix + "-" + key + "-baseline", baseline)
                else:
                    baseline = saved
            output = call(role, name, attempt, failures)
            after = tests_snapshot(project)
            if name == "red":
                if any(after.get(p) != h for p, h in baseline.items()):
                    raise ValueError("RED agent weakened or removed existing tests/config")
            elif after != protected:
                raise ValueError("test files or test configuration changed during implementation")
            values = gates(key)
            if (
                project.spec_hash() != frozen_spec
                or (project.spec_dir / "approval.json").read_bytes() != frozen_approval
                or tests_snapshot(project) != after
            ):
                raise ValueError("quality command modified protected tests/specs")
            return {
                "output": output,
                "values": [v.json() for v in values],
                "snapshot": project.snapshot(),
                "tests": after,
            }

        data = state.once(prefix + "-" + key, perform, replay_safe=True) if state else perform()
        return data, [GateEvidence(**v) for v in data["values"]]

    red, values = phase("tdd-tester", "red")
    evidence.extend(v.json() for v in values)
    if len(values) != 1 or not classify_red(values[0], red["output"].get("expected_failures", [])):
        return result(
            "BLOCKED_ENVIRONMENT",
            evidence=evidence,
            next_action="Reproduce intended assertion failure",
        )
    protected = red["tests"]
    green = None
    for name in ("green", "refactor"):
        failures = []
        cap = max_green_attempts if name == "green" else 1
        for attempt in range(cap):
            green, values = phase("tdd-developer", name, protected, attempt, failures)
            recorded = [v.json() for v in values]
            evidence.extend(recorded)
            if values and all(v.passed for v in values) and values[0].tests > 0:
                break
            if any(v.exit_code in {124, 127} for v in values):
                return result(
                    "BLOCKED_ENVIRONMENT",
                    evidence=evidence,
                    next_action="Command/dependency/timeout failure",
                )
            failures = recorded
        else:
            return result(
                "CHANGES_REQUIRED",
                evidence=evidence,
                next_action="Bounded implementation attempts exhausted; preserve tests",
            )
    mapping = traceability(project, green["output"].get("traceability"))
    return result("PASS", evidence=evidence + [{"traceability": mapping}], spec_hash=frozen_spec)
