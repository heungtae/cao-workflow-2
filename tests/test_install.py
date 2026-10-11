import json
import tempfile
import unittest
from pathlib import Path

from workflow_lib.installation import install, uninstall


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.source = Path(self.tmp.name) / "source"
        (self.source / "workflows").mkdir(parents=True)
        (self.source / "profiles").mkdir()
        (self.source / "workflows/a.py").write_text("pass\n")
        (self.source / "profiles/a.md").write_text("profile")

    def test_install_reinstall_uninstall_preserves_user(self):
        install(self.source, self.home, check=lambda: None)
        user = self.home / "user.txt"
        user.write_text("mine")
        first = (self.home / "cao-workflows-manifest.json").read_bytes()
        install(self.source, self.home, check=lambda: None)
        self.assertEqual(first, (self.home / "cao-workflows-manifest.json").read_bytes())
        uninstall(self.home)
        self.assertEqual(user.read_text(), "mine")
        self.assertFalse((self.home / "workflows/a.py").exists())

    def test_collision_force_restore_and_modified_protection(self):
        dest = self.home / "workflows/a.py"
        dest.parent.mkdir(parents=True)
        dest.write_text("user")
        with self.assertRaises(ValueError):
            install(self.source, self.home, check=lambda: None)
        install(self.source, self.home, force=True, check=lambda: None)
        dest.write_text("modified")
        with self.assertRaises(ValueError):
            uninstall(self.home)
        uninstall(self.home, force=True)
        self.assertEqual(dest.read_text(), "user")

    def test_rollback_and_dry_run(self):
        def fail():
            raise RuntimeError("validation failed")

        with self.assertRaises(RuntimeError):
            install(self.source, self.home, check=fail)
        self.assertFalse((self.home / "workflows/a.py").exists())
        install(self.source, self.home, dry_run=True, check=lambda: None)
        self.assertFalse((self.home / "cao-workflows-manifest.json").exists())

    def test_symlink_escape_rejected(self):
        self.home.mkdir()
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (self.home / "workflows").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            install(self.source, self.home, check=lambda: None)

    def test_deployment_pins_runtime_and_preserves_old_bundle(self):
        (self.source / "workflow_lib").mkdir()
        (self.source / "workflow_lib/__init__.py").write_text("version=1\n")
        (self.source / "workflows/a.py").write_text("RUNTIME_HOME = None\nBUNDLE_DIGEST = None\n")
        install(self.source, self.home, check=lambda: None)
        first = json.loads((self.home / "cao-workflows-manifest.json").read_text())
        self.assertIn(str(self.home), (self.home / "workflows/a.py").read_text())
        bundle = [p for p in first["files"] if ".cao-workflows-bundles" in p]
        self.assertTrue(bundle)
        (self.source / "workflow_lib/__init__.py").write_text("version=2\n")
        install(self.source, self.home, check=lambda: None)
        self.assertTrue(all((self.home / p).exists() for p in bundle))

    def test_interrupted_install_journal_recovers_without_overwriting_user_edit(self):
        import base64
        import hashlib

        from workflow_lib.installation import recover

        dest = self.home / "workflows/a.py"
        dest.parent.mkdir(parents=True)
        dest.write_text("partial")
        journal = {
            "workflows/a.py": {
                "before": base64.b64encode(b"original").decode(),
                "after": hashlib.sha256(b"partial").hexdigest(),
            }
        }
        (self.home / ".cao-workflows-transaction.json").write_text(json.dumps(journal))
        recover(self.home)
        self.assertEqual(dest.read_text(), "original")
        self.assertFalse((self.home / ".cao-workflows-transaction.json").exists())
        (self.home / ".cao-workflows-transaction.json").write_text(json.dumps(journal))
        dest.write_text("user-edit")
        with self.assertRaises(ValueError):
            recover(self.home)
        self.assertEqual(dest.read_text(), "user-edit")
