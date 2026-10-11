import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness.quality_gate import QualityGate
from workflow_lib.approvals import approve
from workflow_lib.project import Project
from workflow_lib.tdd import develop

ROOT = Path(__file__).resolve().parents[1]


class RealTDDTests(unittest.TestCase):
    def test_actual_pytest_red_green_refactor_and_coverage_commands(self):
        if os.environ.get("CAO_TEST_ISOLATION") != "1":
            self.skipTest("namespace-enabled host required")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "target"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text(
                ".cao-runs/\n__pycache__/\n.pytest_cache/\n.ruff_cache/\n"
            )
            specs = root / "specs/001-real"
            specs.mkdir(parents=True)
            for name in ["spec.md", "plan.md", "tasks.md"]:
                (specs / name).write_text("REQ-001 value() must return 42")
            (root / "app.py").write_text("def value():\n    return 0\n")
            (root / "coverage_check.py").write_text("""import ast
import trace
from pathlib import Path
runner=trace.Trace(count=True,trace=False)
runner.run('import app; assert app.value()==42')
source=Path('app.py').resolve()
required={n.lineno for n in ast.walk(ast.parse(source.read_text())) if isinstance(n,ast.stmt)}
observed={line for (file,line),count in runner.results().counts.items() if Path(file).resolve()==source and count>0}
assert len(required & observed)/len(required)>=0.85
""")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=f@example.invalid",
                    "commit",
                    "-qm",
                    "approved fixture specs",
                ],
                check=True,
            )
            project = Project(str(root), "001-real")
            approve(project, "fixture human", "manual")
            config = {
                "test": {
                    "argv": [
                        str(ROOT / ".venv/bin/python"),
                        "-m",
                        "pytest",
                        "-p",
                        "no:libtmux",
                        "test_value.py",
                        "--junitxml=.cao-runs/junit.xml",
                    ],
                    "junit": ".cao-runs/junit.xml",
                },
                "static": {
                    "argv": [str(ROOT / ".venv/bin/ruff"), "check", "app.py", "test_value.py"]
                },
                "coverage": {"argv": [str(ROOT / ".venv/bin/python"), "coverage_check.py"]},
                "readonly_roots": [str(ROOT)],
            }
            phases = []

            def agent(role, prompt, step_id):
                phase = json.loads(prompt)["phase"]
                phases.append(phase)
                if phase == "red":
                    (root / "test_value.py").write_text(
                        "from app import value\n\n\ndef test_value():\n    assert value()==42\n"
                    )
                elif phase == "green":
                    (root / "app.py").write_text("def value():\n    return 42\n")
                elif phase == "refactor":
                    (root / "app.py").write_text(
                        "def answer():\n    return 42\n\n\ndef value():\n    return answer()\n"
                    )
                return {
                    "status": "PASS",
                    "expected_failures": ["test_value::test_value"],
                    "traceability": [
                        {
                            "requirement_id": "REQ-001",
                            "tests": ["test_value.py"],
                            "implementation": ["app.py"],
                        }
                    ],
                }

            output = develop(project, agent, QualityGate(project, config, Path(tmp) / "evidence"))
            logs = {str(p.name): p.read_text() for p in (Path(tmp) / "evidence").glob("*.log")}
            self.assertEqual(output["status"], "PASS", {**output, "logs": logs})
            self.assertEqual(phases, ["red", "green", "refactor"])
            self.assertEqual(
                [entry["exit_code"] for entry in output["evidence"] if "exit_code" in entry],
                [1, 0, 0, 0, 0, 0, 0],
            )
