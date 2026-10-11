import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

from workflow_lib.installation import atomic
from workflow_lib.isolation import isolated_argv
from workflow_lib.merge_guard import guard_argv


@dataclass
class GateEvidence:
    argv: list
    exit_code: int
    log: str
    tests: int
    failures: list
    errors: list
    junit: str | None
    assertion_only: bool
    duration_seconds: float = 0
    junit_files: list = field(default_factory=list)

    @property
    def passed(self):
        return self.exit_code == 0 and not self.errors and not self.failures

    def json(self):
        return asdict(self)


def redact(value):
    value = re.sub(r"AKIA[A-Z0-9]{16}", "[REDACTED]", value)
    value = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        "[REDACTED]",
        value,
        flags=re.DOTALL,
    )
    value = re.sub(r"(?i)(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)", "[REDACTED]", value)
    return re.sub(
        r"(?i)((?:token|password|secret|authorization)\s*[:=]\s*)\S+", r"\1[REDACTED]", value
    )


def junit_evidence(path):
    root = ET.parse(path).getroot()
    cases = [case for case in root.iter("testcase") if case.find("skipped") is None]
    failures, errors = [], []
    assertion_only = True
    for case in cases:
        identity = (case.get("classname", "") + "::" if case.get("classname") else "") + case.get(
            "name", ""
        )
        for failure in case.findall("failure"):
            failures.append(identity)
            text = (failure.get("type", "") + " " + (failure.text or "")).lower()
            assertion_only = assertion_only and ("assertion" in text or "assert " in text)
        if case.find("error") is not None:
            errors.append(identity)
    # collection errors may live directly under a testsuite
    errors.extend(
        "suite-error"
        for suite in root.iter("testsuite")
        if int(suite.get("errors", "0")) > 0 and not errors
    )
    return len(cases), failures, errors, assertion_only


class QualityGate:
    def __init__(self, project, config, evidence_dir):
        self.project = project
        self.config = {**config, "max_green_attempts": config.get("max_green_attempts", 3)}
        self.evidence_dir = Path(evidence_dir)
        if not all(config.get(key) for key in ("test", "static", "coverage")):
            raise ValueError("test/static/coverage gate commands required")
        self.timeout = int(config.get("timeout_seconds", 300))
        if not 1 <= self.timeout <= 3600:
            raise ValueError("invalid command timeout")

    def execute(self, name, gate):
        argv = guard_argv(gate["argv"])
        pattern = gate.get("junit")
        if pattern and (Path(pattern).is_absolute() or ".." in Path(pattern).parts):
            raise ValueError("junit path escapes project")
        if pattern:
            for path in self.project.root.glob(pattern):
                if not path.resolve().is_relative_to(self.project.root):
                    raise ValueError("junit symlink escape")
                path.unlink(missing_ok=True)
        env = {
            k: v
            for k, v in os.environ.items()
            if not re.search(r"(?i)(token|secret|password|credential)", k)
        }
        started = time.monotonic()
        try:
            command = isolated_argv(
                self.project, argv, readonly_roots=self.config.get("readonly_roots", [])
            )
            proc = subprocess.run(
                command,
                cwd=self.project.root,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            code, output = proc.returncode, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            code, output = 124, "quality command timed out"
        except OSError as error:
            code, output = 127, str(error)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        log = self.evidence_dir / f"{name}.log"
        atomic(log, redact(output).encode())
        tests, failures, errors, assertion_only = 0, [], [], False
        archives = []
        if pattern:
            assertion_only = True
            try:
                paths = sorted(self.project.root.glob(pattern))
                if not paths:
                    raise ValueError("missing junit")
                for index, path in enumerate(paths):
                    if not path.resolve().is_relative_to(self.project.root):
                        raise ValueError("junit symlink escape")
                    count, failed, broken, asserted = junit_evidence(path)
                    tests += count
                    failures.extend(failed)
                    errors.extend(broken)
                    assertion_only = assertion_only and asserted
                    archive = self.evidence_dir / f"{name}-junit-{index}.xml"
                    atomic(archive, path.read_bytes())
                    archives.append(str(archive))
            except (OSError, ET.ParseError, ValueError):
                errors.append("missing-or-invalid-junit")
        value = GateEvidence(
            argv,
            code,
            str(log),
            tests,
            failures,
            errors,
            archives[0] if archives else None,
            assertion_only,
            time.monotonic() - started,
            archives,
        )
        atomic(self.evidence_dir / f"{name}.json", json.dumps(value.json(), indent=2).encode())
        return value

    def __call__(self, stage):
        values = [self.execute(stage + "-test", self.config["test"])]
        if stage != "red" and values[0].passed and values[0].tests > 0:
            values.extend(
                self.execute(stage + "-" + name, self.config[name])
                for name in ("static", "coverage")
            )
        return values
