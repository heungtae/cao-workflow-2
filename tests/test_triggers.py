import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from workflow_lib.issue_state import State
from workflow_lib.jira import Jira
from workflow_lib.triggers import dispatch, pr_event, webhook_event


class TriggerTests(unittest.TestCase):
    def test_hmac_latest_pr_metadata_and_ignore_closed(self):
        payload = {
            "action": "synchronize",
            "repository": {"full_name": "owner/repo"},
            "pull_request": {
                "number": 1,
                "state": "open",
                "head": {"sha": "a" * 40, "repo": {"full_name": "owner/repo"}},
            },
        }
        raw = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(b"fixture", raw, hashlib.sha256).hexdigest()
        event = webhook_event(raw, signature, "fixture", "pull_request")
        self.assertEqual(event, pr_event("owner/repo", 1, "a" * 40))
        with self.assertRaises(PermissionError):
            webhook_event(raw, "sha256=bad", "fixture", "pull_request")
        payload["action"] = "closed"
        raw = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(b"fixture", raw, hashlib.sha256).hexdigest()
        self.assertIsNone(webhook_event(raw, signature, "fixture", "pull_request"))

    def test_dryrun_dedup_and_unauthorized_workflow(self):
        event = pr_event("owner/repo", 1, "a" * 40)
        policy = {"repositories": ["owner/repo"], "trigger_workflows": ["pr-review"]}
        binding = {
            "project": "/fixture/project",
            "feature": "001-feature",
            "policy": "/operator/policy.json",
            "config": "/operator/config.json",
        }
        calls = []

        def launch(request):
            calls.append(request)
            return {"run_id": request["run_id"], "status": "SUBMITTED"}

        with (
            tempfile.TemporaryDirectory() as tmp,
            State(Path(tmp) / "state.db", "trigger", {}) as state,
        ):
            self.assertEqual(dispatch(event, binding, policy, state, launch)["status"], "DRY_RUN")
            self.assertEqual(calls, [])
            first = dispatch(event, binding, policy, state, launch, execute=True)
            second = dispatch(event, binding, policy, state, launch, execute=True)
            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1)
            self.assertFalse(calls[0]["inputs"]["authorized"])
            bad = dict(event, workflow="arbitrary")
            with self.assertRaises(ValueError):
                dispatch(bad, binding, policy, state, launch, execute=True)

    def test_jira_fixed_read_adapter_and_planner_only(self):
        calls = []
        payload = {
            "key": "APP-1",
            "fields": {
                "project": {"key": "APP"},
                "summary": "Fix behavior",
                "description": {
                    "type": "doc",
                    "content": [{"type": "text", "text": "Acceptance behavior"}],
                },
            },
        }
        jira = Jira(
            "https://tenant.atlassian.net",
            {"jira_hosts": ["tenant.atlassian.net"], "jira_projects": ["APP"]},
            transport=lambda key: calls.append(key) or payload,
        )
        event = jira.event("APP-1")
        self.assertEqual(event["workflow"], "spec-planner")
        self.assertIn("Acceptance behavior", event["requirement"])
        self.assertEqual(calls, ["APP-1"])
        with self.assertRaises(ValueError):
            jira.event("../escape")
        with self.assertRaises(PermissionError):
            Jira("https://evil.example", {"jira_hosts": ["tenant.atlassian.net"]})
