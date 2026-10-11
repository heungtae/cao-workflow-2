"""Thin Codex invocation adapter. CAO owns execution and all business loops."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from harness.quality_gate import redact
from workflow_lib.approvals import verify
from workflow_lib.contracts import validate, validate_result
from workflow_lib.github_pr import GitHub
from workflow_lib.installation import atomic, lock, safe
from workflow_lib.isolation import codex_profiles_safe, isolated_argv
from workflow_lib.issue_intake import intake
from workflow_lib.project import Project

SKILLS = ("cao-spec", "cao-dev", "cao-issue", "cao-pr-review", "cao-pr-apply")
ROUTES = {
    ("spec", "plan"): ("cao-spec", "spec-planner"),
    ("spec", "update"): ("cao-spec", "spec-update"),
    ("dev", "run"): ("cao-dev", "development-orchestrator"),
    ("issue", "run"): ("cao-issue", "issue-orchestrator"),
    ("pr", "review"): ("cao-pr-review", "pr-review"),
    ("pr", "apply"): ("cao-pr-apply", "pr-apply"),
}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}")
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
BLOCKED = {
    "BLOCKED_SPEC",
    "BLOCKED_ENVIRONMENT",
    "HUMAN_REQUIRED",
    "MAX_RETRIES",
    "CHANGES_REQUIRED",
    "FAILED",
    "CANCELLED",
}


@dataclass(frozen=True)
class Request:
    skill: str
    workflow: str | None
    verb: str
    target: str
    requirement: str = ""


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("invalid feature or run ID")
    return value


def parse_request(words):
    words = list(words)
    explicit = words.pop(0)[1:] if words and words[0].startswith("$") else None
    if len(words) < 3:
        raise ValueError("expected command, action and argument")
    group, verb, *args = words
    if group in {"dev", "pr", "spec", "issue"} and verb in {"status", "resume", "cancel"}:
        if len(args) != 1:
            raise ValueError("one existing Run ID required")
        skill = (
            explicit
            or {"dev": "cao-dev", "pr": "cao-pr-review", "spec": "cao-spec", "issue": "cao-issue"}[
                group
            ]
        )
        if skill not in SKILLS:
            raise ValueError("unknown skill")
        return Request(skill, None, verb, identifier(args[0]))
    if (group, verb) not in ROUTES:
        raise ValueError("unsupported command; merging is never supported")
    skill, workflow = ROUTES[(group, verb)]
    if explicit is not None and explicit != skill:
        raise ValueError("explicit skill does not match command")
    requirement = ""
    if group == "spec":
        if verb == "plan":
            target, requirement = "", " ".join(args).strip()
        else:
            target, requirement = identifier(args[0]), " ".join(args[1:]).strip()
        if not requirement or len(requirement.encode()) > 32000:
            raise ValueError("nonempty bounded requirement required")
    elif group in {"issue", "pr"}:
        if len(args) != 1 or not re.fullmatch(r"[1-9][0-9]{0,9}", args[0]):
            raise ValueError("positive Issue/PR number required")
        target = args[0]
    else:
        if len(args) != 1:
            raise ValueError("one feature required")
        target = identifier(args[0])
    return Request(skill, workflow, verb, target, requirement)


def project_root(path):
    root = subprocess.run(
        ["git", "-C", str(Path(path).expanduser()), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(root).resolve(strict=True)


def read_settings(root):
    path = root / ".cao/skills.json"
    if not path.exists():
        return {}
    if not path.resolve().is_relative_to(root):
        raise ValueError("settings escape project")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("settings must be an object")
    return value


class CaoError(RuntimeError):
    def __init__(self, message, *, transient=False, missing=False):
        super().__init__(message)
        self.transient = transient
        self.missing = missing


class Cao:
    def __init__(self, binary=None, *, env=None):
        self.binary = binary or os.environ.get("CAO_BIN") or shutil.which("cao")
        if not self.binary:
            raise CaoError("CAO not installed")
        self.env = dict(os.environ if env is None else env)

    def call(self, command, *args, read=True):
        if command not in {"get", "run", "status", "result", "resume", "cancel"}:
            raise ValueError("CAO operation not allowlisted")
        read = read and command in {"get", "status", "result"}
        argv = [self.binary, "workflow", command, *map(str, args)]
        if command != "cancel":
            argv.append("--json")
        # No automatic retry of submissions, resume or cancel. Only reads may retry.
        for attempt in range(3 if read else 1):
            try:
                proc = subprocess.run(
                    argv, capture_output=True, text=True, env=self.env, timeout=25 if read else 55
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                failure = CaoError(
                    type(error).__name__, transient=isinstance(error, subprocess.TimeoutExpired)
                )
            else:
                if (
                    proc.returncode == 0
                    or command in {"result", "resume"}
                    and proc.stdout.lstrip().startswith("{")
                ):
                    if command == "cancel":
                        return {"cancel_requested": True}
                    try:
                        return json.loads(proc.stdout)
                    except ValueError as error:
                        raise CaoError("invalid CAO JSON response") from error
                transient = bool(
                    re.search(
                        r"could not reach|Connection|timed out|timeout|status 50[234]",
                        proc.stderr,
                        re.I,
                    )
                )
                missing = bool(
                    re.search(
                        r"unknown run|unknown workflow|not found|status 404", proc.stderr, re.I
                    )
                )
                failure = CaoError(
                    "CAO request failed; inspect server/CLI configuration",
                    transient=transient,
                    missing=missing,
                )
            if not read or not failure.transient or attempt == 2:
                raise failure
            time.sleep(0.2 * (attempt + 1))
        raise AssertionError("unreachable")


def verify_executor(project, config):
    """Verify actual isolation before enabling any live agent invocation."""
    path = config.get("codex_config_path")
    if not path:
        raise ValueError("BLOCKED_ENVIRONMENT: dedicated codex_config_path required")
    codex_profiles_safe(path)
    if (project.root / ".codex/config.toml").exists():
        raise ValueError("BLOCKED_ENVIRONMENT: target Codex config needs audit")
    code = (
        "import os,socket; from pathlib import Path; "
        "assert not any(k in os.environ for k in ('GH_TOKEN','GITHUB_TOKEN','OPENAI_API_KEY')); "
        "assert not Path('/home').exists(); assert not os.access('.git',os.W_OK); "
        "s=socket.socket(); assert s.connect_ex(('1.1.1.1',443)) != 0"
    )
    proc = subprocess.run(
        isolated_argv(project, ["/usr/bin/python3", "-c", code]), capture_output=True, timeout=10
    )
    if proc.returncode:
        raise ValueError("BLOCKED_ENVIRONMENT: isolated executor probe failed")
    # Verify the actual installed Codex launcher can resolve both worker profiles
    # and establish its sandbox. A generic bwrap probe alone is not this evidence.
    codex = shutil.which("codex")
    if not codex:
        raise ValueError("BLOCKED_ENVIRONMENT: Codex executor not installed")
    native_code = """
