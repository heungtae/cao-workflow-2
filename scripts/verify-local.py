#!/usr/bin/env python3
"""Full isolated integration gate. No Agent steps and no GitHub traffic."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    python = ROOT / ".venv/bin/python"
    cao_server = ROOT / ".venv/bin/cao-server"
    with tempfile.TemporaryDirectory(prefix="cao-workflows-validation-") as tmp:
        home = Path(tmp) / "cao-home"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            **os.environ,
            "CAO_HOME_DIR": str(home),
            "CAO_API_PORT": str(port),
            "CAO_TEST_ISOLATION": "1",
        }
        log = ROOT / "docs/local-server.log"
        with log.open("w") as output:
            server = subprocess.Popen(
                [str(cao_server), "--host", "127.0.0.1", "--port", str(port)],
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                cwd=ROOT,
            )
            try:
                ready = False
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("validation server exited; see docs/local-server.log")
                    try:
                        urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/health", timeout=0.5
                        ).close()
                        ready = True
                        break
                    except OSError:
                        time.sleep(0.1)
                if not ready:
                    raise RuntimeError("server readiness timeout")

                def run(*args):
                    subprocess.run([*map(str, args)], env=env, cwd=ROOT, check=True, timeout=180)

                run(ROOT / "scripts/doctor.sh", "--cao-home", home)
                run(ROOT / "scripts/install.sh", "--cao-home", home, "--dry-run")
                self_manifest = home / "cao-workflows-manifest.json"
                assert not self_manifest.exists()
                run(ROOT / "scripts/install.sh", "--cao-home", home)
                first = self_manifest.read_bytes()
                run(ROOT / "scripts/install.sh", "--cao-home", home)
                assert self_manifest.read_bytes() == first
                # Validate deployed profile frontmatter against the actual CAO schema.
                import importlib.resources

                import frontmatter
                import jsonschema

                schema = json.loads(
                    importlib.resources.files("cli_agent_orchestrator")
                    .joinpath("schemas/agent_profile.schema.json")
                    .read_text()
                )
                for profile in (home / "agent-store").glob("*.md"):
                    jsonschema.validate(frontmatter.load(profile).metadata, schema)
                run(ROOT / "scripts/validate.sh", "--cao-home", home)
                # Actual installed shim/input/output imports; fixture skills only.
                target = Path(tmp) / "target"
                target.mkdir()
                run("git", "init", "-q", target)
                (target / ".specify").mkdir()
                for name in ["specify", "clarify", "plan", "tasks", "analyze"]:
                    skill = target / ".agents/skills" / ("speckit-" + name)
                    skill.mkdir(parents=True)
                    (skill / "SKILL.md").write_text("Mock installed skill fixture")
                smoke_env = {
                    **env,
                    "CAO_WORKFLOW_RUN_ID": "fixture-dry-run",
                    "CAO_WORKFLOW_INPUTS": json.dumps(
                        {"project": str(target), "feature": "001-fixture", "dry_run": True}
                    ),
                }
                process = subprocess.run(
                    [str(python), str(home / "workflows/spec-planner.py")],
                    env=smoke_env,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                sentinel = next(
                    line
                    for line in process.stdout.splitlines()
                    if line.startswith("CAO_WORKFLOW_OUTPUT:")
                )
                value = json.loads(sentinel.split(":", 1)[1])
                assert value["status"] == "DRY_RUN"
                run(
                    python,
                    ROOT / "scripts/cli.py",
                    "status",
                    "--cao-home",
                    home,
                    "--key",
                    "fixture-dry-run",
                )
                run(
                    python,
                    ROOT / "scripts/cli.py",
                    "cancel",
                    "--cao-home",
                    home,
                    "--key",
                    "fixture-dry-run",
                )
                snapshot = Path(tmp) / "relocated-snapshot.py"
                snapshot.write_bytes((home / "workflows/spec-planner.py").read_bytes())
                stripped = {
                    k: smoke_env[k]
                    for k in ("CAO_WORKFLOW_INPUTS", "PATH", "HOME")
                    if k in smoke_env
                }
                stripped.update(
                    CAO_WORKFLOW_RUN_ID="fixture-relocated",
                    CAO_WORKFLOW_GENERATION="2",
                    CAO_API_BASE_URL=f"http://127.0.0.1:{port}",
                    CAO_WORKFLOW_RESUME="1",
                )
                relocated = subprocess.run(
                    [str(python), str(snapshot)],
                    env=stripped,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                assert '"status": "DRY_RUN"' in relocated.stdout
                # Offline trigger CLI is exercised without GitHub reads or CAO submissions.
                trigger_policy = Path(tmp) / "trigger-policy.json"
                trigger_policy.write_text(
                    json.dumps({"repositories": ["owner/repo"], "trigger_workflows": ["pr-review"]})
                )
                trigger_config = Path(tmp) / "trigger-config.json"
                trigger_config.write_text("{}")
                binding = Path(tmp) / "trigger-binding.json"
                binding.write_text(
                    json.dumps(
                        {
                            "project": str(target),
                            "feature": "001-fixture",
                            "policy": str(trigger_policy),
                            "config": str(trigger_config),
                            "state_file": str(home / "workflow-data/triggers.db"),
                        }
                    )
                )
                events = Path(tmp) / "events.json"
                events.write_text(
                    json.dumps(
                        [
                            {
                                "source": "github-pr",
                                "workflow": "pr-review",
                                "repo": "owner/repo",
                                "pr_number": 1,
                                "head_sha": "a" * 40,
                            }
                        ]
                    )
                )
                trigger = subprocess.run(
                    [
                        str(python),
                        str(ROOT / "scripts/trigger.py"),
                        "--binding",
                        str(binding),
                        "--events-file",
                        str(events),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                assert json.loads(trigger.stdout)[0]["status"] == "DRY_RUN"
                # A blocked Agent preflight must emit a valid result AND fail the CAO process.
                failure_config = Path(tmp) / "failure-config.json"
                failure_config.write_text(
                    json.dumps({"codex_config_path": str(Path(tmp) / "missing-codex.toml")})
                )
                failure_env = {
                    **smoke_env,
                    "CAO_WORKFLOW_RUN_ID": "fixture-blocked",
                    "CAO_WORKFLOW_INPUTS": json.dumps(
                        {
                            "project": str(target),
                            "feature": "001-blocked",
                            "config": str(failure_config),
                            "dry_run": False,
                            "requirement": "Fixture requirement",
                        }
                    ),
                }
                failure = subprocess.run(
                    [str(python), str(home / "workflows/spec-planner.py")],
                    env=failure_env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert failure.returncode == 1
                blocked = next(
                    line
                    for line in failure.stdout.splitlines()
                    if line.startswith("CAO_WORKFLOW_OUTPUT:")
                )
                assert json.loads(blocked.split(":", 1)[1])["status"] == "BLOCKED_ENVIRONMENT"
                user_file = home / "settings-user.json"
                user_file.write_text('{"preserve":true}')
                owned = list(json.loads(first)["files"])
                run(ROOT / "scripts/uninstall.sh", "--cao-home", home, "--dry-run")
                assert self_manifest.exists()
                run(ROOT / "scripts/uninstall.sh", "--cao-home", home)
                assert user_file.read_text() == '{"preserve":true}'
                assert not self_manifest.exists()
                assert all(not (home / p).exists() for p in owned)
                print(
                    "LOCAL INTEGRATION PASS: install/reinstall/11 CAO validates/profile schema/full tests/dry-run shim/status/cancel/uninstall"
                )
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
