import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from workflow_lib.agent import Agent, BudgetExceeded
from workflow_lib.issue_state import State


class AgentTests(unittest.TestCase):
    def test_actual_shim_contract_budget_replay(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            State(Path(tmp) / "state.db", "run", {}) as state,
        ):
            config = Path(tmp) / "config.toml"
            config.write_text(
                '[profiles.cao-workflows-readonly]\nsandbox_mode="read-only"\napproval_policy="never"\n[profiles.cao-workflows-write]\nsandbox_mode="workspace-write"\napproval_policy="never"\n'
            )
            calls = []

            def shim(provider, role, prompt, **opts):
                calls.append((provider, role, opts))
                self.assertIn(opts["recovery"], ["idempotent", "manual"])
                self.assertIn("working_directory", opts)
                return SimpleNamespace(
                    status="idle", output='{"status":"PASS"}', replayed=True, terminal_id="dead"
                )

            agent = Agent(
                SimpleNamespace(root=Path(tmp)), state, max_steps=1, shim=shim, config_path=config
            )
            self.assertEqual(agent("spec-reviewer", "read", "review")["status"], "PASS")
            self.assertEqual(agent("spec-reviewer", "read", "review")["status"], "PASS")
            self.assertEqual(len(calls), 1)
            with self.assertRaises(BudgetExceeded):
                agent("spec-reviewer", "read", "other")
            with self.assertRaises(ValueError):
                agent("spec-reviewer", "changed", "review")

    def test_unobservable_currency_budget_blocks_before_agent_execution(self):
        with self.assertRaises(BudgetExceeded):
            Agent(SimpleNamespace(root=Path("/tmp")), None, max_cost=1)

    def test_secret_prompt_is_rejected_before_shim(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            State(Path(tmp) / "state.db", "run", {}) as state,
        ):
            agent = Agent(
                SimpleNamespace(root=Path(tmp)),
                state,
                shim=lambda *a, **kw: self.fail("secret reached shim"),
            )
            with self.assertRaisesRegex(ValueError, "secret"):
                agent("spec-reviewer", "ghp_abcdefghijklmnopqrstuvwxyz", "review")
