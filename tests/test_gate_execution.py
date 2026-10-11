import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness.quality_gate import QualityGate, junit_evidence, redact
from workflow_lib.project import Project


class GateExecutionTests(unittest.TestCase):
    def test_junit_assertion_infra_and_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "junit.xml"
            path.write_text(
                '<testsuite tests="1"><testcase name="expected"><failure type="AssertionError">assert 0 == 1</failure></testcase></testsuite>'
            )
            self.assertEqual(junit_evidence(path), (1, ["expected"], [], True))
            path.write_text(
                '<testsuite errors="1"><testcase name="broken"><error>ImportError</error></testcase></testsuite>'
            )
            self.assertFalse(junit_evidence(path)[1])
            self.assertTrue(junit_evidence(path)[2])
        self.assertNotIn("ghp_abcdef", redact("token=ghp_abcdef"))

    def test_real_isolated_command_and_no_network_or_credentials(self):
        if os.environ.get("CAO_TEST_ISOLATION") != "1":
            self.skipTest("run with CAO_TEST_ISOLATION=1 on namespace-enabled host")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "target"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "check.py").write_text("""import os, socket
from pathlib import Path
assert 'GH_TOKEN' not in os.environ
assert not Path.home().joinpath('.config/gh/hosts.yml').exists()
try:
    socket.create_connection(('1.1.1.1',443),timeout=0.1)
except OSError:
    pass
else:
    raise AssertionError('network escaped')
Path('result.xml').write_text('<testsuite tests="1"><testcase name="isolation"/></testsuite>')
""")
            project = Project(str(root), "001-fixture")
            gate = {"argv": ["/usr/bin/python3", "check.py"], "junit": "result.xml"}
            config = {
                "test": gate,
                "static": {"argv": ["/usr/bin/true"]},
                "coverage": {"argv": ["/usr/bin/true"]},
            }
            values = QualityGate(project, config, Path(tmp) / "evidence")("green")
            self.assertEqual([v.exit_code for v in values], [0, 0, 0])
            self.assertEqual(values[0].tests, 1)
