import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_lib.skill_installation import install_skills, uninstall_skills

ROOT = Path(__file__).resolve().parents[1]


class SkillInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "project space/.agents/skills"

    def test_install_reinstall_and_owned_uninstall(self):
        manifest = install_skills(ROOT, self.dest)
        other = self.dest / "other/SKILL.md"
        other.parent.mkdir()
        other.write_text("mine")
        self.assertEqual(manifest, install_skills(ROOT, self.dest))
        launcher = self.dest / "cao-dev/scripts/run.py"
        process = subprocess.run(
            [str(ROOT / ".venv/bin/python"), str(launcher), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        uninstall_skills(self.dest)
        self.assertEqual(other.read_text(), "mine")
        self.assertFalse(launcher.exists())
        self.assertFalse((self.dest / "cao-dev").exists())

    def test_existing_directory_collision_even_if_unmanaged_extra(self):
        extra = self.dest / "cao-dev/extra.txt"
        extra.parent.mkdir(parents=True)
        extra.write_text("user")
        with self.assertRaises(ValueError):
            install_skills(ROOT, self.dest)
        self.assertEqual(extra.read_text(), "user")

    def test_force_backup_restore_and_user_modification_protected(self):
        owned = self.dest / "cao-dev/SKILL.md"
        owned.parent.mkdir(parents=True)
        owned.write_text("original")
        install_skills(ROOT, self.dest, force=True)
        owned.write_text("user edit")
        with self.assertRaises(ValueError):
            uninstall_skills(self.dest)
        uninstall_skills(self.dest, force=True)
        self.assertEqual(owned.read_text(), "original")

    def test_force_reinstall_backs_up_latest_user_modified_owned_file(self):
        install_skills(ROOT, self.dest)
        path = self.dest / "cao-dev/SKILL.md"
        path.write_text("user customization")
        install_skills(ROOT, self.dest, force=True)
        uninstall_skills(self.dest)
        self.assertEqual(path.read_text(), "user customization")

    def test_dry_run_rollback_and_symlink_escape(self):
        install_skills(ROOT, self.dest, dry_run=True)
        self.assertFalse(self.dest.exists())
        with patch(
            "workflow_lib.skill_installation.validate_installed", side_effect=RuntimeError("bad")
        ):
            with self.assertRaises(RuntimeError):
                install_skills(ROOT, self.dest)
        self.assertFalse((self.dest / "cao-dev/SKILL.md").exists())
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        self.dest.mkdir(parents=True, exist_ok=True)
        (self.dest / "cao-dev").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            install_skills(ROOT, self.dest, force=True)

    def test_scripts_project_global_and_validation(self):
        project = Path(self.tmp.name) / "target spaces"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)

        def run(script, *args, env=None):
            return subprocess.run(
                [str(ROOT / "scripts" / script), *map(str, args)],
                env=env,
                capture_output=True,
                text=True,
            )

        import os

        env = {
            **os.environ,
            "HOME": str(Path(self.tmp.name) / "user"),
            "CAO_WORKFLOWS_PYTHON": str(ROOT / ".venv/bin/python"),
        }
        for scope in (("--project", project), ("--global",)):
            proc = run("install-codex-skills.sh", *scope, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(run("validate-codex-skills.sh", *scope, env=env).returncode, 0)
            self.assertEqual(run("uninstall-codex-skills.sh", *scope, env=env).returncode, 0)
        self.assertFalse((project / "AGENTS.md").exists())

    def test_corrupt_manifest_or_runtime_cannot_escape_or_execute(self):
        install_skills(ROOT, self.dest)
        manifest = self.dest / "cao-codex-skills-manifest.json"
        data = json.loads(manifest.read_text())
        data["files"]["../outside"] = {"sha256": "bad", "backup": None}
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            uninstall_skills(self.dest)

    def test_installed_launcher_blocks_runtime_and_hash_manifest_tampering(self):
        import hashlib

        manifest = install_skills(ROOT, self.dest)
        module = next(
            self.dest / name
            for name in manifest["files"]
            if name.endswith("workflow_lib/codex_skills.py")
        )
        module.write_text("raise RuntimeError('tampered ran')")
        runtime = module.parents[1]
        bundle = runtime / "bundle.json"
        hashes = json.loads(bundle.read_text())
        hashes["workflow_lib/codex_skills.py"] = hashlib.sha256(module.read_bytes()).hexdigest()
        bundle.write_text(json.dumps(hashes, sort_keys=True))
        proc = subprocess.run(
            [str(ROOT / ".venv/bin/python"), str(self.dest / "cao-dev/scripts/run.py"), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("runtime changed", proc.stderr)
        self.assertNotIn("tampered ran", proc.stderr)


if __name__ == "__main__":
    unittest.main()
