import tempfile
import unittest
from pathlib import Path

from test_issue_orchestrator import event, policy
from test_pr_review_threads import finding

from workflow_lib.contracts import result
from workflow_lib.github_pr import MockGitHub
from workflow_lib.issue_state import State
from workflow_lib.orchestrators import issue
from workflow_lib.review import inline_review
from workflow_lib.review_threads import apply_threads


class E2ETests(unittest.TestCase):
    def test_review_apply_rereview_and_no_external_merge(self):
        value = event()
        p = policy(value)
        api = MockGitHub()
        calls = []
        with (
            tempfile.TemporaryDirectory() as tmp,
            State(Path(tmp) / "state.db", "owner/repo#1", value) as state,
        ):

            def reviewed():
                calls.append("review")
                sha = api.pr(1)["head_sha"]
                reviewed = {
                    "status": "CHANGES_REQUIRED" if len(calls) == 1 else "PASS",
                    "head_sha": sha,
                    "findings": [finding(sha)] if len(calls) == 1 else [],
                }
                return inline_review(api, 1, reviewed)

            def push(expected):
                self.assertEqual(expected, api.current["head_sha"])
                api.current["head_sha"] = "b" * 40
                return api.current["head_sha"]

            hooks = {
                "plan": lambda: result("PASS"),
                "spec_gate": lambda: result("PASS"),
                "develop": lambda: result("COMPLETED"),
                "create": lambda: {"pr_number": 1},
                "review": reviewed,
                "apply": lambda: apply_threads(
                    api,
                    1,
                    state,
                    lambda t: {"status": "FIXED"},
                    lambda: [{"exit_code": 0, "tests": 1, "errors": [], "failures": []}],
                    push,
                    required_checks=["test"],
                ),
            }
            output = issue(value, p, api, state, hooks, dry_run=False)
            self.assertEqual(output["status"], "AWAITING_HUMAN_MERGE")
            self.assertEqual(calls, ["review", "review"])
            self.assertEqual(api.current["state"], "OPEN")
            self.assertEqual(api.writes, ["create_review", "reply", "resolve"])
            self.assertTrue(all(t["is_resolved"] for t in api.threads(1)))

    def test_apply_resume_after_ci_delay_without_duplicate_fix_push_reply(self):
        api = MockGitHub()
        inline_review(
            api,
            1,
            {
                "status": "CHANGES_REQUIRED",
                "head_sha": api.current["head_sha"],
                "findings": [finding()],
            },
        )
        api.check_values = {"test": "pending"}
        calls = []
        with (
            tempfile.TemporaryDirectory() as tmp,
            State(Path(tmp) / "state.db", "run", {}) as state,
        ):

            def fix(thread):
                calls.append("fix")
                return {"status": "FIXED"}

            def push(expected):
                calls.append("push")
                api.current["head_sha"] = "b" * 40
                return api.current["head_sha"]

            def gates():
                return [{"exit_code": 0, "tests": 1, "errors": [], "failures": []}]

            self.assertEqual(
                apply_threads(api, 1, state, fix, gates, push, required_checks=["test"])["status"],
                "BLOCKED_ENVIRONMENT",
            )
            api.check_values = {"test": "success"}
            self.assertEqual(
                apply_threads(api, 1, state, fix, gates, push, required_checks=["test"])["status"],
                "PASS",
            )
            self.assertEqual(
                apply_threads(api, 1, state, fix, gates, push, required_checks=["test"])["status"],
                "PASS",
            )
            self.assertEqual(calls, ["fix", "push"])
            self.assertEqual(api.writes.count("reply"), 1)
            self.assertEqual(api.writes.count("resolve"), 1)

    def test_sha_race_and_cycle_cap(self):
        value = event()
        p = policy(value)
        api = MockGitHub()
        with (
            tempfile.TemporaryDirectory() as tmp,
            State(Path(tmp) / "state.db", "owner/repo#1", value) as state,
        ):
            hooks = {
                "plan": lambda: result("PASS"),
                "spec_gate": lambda: result("PASS"),
                "develop": lambda: result("COMPLETED"),
                "create": lambda: {"pr_number": 1},
                "review": lambda: {"status": "PASS", "head_sha": "f" * 40, "findings": []},
            }
            output = issue(value, p, api, state, hooks, dry_run=False)
            self.assertEqual(output["status"], "HUMAN_REQUIRED")
            self.assertEqual(api.writes, [])

    def test_completed_issue_revalidates_ci_and_new_threads(self):
        value = event()
        p = policy(value)
        api = MockGitHub()
        with (
            tempfile.TemporaryDirectory() as tmp,
            State(Path(tmp) / "state.db", "owner/repo#1", value) as state,
        ):
            hooks = {
                "plan": lambda: result("PASS"),
                "spec_gate": lambda: result("PASS"),
                "develop": lambda: result("COMPLETED"),
                "create": lambda: {"pr_number": 1},
                "review": lambda: {
                    "status": "PASS",
                    "head_sha": api.current["head_sha"],
                    "findings": [],
                },
            }
            self.assertEqual(
                issue(value, p, api, state, hooks, dry_run=False)["status"], "AWAITING_HUMAN_MERGE"
            )
            api.check_values = {"test": "pending"}
            self.assertEqual(
                issue(value, p, api, state, hooks, dry_run=False)["status"], "BLOCKED_ENVIRONMENT"
            )
