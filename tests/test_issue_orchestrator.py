import tempfile
import unittest
from pathlib import Path

from workflow_lib.contracts import result
from workflow_lib.github_pr import MockGitHub
from workflow_lib.issue_intake import event_digest, intake
from workflow_lib.issue_state import State
from workflow_lib.orchestrators import issue


def event():
    return {
        "repo": "owner/repo",
        "issue_number": 1,
        "author": "cao-bot",
        "origin_id": "origin-1",
        "event_id": "event-1",
        "body": "Fix return value",
        "risk": "low",
        "files": ["app.py"],
    }


def policy(value):
    return {
        "repositories": ["owner/repo"],
        "trusted_authors": ["cao-bot"],
        "origins": {"origin-1": {"event_id": value["event_id"], "digest": event_digest(value)}},
        "auto_low_risk": True,
        "allowed_files": ["app.py"],
        "required_checks": ["test"],
        "max_pr_cycles": 2,
    }


class IntakeTests(unittest.TestCase):
    def test_origin_and_sensitive_scope(self):
        value = event()
        self.assertEqual(intake(value, policy(value)), "PASS")
        p = policy(value)
        value["body"] = "changed"
        self.assertEqual(intake(value, p), "HUMAN_REQUIRED")
        for filename in ["auth/token.py", "infra/deploy.yml", "../escape", "payments.py"]:
            value = event()
            value["files"] = [filename]
            p = policy(value)
            p["allowed_files"] = [filename]
            self.assertEqual(intake(value, p), "HUMAN_REQUIRED")

    def test_issue_stops_at_human_merge_and_resume(self):
        value = event()
        p = policy(value)
        api = MockGitHub()
        called = []

        def stage(name):
            def run():
                called.append(name)
                return result("COMPLETED" if name == "develop" else "PASS")

            return run

        with tempfile.TemporaryDirectory() as tmp:
            with State(Path(tmp) / "state.db", "owner/repo#1", value) as state:

                def review():
                    called.append("review")
                    return {"status": "PASS", "head_sha": api.current["head_sha"], "findings": []}

                hooks = {
                    "plan": stage("plan"),
                    "spec_gate": stage("gate"),
                    "develop": stage("develop"),
                    "create": lambda: {"pr_number": 1},
                    "review": review,
                    "apply": lambda: called.append("apply"),
                }
                output = issue(value, p, api, state, hooks, dry_run=False)
                self.assertEqual(output["status"], "AWAITING_HUMAN_MERGE")
                output = issue(value, p, api, state, hooks, dry_run=False)
                self.assertEqual(output["status"], "AWAITING_HUMAN_MERGE")
                self.assertEqual(called, ["plan", "gate", "develop", "review"])
                self.assertEqual(api.current["state"], "OPEN")
                self.assertEqual(api.writes, [])

    def test_dryrun_and_highrisk_no_steps(self):
        value = event()
        with tempfile.TemporaryDirectory() as tmp:
            with State(Path(tmp) / "state.db", "owner/repo#1", value) as state:
                self.assertEqual(
                    issue(value, policy(value), MockGitHub(), state, {}, dry_run=True)["status"],
                    "DRY_RUN",
                )
                value["risk"] = "high"
                self.assertEqual(
                    issue(value, policy(value), MockGitHub(), state, {}, dry_run=False)["status"],
                    "HUMAN_REQUIRED",
                )
