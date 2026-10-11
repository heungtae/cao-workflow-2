from test_workflows import ProjectTests

from workflow_lib.contracts import result
from workflow_lib.orchestrators import development


class DevelopmentTests(ProjectTests):
    def prepare(self):
        self.project.spec_dir.mkdir(parents=True)
        for name in ["spec.md", "plan.md", "tasks.md"]:
            (self.project.spec_dir / name).write_text("REQ-001 behavior")
        self.approve_specs()

    def test_loop_and_no_planner_or_pr(self):
        self.prepare()
        calls = []
        reviews = iter(
            [
                {
                    "status": "CHANGES_REQUIRED",
                    "findings": [
                        dict(
                            priority="high",
                            file="app.py",
                            line=1,
                            requirement_id="REQ-001",
                            expected_behavior="returns value",
                            suggested_fix="correct value",
                        )
                    ],
                },
                {"status": "PASS", "findings": []},
            ]
        )

        def agent(role, *args):
            calls.append(role)
            return next(reviews)

        def dev(*args, **kwargs):
            calls.append("developer")
            return result("PASS")

        output = development(self.project, agent, None, max_cycles=2, developer=dev)
        self.assertEqual(output["status"], "COMPLETED")
        self.assertEqual(calls, ["developer", "spec-reviewer", "developer", "spec-reviewer"])

    def test_blocked_spec_and_bounded_cycles(self):
        self.prepare()
        (self.project.spec_dir / "spec.md").write_text("changed")
        output = development(self.project, lambda *a: None, None)
        self.assertEqual(output["status"], "BLOCKED_SPEC")
        self.approve_specs()
        output = development(
            self.project,
            lambda *a: {
                "status": "CHANGES_REQUIRED",
                "findings": [
                    dict(
                        priority="high",
                        file="app.py",
                        line=1,
                        requirement_id="REQ-001",
                        expected_behavior="returns value",
                        suggested_fix="correct value",
                    )
                ],
            },
            None,
            max_cycles=2,
            developer=lambda *a, **kw: result("PASS"),
        )
        self.assertEqual(output["status"], "MAX_RETRIES")

    def test_green_failure_no_review(self):
        self.prepare()
        calls = []
        output = development(
            self.project,
            lambda *a: calls.append(a),
            None,
            developer=lambda *a, **kw: result("CHANGES_REQUIRED"),
        )
        self.assertEqual(output["status"], "CHANGES_REQUIRED")
        self.assertEqual(calls, [])
