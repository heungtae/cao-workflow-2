"""CAO Python entrypoint with an immutable, verified installed dependency bundle."""

import hashlib
import json
import sys
from pathlib import Path

from cao_workflow import emit_output, get_inputs

RUNTIME_HOME = None
BUNDLE_DIGEST = None


def bootstrap():
    if RUNTIME_HOME is None or BUNDLE_DIGEST is None:
        raise RuntimeError("Install this workflow before execution")
    bundle = Path(RUNTIME_HOME) / "workflows/.cao-workflows-bundles" / BUNDLE_DIGEST
    entries = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            if not path.resolve().is_relative_to(bundle.resolve()):
                raise RuntimeError("Bundle symlink escapes deployment")
            entries[str(path.relative_to(bundle))] = hashlib.sha256(path.read_bytes()).hexdigest()
    actual = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if actual != BUNDLE_DIGEST:
        raise RuntimeError("Installed dependency bundle changed; execution blocked")
    sys.path.insert(0, str(bundle))


bootstrap()


INPUTS = {
    "project": {"type": "string", "required": True},
    "feature": {"type": "string", "required": True},
    "requirement": {"type": "string", "required": False, "default": ""},
    "config": {"type": "string", "required": False, "default": ""},
    "event": {"type": "string", "required": False, "default": ""},
    "policy": {"type": "string", "required": False, "default": ""},
    "pr_number": {"type": "int", "required": False, "default": 0},
    "dry_run": {"type": "bool", "required": False, "default": True},
    "authorized": {"type": "bool", "required": False, "default": False},
    "max_cycles": {"type": "int", "required": False, "default": 3},
}


def main():
    from workflow_lib.runtime import execute

    value = execute("development-orchestrator", get_inputs(), runtime_home=RUNTIME_HOME)
    emit_output(value)
    if value["status"] in {
        "FAILED",
        "BLOCKED_ENVIRONMENT",
        "BLOCKED_SPEC",
        "CHANGES_REQUIRED",
        "MAX_RETRIES",
        "CANCELLED",
    }:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