import socket
try:
    socket.create_connection(('1.1.1.1',443),timeout=.2)
except OSError:
    pass
else:
    raise AssertionError('network escaped Codex executor')
"""
    env = {
        key: value
        for key, value in os.environ.items()
        if not re.search(r"(?i)(token|secret|password|credential|api_key)", key)
    }
    env["CODEX_HOME"] = str(Path(path).resolve().parent)
    for profile, permission in (
        ("cao-workflows-write", ":workspace"),
        ("cao-workflows-readonly", ":read-only"),
    ):
        probe = subprocess.run(
            [
                codex,
                "sandbox",
                "--permission-profile",
                permission,
                "--profile",
                profile,
                "--cd",
                str(project.root),
                "--",
                "/usr/bin/python3",
                "-c",
                native_code,
            ],
            env=env,
            capture_output=True,
            timeout=15,
        )
        if probe.returncode:
            raise ValueError("BLOCKED_ENVIRONMENT: Codex isolated executor/profile probe failed")


def resolve_repo(root):
    proc = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True
    )
    if proc.returncode:
        raise ValueError("GitHub origin required")
    remote = proc.stdout.strip()
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        remote,
    )
    if not match:
        raise ValueError("unambiguous GitHub origin required")
    return match[1]


class SkillRunner:
    def __init__(self, project, cao, *, endpoint=None, cao_home=None):
        self.root = project_root(project)
        self.cao = cao
        env = getattr(cao, "env", os.environ)
        self.cao_home = (
            Path(
                cao_home
                or env.get("CAO_HOME_DIR", str(Path.home() / ".aws/cli-agent-orchestrator"))
            )
            .expanduser()
            .resolve()
        )
        self.endpoint = endpoint or "http://" + env.get(
            "CAO_API_HOST", "127.0.0.1"
        ) + ":" + env.get("CAO_API_PORT", "9889")
        self.store = self.root / ".cao-runs/codex-skills"
        if not self.store.resolve().is_relative_to(self.root) or any(
            path.is_symlink() for path in (self.store, self.store.parent)
        ):
            raise ValueError("run registry must remain inside the current Git project")

    def save(self, record):
        atomic(
            safe(self.store, identifier(record["run_id"]) + ".json"),
            json.dumps(record, sort_keys=True, indent=2).encode(),
        )

    def load(self, run_id):
        record = json.loads(safe(self.store, identifier(run_id) + ".json").read_text())
        if (
            record["project"] != str(self.root)
            or record["endpoint"] != self.endpoint
            or record["cao_home"] != str(self.cao_home)
        ):
            raise ValueError(
                "Run ID project/server binding differs; use original project and server"
            )
        return record

    def summary(self, record, status, **extra):
        value = {k: record[k] for k in ("run_id", "workflow", "project", "feature")}
        value.update(
            status=status,
            cao_state=record.get("cao_state"),
            dry_run=record["inputs"]["dry_run"],
            next_action="Query this existing Run ID; do not submit a replacement",
            **extra,
        )
        validate(value, "codex-skill-result.schema.json")
        return json.loads(redact(json.dumps(value)))

    def prepare(self, request, settings, execute, authorized):
        feature = (
            request.target
            if request.workflow in {"development-orchestrator", "spec-update"}
            else settings.get("feature")
        )
        if request.workflow == "spec-planner" and not feature:
            feature = "001-" + hashlib.sha256(request.requirement.encode()).hexdigest()[:12]
        if not feature:
            raise ValueError("feature binding required in .cao/skills.json for Issue/PR workflows")
        project = Project(self.root, identifier(feature))
        if request.workflow == "development-orchestrator":
            verify(project)
        if request.workflow == "spec-update":
            project.specs()
        if request.workflow in {"spec-planner", "spec-update", "development-orchestrator"}:
            project.skills()
        inputs = {
            "project": str(self.root),
            "feature": feature,
            "dry_run": not execute,
            "authorized": authorized,
        }
        config = {}
        for key in ("config", "policy", "event"):
            if settings.get(key):
                path = Path(settings[key]).expanduser()
                path = (
                    (self.root / path).resolve(strict=True)
                    if not path.is_absolute()
                    else path.resolve(strict=True)
                )
                value = json.loads(path.read_text())
                if not isinstance(value, dict):
                    raise ValueError(key + " must be an object")
                inputs[key] = str(path)
                if key == "config":
                    config = value
        if request.requirement:
            inputs["requirement"] = request.requirement
        if request.workflow in {"pr-review", "pr-apply", "issue-orchestrator"}:
            repo = resolve_repo(self.root)
            policy = json.loads(Path(inputs["policy"]).read_text()) if "policy" in inputs else {}
            if policy.get("repo", repo) != repo or repo not in policy.get("repositories", []):
                raise ValueError("repository policy does not match current Git origin")
            if request.workflow == "issue-orchestrator":
                event = json.loads(Path(inputs["event"]).read_text()) if "event" in inputs else {}
                if (
                    event.get("repo") != repo
                    or event.get("issue_number") != int(request.target)
                    or intake(event, policy) != "PASS"
                ):
                    raise ValueError("HUMAN_REQUIRED: Issue receipt/eligibility mismatch")
            else:
                if policy.get("repo") != repo:
                    raise ValueError("PR workflow requires policy.repo binding")
                inputs["pr_number"] = int(request.target)
            if execute and not authorized:
                raise ValueError(
                    "explicit authorization required for GitHub publication/push/reply/resolve"
                )
        if execute:
            if request.workflow == "spec-update" and not authorized:
                raise ValueError("explicit human Spec change authorization required")
            verify_executor(project, config)
        return inputs

    def start(self, request, *, settings=None, execute=False, authorized=False, run_id=None):
        settings = read_settings(self.root) if settings is None else settings
        with lock(self.store):
            inputs = self.prepare(request, settings, execute, authorized)
            context_hash = (
                Project(self.root, inputs["feature"]).spec_hash()
                if request.workflow in {"development-orchestrator", "spec-update"}
                else None
            )
            fingerprints = {
                key: hashlib.sha256(Path(inputs[key]).read_bytes()).hexdigest()
                for key in ("config", "policy", "event")
                if key in inputs
            }
            identity = hashlib.sha256(
                json.dumps(
                    [
                        request.workflow,
                        str(self.root),
                        request.target or request.requirement,
                        inputs,
                        fingerprints,
                        context_hash,
                    ],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            if run_id and safe(self.store, identifier(run_id) + ".json").exists():
                raise ValueError("Run ID collision: inspect existing run")
            for path in self.store.glob("*.json"):
                record = json.loads(safe(self.store, path.name).read_text())
                if record["endpoint"] != self.endpoint:
                    continue
                if record["identity"] == identity:
                    return self.status(record["run_id"])
                if (
                    record["workflow"] == request.workflow
                    and record["feature"] == inputs["feature"]
                    and record["inputs"]["dry_run"] == inputs["dry_run"]
                    and record.get("subject") == (request.target or request.requirement)
                ):
                    previous = self.status(record["run_id"])
                    explicit_update = (
                        request.workflow == "spec-update"
                        and record.get("requirement") != request.requirement
                    )
                    reapproved = (
                        request.workflow == "development-orchestrator"
                        and record.get("context_hash") != context_hash
                    )
                    if (
                        previous["status"] == "DRY_RUN"
                        or previous["status"] in {"COMPLETED", "PASS", "HUMAN_REQUIRED"}
                        and (explicit_update or reapproved)
                    ):
                        continue
                    raise ValueError(
                        "existing feature run has different inputs; inspect/resume existing ID"
                    )
            run_id = identifier(run_id) if run_id else "cao-" + uuid.uuid4().hex
            try:
                self.cao.call("status", run_id)
            except CaoError as error:
                if not error.missing:
                    raise error
            else:
                raise ValueError("Run ID collision on CAO server")
            spec = self.cao.call("get", request.workflow)
            script = spec.get("mode") == "script" or str(spec.get("path", "")).endswith(".py")
            if spec.get("name") != request.workflow or not script:
                raise ValueError("unexpected CAO workflow contract")
            declarations = spec.get("inputs", {})
            for key, value in inputs.items():
                kind = (
                    "bool"
                    if isinstance(value, bool)
                    else "int"
                    if isinstance(value, int)
                    else "string"
                )
                if declarations.get(key, {}).get("type") != kind:
                    raise ValueError("unsupported Workflow INPUTS: " + key)
            for key, declaration in declarations.items():
                if declaration.get("required") and key not in inputs:
                    raise ValueError("missing required Workflow INPUTS: " + key)
            record = dict(
                run_id=run_id,
                workflow=request.workflow,
                project=str(self.root),
                feature=inputs["feature"],
                inputs=inputs,
                identity=identity,
                endpoint=self.endpoint,
                cao_home=str(self.cao_home),
                phase="SUBMITTING",
                fingerprints=fingerprints,
                context_hash=context_hash,
                subject=request.target or request.requirement,
                requirement=request.requirement,
            )
            # Freeze operator config/event/policy bytes for CAO's later execution and resume.
            for key in fingerprints:
                path = safe(self.store, run_id + "-" + key + ".snapshot")
                content = Path(inputs[key]).read_bytes()
                if hashlib.sha256(content).hexdigest() != fingerprints[key]:
                    raise ValueError("operator input changed during submission preflight")
                atomic(path, content)
                inputs[key] = str(path)
            self.save(record)  # Persist BEFORE submission, including the uncertainty window.
            argv = [request.workflow, "--run-id", run_id, "--detach"]
            for key, value in inputs.items():
                argv.extend(
                    [
                        "--input",
                        key + "=" + (str(value).lower() if isinstance(value, bool) else str(value)),
                    ]
                )
            try:
                submitted = self.cao.call("run", *argv, read=False)
                if submitted.get("run_id") != run_id:
                    raise CaoError("CAO returned a different Run ID")
                record["phase"] = "SUBMITTED"
            except CaoError:
                record["phase"] = "SUBMISSION_UNCERTAIN"
            self.save(record)
        return self.status(run_id)

    def status(self, run_id):
        record = self.load(run_id)
        try:
            snapshot = self.cao.call("status", run_id)
            if (
                snapshot.get("run_id") != run_id
                or snapshot.get("workflow_name", record["workflow"]) != record["workflow"]
            ):
                raise ValueError("CAO identity mismatch")
            state = str(snapshot.get("state", "")).upper()
            record["cao_state"] = state
            self.save(record)
            if state not in TERMINAL:
                return self.summary(
                    record, "RUNNING" if state in {"RUNNING", "PENDING", "NEW"} else "UNVERIFIED"
                )
            retained = self.cao.call("result", run_id)
        except CaoError as error:
            return self.summary(
                record, "SUBMISSION_UNCERTAIN" if error.missing else "CONNECTION_LOST"
            )
        return self.report(record, retained)

    def report(self, record, retained):
        state = str(retained.get("state", "")).upper()
        value = retained.get("output")
        if (
            retained.get("run_id") != record["run_id"]
            or retained.get("workflow_name") != record["workflow"]
        ):
            raise ValueError("retained result identity mismatch")
        result_source = "cao-result"
        if value is None:
            # The installed CAO retained script result omits emitted output.
            # Existing Workflow runtime also persists a contract-bound result.
            keys = [record["run_id"]]
            if record["workflow"] == "issue-orchestrator":
                event = json.loads(Path(record["inputs"]["event"]).read_text())
                keys.insert(0, f"{event['repo']}#{event['issue_number']}")
            for key in keys:
                path = (
                    self.cao_home
                    / "workflow-data"
                    / hashlib.sha256(key.encode()).hexdigest()[:20]
                    / "result.json"
                )
                if path.is_file() and path.resolve().is_relative_to(self.cao_home):
                    try:
                        value = json.loads(path.read_text())
                    except (OSError, ValueError):
                        return self.summary(record, "UNVERIFIED")
                    result_source = "workflow-owned-artifact"
                    break
        if not isinstance(value, dict):
            return self.summary(record, state if state in {"FAILED", "CANCELLED"} else "UNVERIFIED")
        try:
            validate_result(value)
        except ValueError:
            return self.summary(record, "UNVERIFIED")
        if value["run_id"] != record["run_id"]:
            return self.summary(record, "UNVERIFIED")
        status = value["status"]
        remote = {}
        if (
            record["workflow"] in {"pr-review", "pr-apply", "issue-orchestrator"}
            and not record["inputs"]["dry_run"]
            and status in {"PASS", "COMPLETED", "AWAITING_HUMAN_MERGE"}
        ):
            try:
                policy = json.loads(Path(record["inputs"]["policy"]).read_text())
                repo = resolve_repo(self.root)
                # Only the existing allowlisted READ operations can run here.
                api = GitHub(repo, dry_run=True, authorized=False, policy=policy)
                number = value.get("pr_number") or record["inputs"].get("pr_number")
                if (
                    policy.get("repo", repo) != repo
                    or value.get("repo") not in {None, repo}
                    or not number
                ):
                    raise ValueError("retained repository/PR binding mismatch")
                pr = api.pr(number)
                threads = api.threads(number)
                unresolved = sum(not thread["is_resolved"] for thread in threads)
                remote = {
                    "unresolved_thread_count": unresolved,
                    "pr_state": pr["state"],
                    "observed_head_sha": pr["head_sha"],
                }
                if pr["head_sha"] != value.get("head_sha"):
                    status = "HUMAN_REQUIRED"
                elif record["workflow"] != "pr-review" and (
                    unresolved
                    or not api.ci(number, pr["head_sha"], policy.get("required_checks", []))
                ):
                    status = "BLOCKED_ENVIRONMENT"
            except (OSError, ValueError, PermissionError, subprocess.SubprocessError):
                status = "UNVERIFIED"
        if state == "CANCELLED":
            status = "CANCELLED"
        elif state == "FAILED" and status not in BLOCKED:
            status = "FAILED"
        elif status in {"PASS", "COMPLETED", "AWAITING_HUMAN_MERGE"}:
            if state != "COMPLETED" or not completion_evidence(record["workflow"], value):
                status = "UNVERIFIED"
        tests = [item for item in objects(value["evidence"]) if "exit_code" in item]
        summary = self.summary(record, status)
        summary.update(
            result_source=result_source,
            next_action=value.get("next_action"),
            artifacts=value["artifacts"],
            evidence=value["evidence"],
            tests=tests,
            changed_files=sorted(
                {item["file"] for item in objects(value) if isinstance(item.get("file"), str)}
            ),
            threads=value.get("threads", []),
            head_sha=value.get("head_sha"),
            repo=value.get("repo"),
            pr_number=value.get("pr_number"),
            issue_number=value.get("issue_number"),
            unresolved_thread_count=None,
            changed_files_verified=False,
        )
        summary.update(remote)
        validate(summary, "codex-skill-result.schema.json")
        return json.loads(redact(json.dumps(summary)))

    def follow(self, run_id, *, polls=10, interval=2):
        if not 1 <= polls <= 100 or not 0 <= interval <= 5:
            raise ValueError("bounded polling required")
        value = None
        for attempt in range(polls):
            value = self.status(run_id)
            if value["status"] != "RUNNING":
                break
            if attempt + 1 < polls:
                time.sleep(interval)
        return value

    def resume(self, run_id):
        observed = self.status(run_id)
        if observed["status"] in {"CONNECTION_LOST", "SUBMISSION_UNCERTAIN", "UNVERIFIED"}:
            raise ValueError("cannot resume while current run state is uncertain")
        record = self.load(run_id)
        if record.get("cao_state") not in {"FAILED", "CANCELLED"}:
            raise ValueError(
                "resume only a known failed/cancelled run; never duplicate a running or uncertain submission"
            )
        for key, fingerprint in record.get("fingerprints", {}).items():
            if hashlib.sha256(Path(record["inputs"][key]).read_bytes()).hexdigest() != fingerprint:
                raise ValueError("frozen run inputs changed; human recovery required")
        if not record["inputs"]["dry_run"]:
            # Re-validate approval, immutable inputs and executor before replaying the same journal.
            project = Project(self.root, record["feature"])
            if record["workflow"] == "development-orchestrator":
                verify(project)
            config = json.loads(Path(record["inputs"]["config"]).read_text())
            verify_executor(project, config)
        try:
            self.cao.call("resume", run_id, read=False)
        except CaoError:
            return self.status(run_id)
        return self.status(run_id)

    def cancel(self, run_id):
        self.load(run_id)
        try:
            self.cao.call("cancel", run_id, read=False)
        except CaoError:
            return self.status(run_id)
        value = self.status(run_id)
        value["cancel_requested"] = True
        return value


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def completion_evidence(workflow, value):
    evidence = list(objects(value["evidence"]))
    if workflow in {"spec-planner", "spec-update"}:
        return len(value["artifacts"]) >= 3 and bool(evidence)
    if workflow == "pr-review":
        return any(
            item.get("status") == "PASS" and "findings" in item and item.get("head_sha")
            for item in evidence
        )
    gates = [item for item in evidence if "exit_code" in item and "argv" in item]
    # RED assertion failure is expected; final quality gates must prove GREEN.
    final_gates = {}
    for gate in gates:
        final_gates[json.dumps(gate["argv"], sort_keys=True)] = gate
    green = [
        item
        for item in final_gates.values()
        if item.get("exit_code") == 0 and item.get("errors") == [] and item.get("failures") == []
    ]
    if (
        len(green) != len(final_gates)
        or not any(item.get("tests", 0) > 0 for item in green)
        or len(green) < 3
    ):
        return False
    if workflow == "pr-apply":
        for thread in value.get("threads", []):
            try:
                validate(thread, "pr-apply-result.schema.json")
            except ValueError:
                return False
            if not (
                thread["resolution_status"] == "RESOLVED"
                and thread["github_is_resolved"] is True
                and thread["fix_commit_sha"] == value.get("head_sha")
                and thread["reply_comment_id"]
                and thread["test_evidence"]
            ):
                return False
        return bool(value.get("head_sha"))
    if workflow == "issue-orchestrator":
        return (
            value["status"] == "AWAITING_HUMAN_MERGE"
            and bool(value.get("pr_number"))
            and bool(value.get("head_sha"))
        )
    return any(item.get("review", {}).get("status") == "PASS" for item in evidence)


def validate_skills(source):
    values = []
    for name in SKILLS:
        text = (Path(source) / name / "SKILL.md").read_text()
        match = re.match(r"\A---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n", text)
        if not match or match[1] != name or len(match[2]) > 1024:
            raise ValueError("invalid skill metadata: " + name)
        # Our metadata uses JSON-quoted strings, a valid YAML scalar subset.
        # Reject syntactically invalid YAML without adding a runtime YAML dependency.
        description = json.loads(match[2])
        if not isinstance(description, str) or not description.strip():
            raise ValueError("nonempty skill description required")
        if not (Path(source) / name / "scripts/run.py").is_file():
            raise ValueError("missing skill runner: " + name)
        values.append(name)
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getcwd())
    parser.add_argument("--cao-bin")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--polls", type=int, default=10)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("command", nargs="+")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.polls <= 100 or not 0 <= args.interval <= 5:
            raise ValueError("bounded polling required")
        request = parse_request(args.command)
        runner = SkillRunner(args.project, Cao(args.cao_bin))
        if request.workflow:
            value = runner.start(
                request, execute=args.execute, authorized=args.authorize, run_id=args.run_id
            )
        else:
            value = getattr(runner, request.verb)(request.target)
        print(json.dumps(value, ensure_ascii=False), flush=True)
        if value["status"] == "RUNNING" and request.verb not in {"status", "cancel"}:
            value = runner.follow(value["run_id"], polls=args.polls, interval=args.interval)
            print(json.dumps(value, ensure_ascii=False), flush=True)
        return (
            1
            if value["status"]
            in BLOCKED | {"UNVERIFIED", "CONNECTION_LOST", "SUBMISSION_UNCERTAIN"}
            else 0
        )
    except (ValueError, OSError, CaoError, subprocess.SubprocessError) as error:
        status = "BLOCKED_SPEC" if "BLOCKED_SPEC" in str(error) else "BLOCKED_ENVIRONMENT"
        print(json.dumps({"status": status, "next_action": redact(str(error))}, ensure_ascii=False))
        return 1
