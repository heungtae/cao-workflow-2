import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_lib.approvals import approve
from workflow_lib.codex_skills import Cao, CaoError, SkillRunner, parse_request, validate_skills
from workflow_lib.contracts import result
from workflow_lib.project import Project

ROOT = Path(__file__).resolve().parents[1]


class FakeCao:
    def __init__(self):
        self.calls = []
        self.runs = {}
        self.output = None
        self.state = "RUNNING"
        self.ambiguous = False
        self.query_failures = 0

    def call(self, command, *args, read=True):
        self.calls.append((command, args, read))
        if command == "get":
            return {
                "name": args[0],
                "mode": "script",
                "inputs": {
                    k: {"type": t, "required": k in {"project", "feature"}}
                    for k, t in {
                        "project": "string",
                        "feature": "string",
                        "requirement": "string",
                        "config": "string",
                        "policy": "string",
                        "event": "string",
                        "pr_number": "int",
                        "dry_run": "bool",
                        "authorized": "bool",
                    }.items()
                },
            }
        if command == "run":
            run_id = args[args.index("--run-id") + 1]
            self.runs[run_id] = args[0]
            if self.ambiguous:
                raise CaoError("submission outcome unknown", transient=True)
            return {"run_id": run_id, "state": "RUNNING"}
        run_id = args[0]
        if command == "status":
            if self.query_failures:
                self.query_failures -= 1
                raise CaoError("connection lost", transient=True)
            if run_id not in self.runs:
                raise CaoError("unknown run", missing=True)
            return {"run_id": run_id, "workflow_name": self.runs[run_id], "state": self.state}
        if command == "result":
            return {
                "run_id": run_id,
                "workflow_name": self.runs[run_id],
                "state": self.state,
                "output": self.output,
                "steps": [],
            }
        if command in {"resume", "cancel"}:
            return {"run_id": run_id, "state": "RUNNING"}
        raise AssertionError(command)


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project with spaces"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.feature = "001-feature"
        self.project = Project(self.root, self.feature)
        self.project.spec_dir.mkdir(parents=True)
        for name in ("spec.md", "plan.md", "tasks.md"):
            (self.project.spec_dir / name).write_text("approved " + name)
        (self.root / ".specify").mkdir()
        for name in ("specify", "clarify", "plan", "tasks", "analyze"):
            path = self.root / ".agents/skills" / ("speckit-" + name)
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text("fixture")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Tester",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "specs",
            ],
            check=True,
        )
        approve(self.project, "human", "manual")
        self.cao = FakeCao()
        self.runner = SkillRunner(self.root, self.cao, endpoint="fixture://cao")

    def start(self, command=None, **kwargs):
        return self.runner.start(parse_request(command or ["dev", "run", self.feature]), **kwargs)

    def test_metadata_and_command_mapping(self):
        import yaml

        self.assertEqual(len(validate_skills(ROOT / "codex-skills")), 5)
        for path in (ROOT / "codex-skills").glob("*/SKILL.md"):
            metadata = yaml.safe_load(path.read_text().split("---", 2)[1])
            self.assertEqual(metadata["name"], path.parent.name)
            self.assertIsInstance(metadata["description"], str)
        cases = [
            ("spec plan requirement", "cao-spec", "spec-planner"),
            ("spec update 001-feature change", "cao-spec", "spec-update"),
            ("dev run 001-feature", "cao-dev", "development-orchestrator"),
            ("issue run 123", "cao-issue", "issue-orchestrator"),
            ("pr review 45", "cao-pr-review", "pr-review"),
            ("pr apply 45", "cao-pr-apply", "pr-apply"),
        ]
        for command, skill, workflow in cases:
            with self.subTest(command=command):
                parsed = parse_request(command.split())
                self.assertEqual((parsed.skill, parsed.workflow), (skill, workflow))
        self.assertEqual(parse_request(["$cao-dev", "dev", "run", self.feature]).skill, "cao-dev")

    def test_invalid_inputs_block_before_cao(self):
        for command in (
            ["dev", "run", "../escape"],
            ["issue", "run", "0"],
            ["pr", "apply", "-2"],
            ["dev", "status", "--evil"],
            ["spec", "plan", ""],
            ["pr", "merge", "45"],
        ):
            with self.subTest(command=command), self.assertRaises(ValueError):
                parse_request(command)
        self.assertEqual(self.cao.calls, [])

    def test_registry_symlink_cannot_write_outside_project(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (self.root / ".cao-runs").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            SkillRunner(self.root, self.cao, endpoint="fixture://cao")
        self.assertEqual(list(outside.iterdir()), [])

    def test_exact_inputs_single_orchestrator_and_durable_status(self):
        value = self.start()
        submitted = next(c for c in self.cao.calls if c[0] == "run")
        self.assertEqual(submitted[1][0], "development-orchestrator")
        self.assertIn("project=" + str(self.root), submitted[1])
        self.assertIn("feature=" + self.feature, submitted[1])
        self.assertIn("dry_run=true", submitted[1])
        other = SkillRunner(self.root, self.cao, endpoint="fixture://cao")
        self.assertEqual(other.status(value["run_id"])["status"], "RUNNING")
        self.assertEqual(sum(c[0] == "run" for c in self.cao.calls), 1)

    def test_spec_missing_changed_or_policy_approval_blocks(self):
        (self.project.spec_dir / "spec.md").write_text("changed")
        with self.assertRaisesRegex(ValueError, "BLOCKED_SPEC"):
            self.start()
        self.assertEqual(self.cao.calls, [])

    def test_run_id_collision_and_duplicate_identity(self):
        value = self.start(run_id="chosen-id")
        with self.assertRaisesRegex(ValueError, "existing|duplicate|collision"):
            self.start(run_id="chosen-id")
        same = self.start()
        self.assertEqual(same["run_id"], value["run_id"])
        self.assertEqual(sum(c[0] == "run" for c in self.cao.calls), 1)

    def test_ambiguous_submit_never_submits_again(self):
        self.cao.ambiguous = True
        value = self.start()
        self.assertEqual(value["status"], "RUNNING")
        self.assertEqual(self.start()["run_id"], value["run_id"])
        self.assertEqual(sum(c[0] == "run" for c in self.cao.calls), 1)

    def test_terminal_failure_cancel_human_and_no_evidence_success(self):
        run_id = self.start()["run_id"]
        for state, output, expected in [
            ("FAILED", result("MAX_RETRIES", run_id=run_id), "MAX_RETRIES"),
            ("CANCELLED", None, "CANCELLED"),
            ("COMPLETED", result("HUMAN_REQUIRED", run_id=run_id), "HUMAN_REQUIRED"),
            ("COMPLETED", result("COMPLETED", run_id=run_id), "UNVERIFIED"),
            ("COMPLETED", None, "UNVERIFIED"),
        ]:
            with self.subTest(expected=expected):
                self.cao.state, self.cao.output = state, output
                self.assertEqual(self.runner.status(run_id)["status"], expected)

    def test_connection_failure_recovery_and_bounded_wait(self):
        run_id = self.start()["run_id"]
        self.cao.query_failures = 1
        value = self.runner.status(run_id)
        self.assertEqual(value["status"], "CONNECTION_LOST")
        self.assertEqual(self.runner.status(run_id)["status"], "RUNNING")
        self.assertEqual(self.runner.follow(run_id, polls=2, interval=0)["status"], "RUNNING")
        self.assertEqual(sum(c[0] == "run" for c in self.cao.calls), 1)

    def test_resume_cancel_existing_run_only_and_project_binding(self):
        run_id = self.start()["run_id"]
        with self.assertRaises(ValueError):
            self.runner.resume(run_id)
        self.cao.state = "FAILED"
        self.runner.resume(run_id)
        self.runner.cancel(run_id)
        self.assertEqual(sum(c[0] == "run" for c in self.cao.calls), 1)
        other = SkillRunner(self.root, self.cao, endpoint="fixture://other")
        with self.assertRaises(ValueError):
            other.status(run_id)

    def test_live_execution_requires_verified_isolation_and_remote_permission(self):
        with patch(
            "workflow_lib.codex_skills.verify_executor",
            side_effect=ValueError("BLOCKED_ENVIRONMENT"),
        ):
            with self.assertRaisesRegex(ValueError, "BLOCKED_ENVIRONMENT"):
                self.start(execute=True)
        self.assertFalse(any(c[0] == "run" for c in self.cao.calls))
        with self.assertRaises(ValueError):
            self.start(["pr", "apply", "45"], execute=True, settings={"feature": self.feature})

    def test_spec_plan_allocates_feature_without_starting_development(self):
        value = self.start(["spec", "plan", "Kafka failover"])
        self.assertEqual(value["workflow"], "spec-planner")
        self.assertTrue(value["feature"].startswith("001-"))
        self.assertFalse(any("development-orchestrator" in c[1] for c in self.cao.calls))

    def test_wrong_issue_receipt_and_repository_block(self):
        with self.assertRaises(ValueError):
            self.start(["issue", "run", "123"], settings={"feature": self.feature})
        with self.assertRaises(ValueError):
            self.start(
                ["pr", "review", "45"], settings={"feature": self.feature, "repo": "other/repo"}
            )

    def test_never_merge_static_and_no_mock_mutation(self):
        from workflow_lib.merge_guard import inspect_source

        self.assertEqual(inspect_source(ROOT), [])
        self.start()
        self.assertTrue(all(c[0] in {"get", "status", "run"} for c in self.cao.calls))

    def test_actual_lowercase_cao_state_and_script_get_shape(self):
        original = self.cao.call

        def actual_get(command, *args, **kwargs):
            value = original(command, *args, **kwargs)
            if command == "get":
                value.pop("mode")
                value["path"] = "/cao/workflows/" + args[0] + ".py"
                value["source"] = "INPUTS = {}"
            return value

        self.cao.call = actual_get
        self.cao.state = "running"
        value = self.start()
        self.assertEqual(value["status"], "RUNNING")
        self.cao.state = "completed"
        self.cao.output = result("DRY_RUN", run_id=value["run_id"])
        self.assertEqual(self.runner.status(value["run_id"])["status"], "DRY_RUN")

    def test_real_gate_evidence_success_then_failed_final_gate_is_unverified(self):
        run_id = self.start()["run_id"]
        self.cao.state = "COMPLETED"
        gates = [
            {
                "argv": ["pytest"],
                "exit_code": 0,
                "log": "refactor-test.log",
                "tests": 2,
                "failures": [],
                "errors": [],
            },
            {
                "argv": ["ruff"],
                "exit_code": 0,
                "log": "refactor-static.log",
                "tests": 0,
                "failures": [],
                "errors": [],
            },
            {
                "argv": ["coverage"],
                "exit_code": 0,
                "log": "refactor-coverage.log",
                "tests": 0,
                "failures": [],
                "errors": [],
            },
            {"review": {"status": "PASS", "findings": []}},
        ]
        self.cao.output = result("COMPLETED", run_id=run_id, evidence=gates)
        self.assertEqual(self.runner.status(run_id)["status"], "COMPLETED")
        self.cao.output["evidence"].insert(
            3, {**gates[0], "exit_code": 1, "failures": ["bad"], "log": "final-test.log"}
        )
        self.assertEqual(self.runner.status(run_id)["status"], "UNVERIFIED")

    def test_resume_never_uses_stale_failed_snapshot_after_connection_loss(self):
        run_id = self.start()["run_id"]
        self.cao.state = "FAILED"
        self.runner.status(run_id)
        self.cao.query_failures = 1
        with self.assertRaises(ValueError):
            self.runner.resume(run_id)
        self.assertFalse(any(c[0] == "resume" for c in self.cao.calls))

    def test_changed_config_cannot_launch_second_run_for_same_feature(self):
        config = self.root / "config.json"
        config.write_text("{}")
        first = self.start(settings={"config": "config.json"})
        config.write_text('{"max_agent_steps": 5}')
        with self.assertRaises(ValueError):
            self.start(settings={"config": "config.json"})
        self.assertEqual(sum(c[0] == "run" for c in self.cao.calls), 1)
        self.assertEqual(self.runner.status(first["run_id"])["status"], "RUNNING")

    def test_cao_transport_retries_reads_only_and_classifies_404(self):
        offline = subprocess.CompletedProcess(
            [], 1, "", "Error: could not reach cao-server: Connection refused"
        )
        ok = subprocess.CompletedProcess([], 0, '{"run_id":"id","state":"running"}', "")
        with (
            patch(
                "workflow_lib.codex_skills.subprocess.run", side_effect=[offline, offline, ok]
            ) as run,
            patch("workflow_lib.codex_skills.time.sleep"),
        ):
            self.assertEqual(Cao("cao").call("status", "id")["state"], "running")
            self.assertEqual(run.call_count, 3)
        with patch("workflow_lib.codex_skills.subprocess.run", return_value=offline) as run:
            with self.assertRaises(CaoError):
                Cao("cao").call("run", "spec-planner", read=False)
            self.assertEqual(run.call_count, 1)
        missing = subprocess.CompletedProcess([], 1, "", "Error: unknown workflow 'gone'")
        with patch("workflow_lib.codex_skills.subprocess.run", return_value=missing) as run:
            with self.assertRaises(CaoError) as error:
                Cao("cao").call("get", "gone")
            self.assertTrue(error.exception.missing)
            self.assertEqual(run.call_count, 1)

    def test_spec_plan_repeat_reuses_id_and_safe_argument_array(self):
        requirement = 'Kafka "quoted" $(touch bad) ; --evil'
        value = self.start(["spec", "plan", requirement])
        self.assertEqual(self.start(["spec", "plan", requirement])["run_id"], value["run_id"])
        call = next(c for c in self.cao.calls if c[0] == "run")
        self.assertIn("requirement=" + requirement, call[1])
        self.assertFalse((self.root / "bad").exists())

    def test_new_explicit_spec_update_after_terminal_run_is_allowed(self):
        first = self.start(["spec", "update", self.feature, "first change"])
        self.cao.state = "COMPLETED"
        self.cao.output = result("DRY_RUN", run_id=first["run_id"])
        second = self.start(["spec", "update", self.feature, "second change"])
        self.assertNotEqual(first["run_id"], second["run_id"])

    def test_frozen_inputs_reject_tamper_on_resume(self):
        config = self.root / "config.json"
        config.write_text("{}")
        run_id = self.start(settings={"config": "config.json"})["run_id"]
        record = self.runner.load(run_id)
        frozen = Path(record["inputs"]["config"])
        self.assertNotEqual(frozen, config)
        frozen.write_text('{"changed":true}')
        self.cao.state = "FAILED"
        with self.assertRaisesRegex(ValueError, "frozen"):
            self.runner.resume(run_id)
        self.assertFalse(any(c[0] == "resume" for c in self.cao.calls))

    def test_actual_cao_retained_result_omits_output_use_owned_durable_artifact(self):
        import hashlib

        self.runner = SkillRunner(
            self.root, self.cao, endpoint="fixture://cao", cao_home=Path(self.tmp.name) / "cao-home"
        )
        run_id = self.start()["run_id"]
        self.cao.state = "completed"
        directory = (
            self.runner.cao_home
            / "workflow-data"
            / hashlib.sha256(run_id.encode()).hexdigest()[:20]
        )
        directory.mkdir(parents=True)
        (directory / "result.json").write_text(json.dumps(result("DRY_RUN", run_id=run_id)))
        value = self.runner.status(run_id)
        self.assertEqual(value["status"], "DRY_RUN")
        self.assertEqual(value["result_source"], "workflow-owned-artifact")
        (directory / "result.json").write_text(
            json.dumps(result("DRY_RUN", run_id="different-run"))
        )
        self.assertEqual(self.runner.status(run_id)["status"], "UNVERIFIED")

    def test_pr_apply_requires_all_confirmed_thread_fields_and_evidence(self):
        from workflow_lib.codex_skills import completion_evidence

        gates = [
            {
                "argv": [name],
                "exit_code": 0,
                "tests": 1 if name == "test" else 0,
                "errors": [],
                "failures": [],
            }
            for name in ("test", "static", "coverage")
        ]
        thread = {
            "thread_id": "thread",
            "resolution_status": "RESOLVED",
            "fix_commit_sha": "a" * 40,
            "test_evidence": gates,
            "reply_comment_id": 1,
            "github_is_resolved": True,
        }
        value = result("PASS", evidence=gates, head_sha="a" * 40, threads=[thread])
        self.assertTrue(completion_evidence("pr-apply", value))
        thread["reply_comment_id"] = None
        self.assertFalse(completion_evidence("pr-apply", value))

    def test_all_workflow_inputs_and_eligible_issue_mock_integration(self):
        from workflow_lib.issue_intake import event_digest

        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "remote",
                "add",
                "origin",
                "git@github.com:owner/repo.git",
            ],
            check=True,
        )
        event = {
            "event_id": "evt",
            "origin_id": "origin",
            "repo": "owner/repo",
            "issue_number": 123,
            "author": "bot",
            "body": "Improve value",
            "risk": "low",
            "files": ["src/value.py"],
        }
        # Use the actual existing Issue event contract.
        schema = json.loads((ROOT / "contracts/issue-event.schema.json").read_text())
        for key in schema["required"]:
            self.assertIn(key, event)
        policy = {
            "repo": "owner/repo",
            "repositories": ["owner/repo"],
            "trusted_authors": ["bot"],
            "auto_low_risk": True,
            "allowed_files": ["src/*"],
            "origins": {"origin": {"event_id": "evt", "digest": event_digest(event)}},
        }
        (self.root / "event.json").write_text(json.dumps(event))
        (self.root / "policy.json").write_text(json.dumps(policy))
        settings = {"feature": self.feature, "event": "event.json", "policy": "policy.json"}
        for command, workflow in [
            (["issue", "run", "123"], "issue-orchestrator"),
            (["pr", "review", "45"], "pr-review"),
            (["pr", "apply", "45"], "pr-apply"),
            (["spec", "update", self.feature, "change"], "spec-update"),
        ]:
            with self.subTest(workflow=workflow):
                value = self.start(command, settings=settings)
                self.assertEqual(value["workflow"], workflow)
                call = [c for c in self.cao.calls if c[0] == "run"][-1]
                self.assertIn("project=" + str(self.root), call[1])
                if workflow.startswith("pr-"):
                    self.assertIn("pr_number=45", call[1])
        event["issue_number"] = 124
        (self.root / "event.json").write_text(json.dumps(event))
        with self.assertRaises(ValueError):
            self.start(["issue", "run", "123"], settings=settings)

    def test_current_codex_profile_files_validated_and_native_probe_required(self):
        from workflow_lib.codex_skills import verify_executor
        from workflow_lib.isolation import codex_profiles_safe

        home = Path(self.tmp.name) / "codex"
        home.mkdir()
        config = home / "config.toml"
        config.write_text("")
        for name, mode in (("readonly", "read-only"), ("write", "workspace-write")):
            (home / f"cao-workflows-{name}.config.toml").write_text(
                f'approval_policy="never"\nsandbox_mode="{mode}"\n[sandbox_workspace_write]\nnetwork_access=false\nwritable_roots=[]\n'
            )
        self.assertTrue(codex_profiles_safe(config))
        ok = subprocess.CompletedProcess([], 0, b"", b"")
        failed = subprocess.CompletedProcess([], 1, b"", b"missing profile")
        with patch("workflow_lib.codex_skills.subprocess.run", side_effect=[ok, failed]) as run:
            with self.assertRaisesRegex(ValueError, "Codex.*executor"):
                verify_executor(self.project, {"codex_config_path": str(config)})
            self.assertIn("sandbox", run.call_args.args[0])

    def test_pr_completion_reports_authoritative_unresolved_count_and_sha_race(self):
        from unittest.mock import Mock

        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "remote",
                "add",
                "origin",
                "git@github.com:owner/repo.git",
            ],
            check=True,
        )
        run_id = self.start()["run_id"]
        record = self.runner.load(run_id)
        record.update(workflow="pr-review")
        record["inputs"]["dry_run"] = False
        record["inputs"]["policy"] = str(self.root / "policy.json")
        (self.root / "policy.json").write_text(
            '{"repo":"owner/repo","repositories":["owner/repo"]}'
        )
        record["inputs"]["pr_number"] = 45
        self.runner.save(record)
        self.cao.runs[run_id] = "pr-review"
        self.cao.state = "COMPLETED"
        self.cao.output = result(
            "PASS",
            run_id=run_id,
            repo="owner/repo",
            pr_number=45,
            head_sha="a" * 40,
            evidence=[{"status": "PASS", "head_sha": "a" * 40, "findings": []}],
        )
        api = Mock()
        api.pr.return_value = {"state": "OPEN", "head_sha": "a" * 40}
        api.threads.return_value = [{"is_resolved": False}, {"is_resolved": True}]
        with patch("workflow_lib.codex_skills.GitHub", return_value=api) as factory:
            value = self.runner.status(run_id)
            self.assertEqual(value["status"], "PASS")
            self.assertEqual(value["unresolved_thread_count"], 1)
            self.assertEqual(factory.call_args.kwargs["dry_run"], True)
            self.assertEqual(factory.call_args.kwargs["authorized"], False)
            api.pr.return_value = {"state": "OPEN", "head_sha": "b" * 40}
            self.assertEqual(self.runner.status(run_id)["status"], "HUMAN_REQUIRED")
            self.assertFalse(api.call.called)


if __name__ == "__main__":
    unittest.main()
