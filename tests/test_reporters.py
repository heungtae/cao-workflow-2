import tempfile
import unittest

from harness.reporters import report
from workflow_lib.contracts import result


class ReporterTests(unittest.TestCase):
    def test_observed_metrics_and_unavailable_cost_are_distinct(self):
        value = result(
            "PASS",
            evidence=[{"argv": ["test"], "log": "log", "exit_code": 0, "duration_seconds": 1.5}],
        )
        with tempfile.TemporaryDirectory() as tmp:
            report(tmp, value)
        self.assertEqual(value["metrics"]["command_seconds"], 1.5)
        self.assertEqual(value["metrics"]["commands"], 1)
        self.assertIsNone(value["metrics"]["cost"])
        self.assertIsNone(value["metrics"]["human_interventions"])
