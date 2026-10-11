"""CAO entrypoint wiring. External writes remain explicit and policy-bound."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

from harness.quality_gate import QualityGate
from harness.reporters import report
from workflow_lib.agent import Agent, BudgetExceeded
from workflow_lib.approvals import approve, verify
from workflow_lib.contracts import result
from workflow_lib.dispatcher import planner, review
from workflow_lib.github_pr import GitHub
from workflow_lib.issue_intake import intake, verify_remote_issue
from workflow_lib.issue_state import Busy, Cancelled, State
from workflow_lib.orchestrators import development, issue
from workflow_lib.pr_create import Repository, create_pr, issue_worktree
from workflow_lib.project import Project
from workflow_lib.review import inline_review
from workflow_lib.review_threads import apply_threads
from workflow_lib.tdd import develop, tests_snapshot


def read_json(path, default=None):
    if not path:
        return {} if default is None else default
    return json.loads(Path(path).expanduser().resolve(strict=True).read_text())


def changed_files(project):
    proc = subprocess.run(
        ["git", "-C", str(project.root), "status", "--porcelain", "-z"],
        check=True,
        capture_output=True,
    )
    values = []
    for line in proc.stdout.decode().split("\0"):
        if not line:
            continue
        if line[:2].strip() in {"R", "C"}:
            raise ValueError("renames/copies require explicit manual review before staging")
        name = line[3:]
        if not name.startswith(".cao-runs/"):
            values.append(name)
    return values


def execute(name, inputs, *, runtime_home=None):
    run_id = os.environ.get("CAO_WORKFLOW_RUN_ID")
    if not run_id or not runtime_home:
        raise ValueError("CAO identity and installed runtime home required")
    home = Path(runtime_home).resolve()
    initial_dir = home / "workflow-data" / hashlib.sha256(run_id.encode()).hexdigest()[:20]
    try:
        project = Project(inputs["project"], inputs["feature"])
        config = read_json(inputs.get("config"))
        policy = read_json(inputs.get("policy"))
        event = read_json(inputs.get("event"))
    except (ValueError, OSError, KeyError) as error:
        value = result(
            "BLOCKED_ENVIRONMENT" if isinstance(error, OSError) else "FAILED",
            run_id=run_id,
            next_action="Preflight "
            + type(error).__name__
            + "; inspect target/config/artifact inputs",
        )
        report(initial_dir, value)
        return value
    dry_run = inputs.get("dry_run", True)
    authorized = inputs.get("authorized", False)
    key = (
        f"{event['repo']}#{event['issue_number']}"
        if name == "issue-orchestrator" and event
        else run_id
    )
    evidence_dir = home / "workflow-data" / hashlib.sha256(key.encode()).hexdigest()[:20]
    frozen = {
        "name": name,
        "inputs": inputs,
        "config": config,
        "policy": policy,
        "event": event,
        "run_id": run_id,
    }
    value = None
    try:
        with State(home / "workflow-data/state.db", key, frozen) as state:
            state.check()
            if name in {
                "spec-planner",
                "spec-plan",
                "spec-update",
                "development-orchestrator",
                "tdd-developer",
                "spec-tdd",
            }:
                project.skills()
            if dry_run:
                if name in {"spec-planner", "spec-plan", "spec-update"}:
                    project.skills()
                elif name in {"development-orchestrator", "tdd-developer", "spec-tdd"}:
                    verify(project)
                if name == "issue-orchestrator":
                    value = issue(event, policy, GitHub(event["repo"]), state, {}, dry_run=True)
                else:
                    value = result(
                        "DRY_RUN",
                        run_id=run_id,
                        next_action="Preflight passed; dry_run=false starts agents; writes require authorized=true",
                    )
            else:
                if name == "issue-orchestrator":
                    if not authorized:
                        raise PermissionError("Issue automation requires explicit authorization")
                    if intake(event, policy) != "PASS":
                        value = result(
                            "HUMAN_REQUIRED",
                            run_id=run_id,
                            next_action="Origin/risk policy rejected Issue",
                        )
                    else:
                        api = GitHub(event["repo"], dry_run=False, authorized=True, policy=policy)
                        if not policy.get("allow_feature_push", False):
                            raise PermissionError("feature branch push policy required")
                        verify_remote_issue(event, api)
                        root = config.get("worktree_root", str(home / "workflow-worktrees"))
                        path, branch = issue_worktree(project, event, run_id, root)
                        project = Project(str(path), inputs["feature"])
                        agent = Agent(
                            project,
                            state,
                            max_steps=int(policy.get("max_agent_steps", 40)),
                            max_text_bytes=int(policy.get("max_text_bytes", 2000000)),
                            max_cost=policy.get("max_cost"),
                            config_path=config.get("codex_config_path"),
                        )
                        gates = QualityGate(project, config["quality"], evidence_dir / "quality")
                        repository = Repository(
                            project, event["repo"], branch, policy.get("base", "main")
                        )

                        def plan():
                            value = planner(project, event["body"], agent)
                            if (
                                value["status"] == "HUMAN_REQUIRED"
                                and value["evidence"][0]["unresolved_risks"] == []
                            ):
                                value["status"] = "PASS"
                            return value

                        def spec_gate():
                            if intake(event, policy) != "PASS":
                                return result("HUMAN_REQUIRED")
                            text = "\n".join(project.specs().values())
                            if (
                                "HUMAN_REQUIRED" in text
                                or "BLOCKED_SPEC" in text
                                or "NEEDS CLARIFICATION" in text
                            ):
                                return result("BLOCKED_SPEC")
                            approve(project, event["origin_id"], "policy")
                            return result("PASS", spec_hash=project.spec_hash())

                        def do_create():
                            files = changed_files(project)
                            allowed = set(event["files"])
                            if any(
                                f not in allowed and not f.startswith(f"specs/{project.feature}/")
                                for f in files
                            ):
                                raise ValueError("Issue development exceeded declared file scope")
                            return create_pr(
                                api,
                                repository,
                                state,
                                "CAO Issue " + str(event["issue_number"]),
                                event["body"],
                                files,
                            )

                        def number():
                            return state.get("create")["pr_number"]

                        def pr_review():
                            return run_review(
                                project,
                                agent,
                                api,
                                number(),
                                publish=True,
                                step_id=f"pr-review-{state.get('current-cycle')}",
                            )

                        hooks = {
                            "plan": plan,
                            "spec_gate": spec_gate,
                            "develop": lambda: development(
                                project, agent, gates, allow_policy=True, state=state
                            ),
                            "create": do_create,
                            "reconcile_create": do_create,
                            "review": pr_review,
                            "apply": lambda: run_apply(
                                project,
                                agent,
                                api,
                                number(),
                                state,
                                gates,
                                repository,
                                policy["required_checks"],
                                f"cycle-{state.get('current-cycle')}",
                            ),
                        }
                        value = issue(event, policy, api, state, hooks, dry_run=False)
                else:
                    agent = Agent(
                        project,
                        state,
                        max_steps=config.get("max_agent_steps", 40),
                        max_text_bytes=config.get("max_text_bytes", 2000000),
                        max_cost=config.get("max_cost"),
                        config_path=config.get("codex_config_path"),
                    )
                    if name in {"spec-planner", "spec-plan", "spec-update"}:
                        if name == "spec-update" and not authorized:
                            raise PermissionError(
                                "spec-update requires explicit human change request/authorization"
                            )
                        before = project.snapshot()
                        value = planner(project, inputs.get("requirement", ""), agent)
                        after = project.snapshot()
                        changes = {
                            p for p in before.keys() | after.keys() if before.get(p) != after.get(p)
                        }
                        if any(not p.startswith(f"specs/{project.feature}/") for p in changes):
                            raise ValueError("planner wrote outside spec artifacts")
                    elif name == "spec-review":
                        reviewed = review(project, agent, "spec-review")
                        value = result(reviewed["status"], evidence=[reviewed])
                    elif name in {"development-orchestrator", "tdd-developer", "spec-tdd"}:
                        gates = QualityGate(project, config["quality"], evidence_dir / "quality")
                        value = (
                            development(
                                project,
                                agent,
                                gates,
                                max_cycles=inputs.get("max_cycles", 3),
                                state=state,
                            )
                            if name == "development-orchestrator"
                            else develop(project, agent, gates, state=state)
                        )
                    elif name in {"pr-create", "pr-review", "pr-apply"}:
                        repo = policy["repo"]
                        api = GitHub(repo, dry_run=False, authorized=authorized, policy=policy)
                        number = inputs.get("pr_number")
                        if name == "pr-review":
                            reviewed = run_review(
                                project, agent, api, number, publish=authorized, step_id="pr-review"
                            )
                            value = result(
                                reviewed["status"],
                                repo=repo,
                                pr_number=number,
                                head_sha=reviewed["head_sha"],
                                evidence=[reviewed],
                            )
                        else:
                            if not authorized:
                                raise PermissionError(
                                    "Git/PR mutations require explicit authorization"
                                )
                            if repo not in policy.get("repositories", []) or not policy.get(
                                "allow_feature_push", False
                            ):
                                raise PermissionError("repository/feature push policy required")
                            verify(project, allow_policy=True)
                            repository = Repository(
                                project, repo, config["branch"], policy.get("base", "main")
                            )
                            if name == "pr-create":
                                gates = QualityGate(
                                    project, config["quality"], evidence_dir / "quality"
                                )
                                values = gates("pre-pr")
                                if not all(v.passed for v in values) or values[0].tests < 1:
                                    value = result(
                                        "CHANGES_REQUIRED", evidence=[v.json() for v in values]
                                    )
                                else:
                                    created = create_pr(
                                        api,
                                        repository,
                                        state,
                                        config["title"],
                                        config.get("body", ""),
                                        changed_files(project),
                                    )
                                    value = result("PASS", repo=repo, **created)
                            else:
                                gates = QualityGate(
                                    project, config["quality"], evidence_dir / "quality"
                                )
                                value = run_apply(
                                    project,
                                    agent,
                                    api,
                                    number,
                                    state,
                                    gates,
                                    repository,
                                    policy["required_checks"],
                                    "manual-apply",
                                )
                    else:
                        raise ValueError("unknown workflow")
            value["run_id"] = run_id
            state.set_status(value["status"])
    except Cancelled:
        value = result("CANCELLED", run_id=run_id, next_action="Operator cancelled")
    except Busy:
        value = result(
            "HUMAN_REQUIRED", run_id=run_id, next_action="An active run already owns this identity"
        )
    except BudgetExceeded:
        value = result(
            "HUMAN_REQUIRED", run_id=run_id, next_action="Agent step/text budget exceeded"
        )
    except (PermissionError, OSError) as error:
        value = result(
            "BLOCKED_ENVIRONMENT",
            run_id=run_id,
            next_action=type(error).__name__ + "; inspect operator environment/permission",
        )
    except (ValueError, KeyError) as error:
        value = result(
            "BLOCKED_SPEC" if "BLOCKED_SPEC" in str(error) else "FAILED",
            run_id=run_id,
            next_action=str(error)[:500],
        )
    except Exception as error:
        value = result(
            "BLOCKED_ENVIRONMENT"
            if type(error).__module__.startswith("cao_workflow")
            else "FAILED",
            run_id=run_id,
            next_action=type(error).__name__ + "; inspect retained CAO step evidence",
        )
    report(evidence_dir, value)
    return value


def run_review(project, agent, api, number, *, publish, step_id):
    pr = api.pr(number)
    before = project.snapshot()
    local = subprocess.run(
        ["git", "-C", str(project.root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if local != pr["head_sha"] or changed_files(project):
        raise ValueError("PR review requires clean checkout of latest HEAD SHA")
    context = {
        "head_sha": pr["head_sha"],
        "diff_untrusted": api.call("diff", {"pr": number}),
        "threads_untrusted": api.threads(number),
        "checks": api.call("checks", {"pr": number, "sha": pr["head_sha"]}),
        "contract": read_json(
            Path(__file__).resolve().parent.parent / "contracts/review-result.schema.json"
        ),
    }
    output = agent("pr-reviewer", json.dumps(context, sort_keys=True), step_id)
    if project.snapshot() != before:
        raise ValueError("PR reviewer modified source")
    return inline_review(api, number, output, publish=publish)


def run_apply(project, agent, api, number, state, gates, repository, required, scope):
    frozen = project.spec_hash()
    protected = tests_snapshot(project)

    def fix(thread):
        value = agent(
            "pr-applier",
            json.dumps(
                {"thread_untrusted": thread, "head_sha": api.pr(number)["head_sha"]}, sort_keys=True
            ),
            scope + "-fix-" + hashlib.sha256(thread["thread_id"].encode()).hexdigest()[:12],
        )
        if frozen != project.spec_hash() or any(
            tests_snapshot(project).get(p) != h for p, h in protected.items()
        ):
            raise ValueError("BLOCKED_SPEC: PR apply changed specs or existing tests")
        return value

    def quality():
        values = gates(scope + "-apply")
        if frozen != project.spec_hash() or any(
            tests_snapshot(project).get(p) != h for p, h in protected.items()
        ):
            raise ValueError("quality command changed specs/tests")
        return [v.json() for v in values]

    def push(expected):
        files = changed_files(project)
        if not files:
            raise ValueError("no verified code/test changes to push")
        return repository.commit_push(files, "fix " + scope, expected_remote=expected)

    return apply_threads(
        api, number, state, fix, quality, push, required_checks=required, scope=scope
    )
