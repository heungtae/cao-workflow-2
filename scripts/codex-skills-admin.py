#!/usr/bin/env python3
"""Install, remove and validate Codex Skills without touching CAO or GitHub."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow_lib.codex_skills import project_root, validate_skills  # noqa: E402
from workflow_lib.merge_guard import inspect_source  # noqa: E402
from workflow_lib.skill_installation import install_skills, uninstall_skills, verify_installation  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "uninstall", "validate"])
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--global", dest="global_scope", action="store_true")
    scope.add_argument("--project")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "validate":
        violations = inspect_source(ROOT)
        if violations:
            raise ValueError("executable safety violations: " + str(violations))
    # Default is source validation, global scope for install/uninstall.
    if args.command == "validate" and not (args.global_scope or args.project):
        print(json.dumps({"source_skills": validate_skills(ROOT / "codex-skills")}))
        return 0
    destination = (project_root(args.project) if args.project else Path.home()) / ".agents/skills"
    if args.command == "install":
        value = install_skills(ROOT, destination, dry_run=args.dry_run, force=args.force)
        value = {"owned_files": len(value["files"]), "dry_run": args.dry_run}
    elif args.command == "uninstall":
        value = {
            "owned_files": uninstall_skills(destination, dry_run=args.dry_run, force=args.force),
            "dry_run": args.dry_run,
        }
    else:
        value = verify_installation(destination)
    print(json.dumps({"destination": str(destination), **value}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
