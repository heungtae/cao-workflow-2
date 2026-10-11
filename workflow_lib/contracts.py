"""Fail-closed JSON contracts. The installed library includes the schemas."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent / "contracts"


def validate(value, schema):
    try:
        Draft202012Validator(json.loads((ROOT / schema).read_text())).validate(value)
    except Exception as error:
        raise ValueError(f"invalid {schema}: {error}") from error
    return value


def validate_result(value):
    return validate(value, "workflow-result.schema.json")


def result(
    status,
    *,
    run_id="local",
    repo=None,
    issue_number=None,
    pr_number=None,
    head_sha=None,
    next_action=None,
    artifacts=(),
    evidence=(),
    **extra,
):
    value = dict(
        run_id=run_id,
        repo=repo,
        issue_number=issue_number,
        pr_number=pr_number,
        head_sha=head_sha,
        status=status,
        next_action=next_action,
        artifacts=list(artifacts),
        evidence=list(evidence),
        **extra,
    )
    return validate_result(value)
