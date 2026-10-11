import unittest

from workflow_lib.github_pr import GitHub, MockGitHub
from workflow_lib.review import inline_review

SHA = "a" * 40


def finding(sha=SHA, line=2):
    return dict(
        finding_id="F1",
        thread_id=None,
        comment_id=None,
        type="bug",
        priority="high",
        file="app.py",
        line=line,
        head_sha=sha,
        requirement_id="REQ-001",
        expected_behavior="returns value",
        suggested_fix="return correct value",
    )


class ReviewTests(unittest.TestCase):
    def test_inline_and_dedup(self):
        api = MockGitHub(head=SHA)
        value = {"status": "CHANGES_REQUIRED", "head_sha": SHA, "findings": [finding()]}
        inline_review(api, 1, value)
        inline_review(api, 1, value)
        self.assertEqual(len(api.threads(1)), 1)
        self.assertEqual(api.writes.count("create_review"), 1)

    def test_stale_sha_and_invalid_line(self):
        for f in [finding("b" * 40), finding(line=900)]:
            api = MockGitHub(head=SHA)
            with self.assertRaises(ValueError):
                inline_review(
                    api,
                    1,
                    {"status": "CHANGES_REQUIRED", "head_sha": f["head_sha"], "findings": [f]},
                )
            self.assertEqual(api.writes, [])

    def test_allowlist_and_dryrun(self):
        api = GitHub("owner/repo")
        for operation in ["merge", "auto_merge", "queue", "close_issue", "arbitrary"]:
            with self.assertRaises(ValueError):
                api.call(operation, {})
        with self.assertRaises(PermissionError):
            api.call("create_review", {"pr": 1})

    def test_deleted_line_can_receive_left_side_inline_comment(self):
        api = MockGitHub(head=SHA)
        api.changed_lines = [{"filename": "gone.py", "patch": "@@ -1,1 +0,0 @@\n-old"}]
        value = finding(line=1)
        value["file"] = "gone.py"
        value["side"] = "LEFT"
        output = inline_review(
            api, 1, {"status": "CHANGES_REQUIRED", "head_sha": SHA, "findings": [value]}
        )
        self.assertEqual(output["findings"][0]["thread_id"], "T1")

    def test_paginated_reads_support_installed_gh_without_slurp(self):
        from subprocess import CompletedProcess
        from unittest.mock import patch

        with patch("workflow_lib.github_pr.subprocess.run") as run:
            run.return_value = CompletedProcess([], 0, '[{"number":1}]\n[{"number":2}]\n', "")
            api = GitHub("owner/repo")
            pages = api.call("list_prs", {"branch": "cao/issue-1"})
            self.assertNotIn("--slurp", run.call_args.args[0])
            self.assertEqual(pages, [[{"number": 1}], [{"number": 2}]])
