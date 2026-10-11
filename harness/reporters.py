import json
from pathlib import Path

from workflow_lib.contracts import validate_result
from workflow_lib.installation import atomic


def report(directory, value):
    observed = {}
    pending = [value.get("evidence", [])]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            if (
                item.get("log")
                and isinstance(item.get("argv"), list)
                and isinstance(item.get("duration_seconds"), (int, float))
            ):
                observed[item["log"]] = item
            pending.extend(v for v in item.values() if isinstance(v, (dict, list)))
    value["metrics"] = {
        "commands": len(observed),
        "command_seconds": sum(v["duration_seconds"] for v in observed.values()),
        "failed_commands": sum(v.get("exit_code") != 0 for v in observed.values()),
        "cost": None,
        "human_interventions": None,
    }
    validate_result(value)
    directory = Path(directory)
    atomic(directory / "result.json", json.dumps(value, indent=2, sort_keys=True).encode())
    lines = [
        f"# Run {value['run_id']}",
        "",
        f"Status: {value['status']}",
        f"Next: {value['next_action']}",
        "",
        "```json",
        json.dumps(value["evidence"], indent=2),
        "```",
    ]
    atomic(directory / "result.md", "\n".join(lines).encode())
