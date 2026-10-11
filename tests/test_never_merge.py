import unittest
from pathlib import Path

from workflow_lib.github_pr import GitHub
from workflow_lib.merge_guard import guard_argv, inspect_source


class NeverMergeTests(unittest.TestCase):
    def test_denied_commands_all_approval_modes(self):
        denied = [
            ["gh", "pr", "merge", "1"],
            ["git", "merge", "topic"],
            ["git", "push", "origin", "main"],
            ["git", "push", "origin", "HEAD:refs/heads/main"],
            ["git", "push", "--force", "origin", "cao/x"],
            ["curl", "https://api.github.com/repos/o/r/pulls/1/merge"],
        ]
        for argv in denied:
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                guard_argv(argv, branch="cao/x", base="main")
        self.assertEqual(
            guard_argv(
                ["git", "push", "origin", "HEAD:refs/heads/cao/x"], branch="cao/x", base="main"
            )[-1],
            "HEAD:refs/heads/cao/x",
        )

    def test_no_executable_merge_paths(self):
        self.assertEqual(inspect_source(Path(__file__).resolve().parents[1]), [])

    def test_adapter_never_grants_forbidden_operations(self):
        for authorized in [False, True]:
            api = GitHub(
                "owner/repo",
                dry_run=False,
                authorized=authorized,
                policy={
                    "repositories": ["owner/repo"],
                    "github_operations": ["merge", "close_issue", "auto_merge", "queue"],
                },
                transport=lambda *a: self.fail("forbidden network operation"),
            )
            for op in [
                "merge",
                "close_issue",
                "auto_merge",
                "queue",
                "mergePullRequest",
                "enablePullRequestAutoMerge",
            ]:
                with self.assertRaises(ValueError):
                    api.call(op, {})
            self.assertEqual(api.audit, [])

    def test_static_ast_split_argv_and_raw_adapter_are_blocked(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflows"
            path.mkdir()
            (path / "bad.py").write_text(
                "import subprocess\nsubprocess.run(['gh','pr','merge','1'])\n"
            )
            self.assertTrue(inspect_source(tmp))
        api = GitHub("owner/repo", dry_run=False, authorized=True)
        with self.assertRaises(ValueError):
            api._rest("PUT", "repos/owner/repo/pulls/1/merge")
        with self.assertRaises(ValueError):
            api._graphql(
                'mutation { mergePullRequest(input:{pullRequestId:"x"}){clientMutationId}}'
            )

    def test_shell_executable_scan(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scripts"
            path.mkdir()
            (path / "bad.sh").write_text("#!/bin/sh\ngh pr merge 1\n")
            self.assertTrue(inspect_source(tmp))
