import unittest

from test_workflows import ProjectTests

from harness.quality_gate import GateEvidence
from workflow_lib.tdd import classify_red, develop


def evidence(code=0, failures=(), errors=(), tests=1):
    return GateEvidence(
        ["pytest"], code, "log", tests, list(failures), list(errors), "junit.xml", True
    )


class RedTests(unittest.TestCase):
    def test_assertion_only_is_red(self):
        self.assertTrue(classify_red(evidence(1, ["test_req"]), ["test_req"]))
        for value in [
            evidence(0),
            evidence(2, ["test_req"]),
            evidence(1, errors=["syntax"]),
            evidence(1, ["other"]),
            evidence(1, tests=0),
            evidence(1),
        ]:
            self.assertFalse(classify_red(value, ["test_req"]))


class TDDTests(ProjectTests):
    def prepare(self):
        self.project.spec_dir.mkdir(parents=True)
        for name in ["spec.md", "plan.md", "tasks.md"]:
            (self.project.spec_dir / name).write_text("REQ-001 behavior")
        self.approve_specs()
        (self.root / "test_req.py").write_text("assert False")

    def test_red_green_refactor_order(self):
        self.prepare()
        calls = []

        def agent(role, prompt, step_id):
            calls.append(role)
            return {
                "status": "PASS",
                "expected_failures": ["test_req"],
                "traceability": [
                    {
                        "requirement_id": "REQ-001",
                        "tests": ["test_req.py"],
                        "implementation": ["impl.py"],
                    }
                ],
            }

        (self.root / "impl.py").write_text("implementation")
        stages = iter([evidence(1, ["test_req"]), evidence(), evidence()])
        result = develop(self.project, agent, lambda stage: [next(stages)])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(calls, ["tdd-tester", "tdd-developer", "tdd-developer"])

    def test_green_failure_stops_refactor(self):
        self.prepare()
        calls = []

        def agent(role, *args):
            calls.append(role)
            return {"status": "PASS", "expected_failures": ["test_req"], "traceability": []}

        stages = iter([evidence(1, ["test_req"]), evidence(1, ["test_req"])])
        result = develop(self.project, agent, lambda stage: [next(stages)])
        self.assertEqual(result["status"], "CHANGES_REQUIRED")
        self.assertEqual(len(calls), 2)

    def test_test_tampering_and_spec_change_blocked(self):
        for target in ["test_req.py", "specs/001-test/spec.md"]:
            with self.subTest(target=target):
                if not self.project.spec_dir.exists():
                    self.prepare()
                else:
                    (self.project.spec_dir / "spec.md").write_text("REQ-001 behavior")
                    self.approve_specs()

                def agent(role, *args, target=target):
                    if role == "tdd-developer":
                        (self.root / target).write_text("weakened")
                    return {"status": "PASS", "expected_failures": ["test_req"], "traceability": []}

                with self.assertRaises(ValueError):
                    develop(self.project, agent, lambda stage: [evidence(1, ["test_req"])])

    def test_completed_tdd_resumes_without_rerunning_red_or_agents(self):
        import tempfile
        from pathlib import Path

        from workflow_lib.issue_state import State

        self.prepare()
        (self.root / "impl.py").write_text("implementation")
        calls = []

        def agent(role, prompt, step_id):
            calls.append(step_id)
            return {
                "status": "PASS",
                "expected_failures": ["test_req"],
                "traceability": [
                    {
                        "requirement_id": "REQ-001",
                        "tests": ["test_req.py"],
                        "implementation": ["impl.py"],
                    }
                ],
            }

        stages = iter([evidence(1, ["test_req"]), evidence(), evidence()])
        with (
            tempfile.TemporaryDirectory() as tmp,
            State(Path(tmp) / "state.db", "dev", {}) as state,
        ):

            def runner(phase):
                return [next(stages)]

            self.assertEqual(develop(self.project, agent, runner, state=state)["status"], "PASS")
            self.assertEqual(develop(self.project, agent, runner, state=state)["status"], "PASS")
            self.assertEqual(len(calls), 3)

    def test_green_retry_is_bounded_and_preserves_tests(self):
        self.prepare()
        (self.root / "impl.py").write_text("implementation")
        calls = []

        def agent(role, prompt, step_id):
            calls.append(step_id)
            return {
                "status": "PASS",
                "expected_failures": ["test_req"],
                "traceability": [
                    {
                        "requirement_id": "REQ-001",
                        "tests": ["test_req.py"],
                        "implementation": ["impl.py"],
                    }
                ],
            }

        stages = iter(
            [evidence(1, ["test_req"]), evidence(1, ["test_req"]), evidence(), evidence()]
        )
        output = develop(self.project, agent, lambda phase: [next(stages)], max_green_attempts=2)
        self.assertEqual(output["status"], "PASS")
        self.assertEqual(
            calls, ["dev-0-red", "dev-0-green", "dev-0-green-retry-1", "dev-0-refactor"]
        )
