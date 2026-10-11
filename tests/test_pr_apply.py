import tempfile
import unittest
from pathlib import Path

from test_pr_review_threads import SHA, finding

from workflow_lib.github_pr import MockGitHub
from workflow_lib.issue_state import State
from workflow_lib.review import inline_review
from workflow_lib.review_threads import apply_threads


class ApplyTests(unittest.TestCase):
    def run_apply(self, api, fix=None, gates=True):
        with tempfile.TemporaryDirectory() as tmp:
            with State(Path(tmp) / "state.db", "run", {}) as state:

                def push(expected):
                    api.current["head_sha"] = "b" * 40
                    return "b" * 40

                return apply_threads(
                    api,
                    1,
                    state,
                    fix or (lambda t: {"status": "FIXED"}),
                    lambda: [
                        {"exit_code": 0 if gates else 1, "tests": 1, "failures": [], "errors": []}
                    ],
                    push,
                    required_checks=["test"],
                )

    def api(self):
        api = MockGitHub()
        inline_review(
            api, 1, {"status": "CHANGES_REQUIRED", "head_sha": SHA, "findings": [finding()]}
        )
        return api

    def test_fix_test_reply_resolve_open(self):
        api = self.api()
        output = self.run_apply(api)
        self.assertEqual(output["status"], "PASS")
        thread = output["threads"][0]
        self.assertEqual(thread["resolution_status"], "RESOLVED")
        self.assertTrue(thread["github_is_resolved"])
        self.assertEqual(api.current["state"], "OPEN")
        self.assertEqual(api.writes, ["create_review", "reply", "resolve"])

    def test_failure_and_dispute_never_resolve(self):
        for options in [
            {"gates": False},
            {"fix": lambda t: {"status": "DISPUTED"}},
            {"fix": lambda t: {"status": "BLOCKED_SPEC"}},
        ]:
            api = self.api()
            output = self.run_apply(api, **options)
            self.assertNotEqual(output["status"], "PASS")
            self.assertNotIn("resolve", api.writes)
            self.assertNotIn("reply", api.writes)

    def test_ci_delay_outdated_resolve_failure_permission(self):
        api = self.api()
        api.check_values = {"test": "pending"}
        self.assertEqual(self.run_apply(api)["status"], "BLOCKED_ENVIRONMENT")
        self.assertNotIn("resolve", api.writes)
        api = self.api()
        api.thread_values[0]["outdated"] = True
        self.assertEqual(self.run_apply(api)["status"], "HUMAN_REQUIRED")
        api = self.api()
        api.fail_resolve = True
        output = self.run_apply(api)
        self.assertEqual(output["status"], "BLOCKED_ENVIRONMENT")
        self.assertFalse(output["threads"][0]["github_is_resolved"])
        api = self.api()
        api.fail_permission = True
        with self.assertRaises(PermissionError):
            self.run_apply(api)
