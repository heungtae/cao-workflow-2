import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow_lib.approvals import approve, verify
from workflow_lib.contracts import validate_result
from workflow_lib.dispatcher import planner, review
from workflow_lib.project import Project


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".specify").mkdir()
        skills = self.root / ".agents/skills"
        for name in ["specify", "clarify", "plan", "tasks", "analyze"]:
            p = skills / ("speckit-" + name)
            p.mkdir(parents=True)
            (p / "SKILL.md").write_text("installed skill")
        self.project = Project(str(self.root), "001-test")

    def approve_specs(self):
        subprocess.run(["git", "-C", str(self.root), "add", "specs"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "--allow-empty",
                "-qm",
                "approve fixture specs",
            ],
            check=True,
        )
        return approve(self.project, "human", "manual")

    def test_path_escape_and_non_git(self):
        for name in ["../escape", "/tmp/x", "a/b", ".", ""]:
            with self.assertRaises(ValueError):
                Project(str(self.root), name)
        with self.assertRaises(ValueError):
            Project("/tmp", "001-test")

    def test_planner_only_plan_and_approval_hash(self):
        calls = []

        def agent(role, prompt, step_id):
            calls.append(role)
            self.project.spec_dir.mkdir(parents=True, exist_ok=True)
            for name in ["spec.md", "plan.md", "tasks.md"]:
                (self.project.spec_dir / name).write_text("REQ-001 verified requirement")
            return {"status": "PASS", "findings": [], "unresolved_risks": []}

        result = planner(self.project, "feature", agent)
        self.assertEqual(calls, ["spec-planner"] * 5 + ["spec-reviewer"])
        self.assertEqual(result["status"], "HUMAN_REQUIRED")
        self.approve_specs()
        verify(self.project)
        (self.project.spec_dir / "spec.md").write_text("changed")
        with self.assertRaises(ValueError):
            verify(self.project)

    def test_missing_specs_and_invalid_results(self):
        with self.assertRaises(ValueError):
            verify(self.project)
        with self.assertRaises(ValueError):
            validate_result({"status": "PASS"})

    def test_review_readonly_detects_mutation(self):
        def agent(*args):
            (self.root / "code.txt").write_text("unexpected write")
            return {"status": "PASS", "findings": []}

        with self.assertRaises(ValueError):
            review(self.project, agent, "review")

    def test_approval_requires_committed_specs(self):
        self.project.spec_dir.mkdir(parents=True)
        for name in ["spec.md", "plan.md", "tasks.md"]:
            (self.project.spec_dir / name).write_text("REQ-001")
        with self.assertRaises(ValueError):
            approve(self.project, "human", "manual")

    def test_malformed_review_findings_fail_closed(self):
        with self.assertRaises(ValueError):
            review(
                self.project, lambda *a: {"status": "CHANGES_REQUIRED", "findings": [{}]}, "review"
            )
