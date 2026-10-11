#!/usr/bin/env python3
"""Source-tree entrypoint; installed Skills carry their own immutable adapter."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_lib.codex_skills import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
