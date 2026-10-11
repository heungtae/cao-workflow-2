#!/usr/bin/env python3
"""Invoke the installed immutable shared adapter, or this repository's source."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = None
sys.path.insert(0, str(Path(RUNTIME) if RUNTIME else ROOT))
from workflow_lib.codex_skills import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
