import tempfile
import unittest
from pathlib import Path

from workflow_lib.issue_state import Busy, Cancelled, State
from workflow_lib.parallel import layers


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.db"

    def test_checkpoint_replay_and_inputs_frozen(self):
        with State(self.path, "owner/repo#1", {"input": "same"}) as state:
            count = []
            for _ in range(2):
                self.assertEqual(
                    state.once("write", lambda: count.append(1) or {"number": 1}), {"number": 1}
                )
            self.assertEqual(count, [1])
        with self.assertRaises(ValueError):
            with State(self.path, "owner/repo#1", {"input": "changed"}):
                pass

    def test_unknown_completion_requires_reconcile(self):
        with State(self.path, "key", {}) as state:
            with self.assertRaises(RuntimeError):
                state.once("write", lambda: (_ for _ in ()).throw(RuntimeError("lost response")))
            with self.assertRaises(ValueError):
                state.once("write", lambda: {"number": 2})
            self.assertEqual(
                state.once("write", lambda: None, reconcile=lambda: {"number": 1}), {"number": 1}
            )

    def test_cancel_and_exclusion(self):
        with State(self.path, "key", {}) as state:
            with self.assertRaises(Busy):
                with State(self.path, "key", {}):
                    pass
            State.cancel(self.path, "key")
            with self.assertRaises(Cancelled):
                state.check()

    def test_dag_and_ownership(self):
        tasks = [
            {"id": "a", "depends": [], "files": ["a.py"]},
            {"id": "b", "depends": [], "files": ["b.py"]},
            {"id": "c", "depends": ["a", "b"], "files": ["c.py"]},
        ]
        self.assertEqual(layers(tasks), [["a", "b"], ["c"]])
        tasks[1]["files"] = ["a.py"]
        with self.assertRaises(ValueError):
            layers(tasks)
        with self.assertRaises(ValueError):
            layers([{"id": "a", "depends": ["a"], "files": []}])

    def test_real_dag_worktrees_preserve_source(self):
        import subprocess
        from types import SimpleNamespace

        from workflow_lib.parallel import isolated_fanout

        source = Path(self.tmp.name) / "source"
        source.mkdir()
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        (source / "base.txt").write_text("base")
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=f@example.invalid",
                "commit",
                "-qm",
                "base",
            ],
            check=True,
        )
        tasks = [
            {"id": "a", "depends": [], "files": ["a.txt"]},
            {"id": "b", "depends": ["a"], "files": ["b.txt"]},
        ]

        def execute(task, path, step_id):
            if task["id"] == "b":
                self.assertEqual((path / "a.txt").read_text(), "a")
            (path / (task["id"] + ".txt")).write_text(task["id"])
            return {"status": "PASS"}

        result = isolated_fanout(
            SimpleNamespace(root=source), tasks, "run", execute, Path(self.tmp.name) / "worktrees"
        )
        self.assertEqual(set(result), {"a", "b"})
        self.assertFalse((source / "a.txt").exists())
