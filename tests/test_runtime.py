import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_lib.runtime import execute


class RuntimeTests(unittest.TestCase):
    def test_invalid_preflight_has_structured_failure_report(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"CAO_WORKFLOW_RUN_ID": "fixture-invalid"}),
        ):
            home = Path(tmp) / "home"
            value = execute(
                "spec-planner", {"project": tmp, "feature": "../escape"}, runtime_home=str(home)
            )
            self.assertEqual(value["status"], "FAILED")
            path = (
                home
                / "workflow-data"
                / hashlib.sha256(b"fixture-invalid").hexdigest()[:20]
                / "result.json"
            )
            self.assertEqual(json.loads(path.read_text())["status"], "FAILED")
