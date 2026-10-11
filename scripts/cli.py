#!/usr/bin/env python3
"""Repository administration; no agent or GitHub side effects."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow_lib.approvals import approve
from workflow_lib.installation import install, uninstall
from workflow_lib.issue_state import State
from workflow_lib.merge_guard import inspect_source
from workflow_lib.project import Project


def cao_binary():
    explicit = os.environ.get("CAO_BIN")
    return explicit or (
        str(ROOT / ".venv/bin/cao") if (ROOT / ".venv/bin/cao").exists() else shutil.which("cao")
    )


def check_cao(home, paths):
    binary = cao_binary()
    if not binary:
        raise RuntimeError("CAO is not installed; install CAO before deployment")
    env = {**os.environ, "CAO_HOME_DIR": str(home)}
    for path in paths:
        subprocess.run([binary, "workflow", "validate", str(path)], env=env, check=True, timeout=60)


def doctor(home, project=None, feature=None):
    binary = cao_binary()
    report = {
        "cao_binary": binary,
        "cao_home": str(home),
        "python": sys.version.split()[0],
        "gh": shutil.which("gh"),
        "specify": shutil.which("specify"),
        "bwrap": shutil.which("bwrap"),
        "profiles": sorted(p.stem for p in (home / "agent-store").glob("*.md")),
        "runtime_agents_verified": False,
        "github_live_verified": False,
    }
    report["codex_binary"] = shutil.which("codex")
    try:
        from workflow_lib.isolation import codex_profiles_safe

        codex_profiles_safe(
            Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
        )
        report["agent_config_ready"] = True
    except (OSError, ValueError):
        report["agent_config_ready"] = False
    code = 0
    if binary:
        proc = subprocess.run(
            [binary, "workflow", "--help"],
            env={**os.environ, "CAO_HOME_DIR": str(home)},
            capture_output=True,
            text=True,
            timeout=60,
        )
        report["cao_version"] = subprocess.run(
            [binary, "--version"],
            env={**os.environ, "CAO_HOME_DIR": str(home)},
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.strip()
        report["supported_commands"] = [
            name
            for name in ("run", "validate", "status", "cancel", "resume", "result")
            if name in proc.stdout
        ]
        report["cao_cli_ok"] = proc.returncode == 0 and len(report["supported_commands"]) == 6
        code = 0 if report["cao_cli_ok"] else 1
    else:
        code = 1
        report["cao_cli_ok"] = False
    if project:
        try:
            target = Project(project, feature or "doctor")
            report["spec_kit_skills"] = target.skills()
        except (ValueError, OSError) as error:
            report["target_error"] = str(error)
            code = 1
    print(json.dumps(report, indent=2))
    return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["install", "uninstall", "validate", "doctor", "approve-spec", "status", "cancel"],
    )
    parser.add_argument(
        "--cao-home",
        default=os.environ.get("CAO_HOME_DIR", str(Path.home() / ".aws/cli-agent-orchestrator")),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--profile-mode", choices=["copy", "link"], default="copy")
    parser.add_argument("--project")
    parser.add_argument("--feature")
    parser.add_argument("--actor")
    parser.add_argument("--key")
    args = parser.parse_args()
    home = Path(args.cao_home).expanduser().resolve()
    if args.command == "install":

        def check():
            check_cao(home, sorted((home / "workflows").glob("*.py")))
            if doctor(home):
                raise RuntimeError("post-install doctor failed")

        manifest = install(
            ROOT,
            home,
            dry_run=args.dry_run,
            force=args.force,
            profile_mode=args.profile_mode,
            check=check,
        )
        print(json.dumps({"dry_run": args.dry_run, "owned_files": len(manifest["files"])}))
    elif args.command == "uninstall":
        print(json.dumps(uninstall(home, dry_run=args.dry_run, force=args.force)))
    elif args.command == "doctor":
        return doctor(home, args.project, args.feature)
    elif args.command == "approve-spec":
        if not args.actor:
            parser.error("--actor required for human approval")
        print(json.dumps(approve(Project(args.project, args.feature), args.actor, "manual")))
    elif args.command in {"status", "cancel"}:
        if args.command == "cancel":
            if not args.key:
                parser.error("--key required")
            State.cancel(home / "workflow-data/state.db", args.key)
        print(json.dumps(State.status(home / "workflow-data/state.db", args.key), indent=2))
    elif args.command == "validate":
        subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            [
                str(ROOT / ".venv/bin/ruff"),
                "check",
                "workflow_lib",
                "workflows",
                "harness",
                "scripts",
                "tests",
            ],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            [
                str(ROOT / ".venv/bin/ruff"),
                "format",
                "--check",
                "workflow_lib",
                "workflows",
                "harness",
                "scripts",
                "tests",
            ],
            cwd=ROOT,
            check=True,
        )
        shellcheck = shutil.which("shellcheck")
        if shellcheck:
            subprocess.run(
                [shellcheck, *map(str, sorted((ROOT / "scripts").glob("*.sh")))], check=True
            )
        else:
            print("ShellCheck unavailable (not claimed as passed)", file=sys.stderr)
        violations = inspect_source(ROOT)
        if violations:
            raise ValueError("executable safety violations: " + str(violations))
        from workflow_lib.installation import inventory

        for relative, data in inventory(ROOT, home).items():
            target = home / relative
            if not target.is_file() or target.read_bytes() != data:
                raise ValueError("install current source before CAO validation")
        check_cao(home, sorted((home / "workflows").glob("*.py")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
