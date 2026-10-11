#!/usr/bin/env python3
"""Real CLI discovery and local CAO dry-run smoke. No model or GitHub writes."""

import json
import os
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow_lib.approvals import approve  # noqa: E402
from workflow_lib.codex_skills import SKILLS, Cao, SkillRunner, parse_request, verify_executor  # noqa: E402
from workflow_lib.installation import install  # noqa: E402
from workflow_lib.issue_intake import event_digest  # noqa: E402
from workflow_lib.project import Project  # noqa: E402
from workflow_lib.skill_installation import install_skills, uninstall_skills  # noqa: E402


def discover(codex, target, env):
    process = subprocess.Popen(
        [codex, "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        text=True,
    )

    def rpc(identifier, method, params):
        process.stdin.write(
            json.dumps({"id": identifier, "method": method, "params": params}) + "\n"
        )
        process.stdin.flush()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if not select.select([process.stdout], [], [], 1)[0]:
                continue
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("Codex app-server ended")
            value = json.loads(line)
            if value.get("id") == identifier:
                if "error" in value:
                    raise RuntimeError(str(value["error"]))
                return value["result"]
        raise RuntimeError("Codex RPC timeout")

    try:
        rpc(
            1,
            "initialize",
            {
                "clientInfo": {"name": "cao-skills-validation", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        process.stdin.write(json.dumps({"method": "initialized"}) + "\n")
        process.stdin.flush()
        value = rpc(2, "skills/list", {"cwds": [str(target)], "forceReload": True})
        rows = value["data"]
        skills = [skill for row in rows for skill in row["skills"] if skill["name"] in SKILLS]
        if {skill["name"] for skill in skills} != set(SKILLS) or any(row["errors"] for row in rows):
            raise RuntimeError("Codex skill discovery failed: " + str(value))
        return [{k: skill.get(k) for k in ("name", "path", "enabled", "scope")} for skill in skills]
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    cao_bin = ROOT / ".venv/bin/cao"
    server_bin = ROOT / ".venv/bin/cao-server"
    codex = shutil.which("codex")
    if not cao_bin.exists() or not codex:
        raise RuntimeError("real CAO/Codex binaries required")
    with tempfile.TemporaryDirectory(prefix="cao-codex-skills-") as directory:
        temp = Path(directory)
        target = temp / "target project"
        target.mkdir()
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        (target / ".specify").mkdir()
        for name in ("specify", "clarify", "plan", "tasks", "analyze"):
            path = target / ".agents/skills" / ("speckit-" + name)
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(
                f"---\nname: speckit-{name}\ndescription: Isolated smoke fixture.\n---\nFixture only."
            )
        user = temp / "user"
        codex_home = user / ".codex"
        codex_home.mkdir(parents=True)
        (codex_home / "config.toml").write_text("")
        for name, mode in (("readonly", "read-only"), ("write", "workspace-write")):
            (codex_home / f"cao-workflows-{name}.config.toml").write_text(
                f'approval_policy="never"\nsandbox_mode="{mode}"\n[sandbox_workspace_write]\nnetwork_access=false\nwritable_roots=[]\n'
            )
        verify_executor(
            Project(target, "001-probe"), {"codex_config_path": str(codex_home / "config.toml")}
        )
        print(
            json.dumps(
                {
                    "actual_isolated_executor": "PASS",
                    "native_codex_profiles": "PASS",
                    "model_started": False,
                }
            ),
            flush=True,
        )
        env = {**os.environ, "HOME": str(user), "CODEX_HOME": str(codex_home)}
        # These are controlled temporary process homes; never modify the operator's config.
        install_skills(ROOT, target / ".agents/skills")
        project_skills = discover(codex, target, env)
        uninstall_skills(target / ".agents/skills")
        install_skills(ROOT, user / ".agents/skills")
        global_skills = discover(codex, target, env)
        uninstall_skills(user / ".agents/skills")
        print(
            json.dumps(
                {"codex_project_discovery": project_skills, "codex_global_discovery": global_skills}
            ),
            flush=True,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        home = temp / "cao-home"
        env.update(CAO_HOME_DIR=str(home), CAO_API_PORT=str(port))
        with (ROOT / "docs/codex-skills-server.log").open("w") as log:
            server = subprocess.Popen(
                [str(server_bin), "--host", "127.0.0.1", "--port", str(port)],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("CAO server exited")
                    try:
                        urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/health", timeout=0.2
                        ).close()
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("CAO readiness timeout")

                def validate():
                    for path in (home / "workflows").glob("*.py"):
                        proc = subprocess.run(
                            [str(cao_bin), "workflow", "validate", str(path), "--json"],
                            env=env,
                            capture_output=True,
                            text=True,
                            timeout=25,
                        )
                        if proc.returncode:
                            raise RuntimeError("CAO validate failed: " + path.name + proc.stderr)

                install(ROOT, home, check=validate)
                runner = SkillRunner(
                    target, Cao(str(cao_bin), env=env), endpoint=f"http://localhost:{port}"
                )
                value = runner.start(parse_request(["spec", "plan", "Local safe smoke"]))
                value = runner.follow(value["run_id"], polls=30, interval=0.2)
                if value["status"] != "DRY_RUN":
                    print(
                        json.dumps(
                            {
                                "raw_status": runner.cao.call("status", value["run_id"]),
                                "raw_result": runner.cao.call("result", value["run_id"]),
                            }
                        ),
                        flush=True,
                    )
                    raise RuntimeError(
                        "Actual CAO submission did not yield DRY_RUN: " + json.dumps(value)
                    )
                fresh = SkillRunner(
                    target, Cao(str(cao_bin), env=env), endpoint=f"http://localhost:{port}"
                )
                assert fresh.status(value["run_id"])["status"] == "DRY_RUN"
                print(
                    json.dumps(
                        {
                            "cao_actual_submit_status_result": value,
                            "cross_session_status": "PASS",
                            "external_github_writes": 0,
                            "provider_model_execution": "UNVERIFIED",
                            "implicit_model_selection": "UNVERIFIED",
                        }
                    ),
                    flush=True,
                )
                # Fixture approvals are test data; no operator approval is fabricated.
                feature = "001-fixture"
                project = Project(target, feature)
                project.spec_dir.mkdir(parents=True)
                for name in ("spec.md", "plan.md", "tasks.md"):
                    (project.spec_dir / name).write_text("fixture " + name)
                subprocess.run(["git", "-C", str(target), "add", "."], check=True)
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(target),
                        "-c",
                        "user.name=Fixture",
                        "-c",
                        "user.email=fixture@example.invalid",
                        "commit",
                        "-qm",
                        "fixture specs",
                    ],
                    check=True,
                )
                approve(project, "fixture-human", "manual")
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(target),
                        "remote",
                        "add",
                        "origin",
                        "https://github.com/fixture-owner/fixture-repo.git",
                    ],
                    check=True,
                )
                event = {
                    "repo": "fixture-owner/fixture-repo",
                    "issue_number": 123,
                    "author": "fixture-bot",
                    "origin_id": "fixture-origin",
                    "event_id": "fixture-event",
                    "body": "Improve value",
                    "risk": "low",
                    "files": ["src/value.py"],
                }
                policy = {
                    "repo": event["repo"],
                    "repositories": [event["repo"]],
                    "trusted_authors": [event["author"]],
                    "auto_low_risk": True,
                    "allowed_files": ["src/*"],
                    "origins": {
                        event["origin_id"]: {
                            "event_id": event["event_id"],
                            "digest": event_digest(event),
                        }
                    },
                }
                (target / "policy.json").write_text(json.dumps(policy))
                (target / "event.json").write_text(json.dumps(event))
                settings = {"feature": feature, "policy": "policy.json", "event": "event.json"}
                for command in (
                    ["dev", "run", feature],
                    ["spec", "update", feature, "Fixture change"],
                    ["issue", "run", "123"],
                    ["pr", "review", "45"],
                    ["pr", "apply", "45"],
                ):
                    checked = runner.start(parse_request(command), settings=settings)
                    checked = runner.follow(checked["run_id"], polls=30, interval=0.2)
                    assert checked["status"] == "DRY_RUN", checked
                    print(json.dumps({"actual_workflow_dry_run": checked}), flush=True)
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
