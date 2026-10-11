# CAO Workflows

Reusable CAO Workflows for Spec Kit planning, approved-spec TDD, independent review, and GitHub Issue/PR processing. Five Codex CLI Skills connect user requests to existing Workflows and track Run IDs, execution status, and completion evidence.

Install in this order: **prepare the execution environment → start the CAO server → install Workflows → install Codex Skills → configure the target project**. Use the system in this order: **plan specs → human review and approval → development → verify results**.

Humans merge PRs and close Issues. Automation stops at `AWAITING_HUMAN_MERGE`; merge, auto-merge, merge queue, base/protected branch pushes, and protection bypass are prohibited. Remote GitHub changes require explicit user authorization.

## 1. Prepare the execution environment

Required tools: Python 3.11+, Git, Codex CLI, compatible CAO 2.5.0, GitHub CLI (`gh`), and Linux bubblewrap (`bwrap`). Live Agent execution also requires a verified isolated executor and separate Codex authentication.

Run the following commands from this repository's root. Replace example absolute paths with your own paths.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install \
  /absolute/path/to/cli-agent-orchestrator \
  'jsonschema>=4.19,<5' 'pytest>=8,<10' 'ruff>=0.9,<1' 'PyYAML>=6,<7'

export WORKFLOW_ROOT="$(pwd)"
export TARGET_PROJECT=/absolute/path/to/development-project
export CAO_BIN="$WORKFLOW_ROOT/.venv/bin/cao"
export CAO_WORKFLOWS_PYTHON="$WORKFLOW_ROOT/.venv/bin/python"
export CAO_HOME_DIR=/absolute/path/to/cao-home
export CAO_API_HOST=127.0.0.1
export CAO_API_PORT=19889
export WORKER_CODEX_HOME=/absolute/path/to/isolated-codex
```

The validated environment used **CAO 2.5.0 from a local source checkout and Codex CLI 0.162.1**. You may replace the source checkout argument with `cli-agent-orchestrator==2.5.0`, but the PyPI distribution was not independently qualified. If your existing CAO works, keep it and point `CAO_BIN` to its executable. See [verified versions and interfaces](docs/versions.md).

Keep the CAO Worker Codex environment separate from interactive Codex. Prepare `config.toml`, model authentication, and the following two profiles in `$WORKER_CODEX_HOME`. Use a dedicated execution account without GitHub credentials, external MCP servers, or extra writable roots.

| File | Settings |
| --- | --- |
| `cao-workflows-readonly.config.toml` | `approval_policy="never"`, `sandbox_mode="read-only"`, network disabled |
| `cao-workflows-write.config.toml` | `approval_policy="never"`, `sandbox_mode="workspace-write"`, network disabled |

Installation scripts do not create or overwrite user authentication or configuration. Follow the [Skills guide](docs/codex-skills.md#isolated-profiles-for-the-installed-codex-version) for **profile file contents and isolation settings** for the validated Codex version. Failed executor verification blocks Agent execution.

## 2. Start the CAO server and install Workflows

Set the same environment variables in a separate terminal and start the server. The server and CLI must share `CAO_HOME_DIR`, host, and port. Set the Worker `CODEX_HOME` for the server process.

```bash
CODEX_HOME="$WORKER_CODEX_HOME" "$WORKFLOW_ROOT/.venv/bin/cao-server" \
  --host "$CAO_API_HOST" --port "$CAO_API_PORT"
```

From the repository root in the first terminal, check the environment, preview installation, install, and validate in order. Workflow validation requires a running CAO server.

```bash
CODEX_HOME="$WORKER_CODEX_HOME" ./scripts/doctor.sh --cao-home "$CAO_HOME_DIR"
./scripts/install.sh --cao-home "$CAO_HOME_DIR" --dry-run
./scripts/install.sh --cao-home "$CAO_HOME_DIR"
./scripts/validate.sh --cao-home "$CAO_HOME_DIR"
```

Check `cao_cli_ok` and `agent_config_ready` in the `doctor` output. These values do not verify model authentication or live Agent execution. Workflows and Agent profiles are installed into the selected CAO home; a manifest tracks ownership and backups.

## 3. Install Codex Skills

Workflow installation and Skill installation are separate. **Choose either Global or Project scope**. Neither installer starts the server or a Codex session automatically.

Global installation uses `~/.agents/skills/` and is available across projects.

```bash
./scripts/install-codex-skills.sh --global --dry-run
./scripts/install-codex-skills.sh --global
./scripts/validate-codex-skills.sh --global
```

Project installation uses the target Git project's `.agents/skills/` directory.

```bash
./scripts/install-codex-skills.sh --project "$TARGET_PROJECT" --dry-run
./scripts/install-codex-skills.sh --project "$TARGET_PROJECT"
./scripts/validate-codex-skills.sh --project "$TARGET_PROJECT"
```

Installation stops on conflicts with an existing Skill of the same name or a modified owned file. Identical installation is idempotent; use the same command for updates. `--force` backs up and replaces existing files, so use it only after inspecting conflicts. Other Skills and the target project's `AGENTS.md` are preserved.

## 4. Configure the target development project

This repository deploys Workflows; `$TARGET_PROJECT` is the **existing Git root** where application code is developed. Prepare the following before planning or development.

1. Initialize Spec Kit to create `.specify/`.
2. Install real `speckit-specify`, `speckit-clarify`, `speckit-plan`, `speckit-tasks`, and `speckit-analyze` Skills in the target project's `.agents/skills/` or `.claude/skills/`. CAO Skills do not install Spec Kit for you.
3. Set `codex_config_path` in `.cao/operator-config.json` to the **actual absolute path** of `$WORKER_CODEX_HOME/config.toml`, and configure the target's test, static-analysis, and coverage commands. Commands are argv arrays; required tests must produce JUnit evidence. Follow the [operator configuration example](docs/usage.md#target-quality-configuration).
4. Install or cache dependencies before testing in the environment with networking disabled. Add `.cao-runs/`, generated reports, and build directories to the target Git ignore file.
5. Bind the Feature and configuration file in the target project's `.cao/skills.json`.

```json
{
  "feature": "001-kafka-failover",
  "config": ".cao/operator-config.json"
}
```

Relative configuration paths resolve from the target Git root. `spec plan` uses the configured Feature or generates an ID from the requirement hash when absent. `dev run` uses the Feature in the command.

For Issue/PR commands, add a `policy` path to `.cao/skills.json`; Issue processing also needs an `event` path. Policy must bind the Git origin repository, allowed operations, owned Feature branch, and required CI. Issues must pass trusted provenance receipt verification. Follow the [Issue/PR operational policy](docs/usage.md#issue-execution-policy). Do not put authentication tokens in configuration files.

## 5. Plan specs, approve, and develop in Codex

In a terminal with the CAO environment variables set, switch to the target project and start Codex. You do not need to set the Worker `CODEX_HOME` for this interactive session.

```bash
cd "$TARGET_PROJECT"
codex
```

Enter the following in the Codex conversation. If implicit selection does not work, use explicit invocation such as `$cao-spec`. If discovery is delayed after installation, check in a fresh Codex session.

```text
spec plan "Plan automatic failover requirements for Kafka failures"
# Explicit invocation: $cao-spec spec plan "Plan automatic failover requirements for Kafka failures"
```

A human reviews the generated `specs/001-kafka-failover/{spec.md,plan.md,tasks.md}` and commits the three files in the target project. After resolving outstanding risks or changes, **the approver personally** creates the approval record.

```bash
"$CAO_WORKFLOWS_PYTHON" "$WORKFLOW_ROOT/scripts/cli.py" approve-spec \
  --project "$TARGET_PROJECT" --feature 001-kafka-failover --actor your-name
```

This command creates `approval.json` bound to the spec commit/content hash. Spec changes require another review, commit, and approval. The Skill does not create human approval on the user's behalf.

Request development in the target project's Codex conversation.

```text
dev run 001-kafka-failover
# Explicit invocation: $cao-dev dev run 001-kafka-failover
```

The Skill validates inputs, approval, CAO, and the isolated executor before submitting the Workflow and reporting its Run ID. `development-orchestrator` owns the Developer ↔ Reviewer loop. `DRY_RUN` is preflight evidence, not live development completion.

| Codex conversation command | Skill | Workflow |
| --- | --- | --- |
| `spec plan "requirements"` | `$cao-spec` | spec-planner |
| `spec update 001-feature "change request"` | `$cao-spec` | spec-update |
| `dev run 001-feature` | `$cao-dev` | development-orchestrator |
| `issue run 123` | `$cao-issue` | issue-orchestrator |
| `pr review 45` | `$cao-pr-review` | pr-review |
| `pr apply 45` | `$cao-pr-apply` | pr-apply |

Remote changes such as Issue creation, PR creation, comments, pushes, replies, and Thread Resolve require user authorization for the concrete repository and operation. `cao-pr-apply` handles review fixes, verification, replies, and Thread Resolve; it does not merge PRs. See [all commands and direct adapter invocation](docs/codex-skills.md#codex-conversation-commands).

## 6. Check execution status and recover

Use the reported Run ID in the **original target project and CAO server**. The following are Codex conversation commands.

```text
dev status RUN_ID
dev resume RUN_ID
dev cancel RUN_ID
pr status RUN_ID
```

Use `resume` to continue an existing failed or cancelled run. If the connection is lost or submission outcome is uncertain, query `status` for the same Run ID first. Do not submit a duplicate Workflow. Only query errors receive bounded retries; submission, resume, and cancellation are not automatically repeated.

The CAO run and the target project's `.cao-runs/codex-skills/<run-id>.json` survive Codex session termination. The current session polls a bounded number of times; it does not run as a resident monitor. Check the CAO `COMPLETED` state together with business results and verification evidence; insufficient evidence is reported as `UNVERIFIED`. Retry exhaustion, Human Review, and uncertain write steps require human evidence review.

You can also query CAO status and results from a terminal.

```bash
"$CAO_BIN" workflow status RUN_ID
"$CAO_BIN" workflow result RUN_ID
```

Preserve both the CAO journal and business results in `$CAO_HOME_DIR/workflow-data/`. Follow the [recovery guide](docs/usage.md#status-cancellation-and-recovery) for cancellation, resume, and manual step decisions, and [Skills results and recovery](docs/codex-skills.md#results-and-recovery) for error handling.

## 7. Local validation and current qualification

Run the following from the Workflow repository root.

```bash
cd "$WORKFLOW_ROOT"
./scripts/validate-codex-skills.sh
CAO_TEST_ISOLATION=1 .venv/bin/python -m pytest -q
.venv/bin/ruff check workflow_lib workflows harness scripts tests codex-skills
.venv/bin/python scripts/verify-local.py
.venv/bin/python scripts/verify-codex-skills.py
```

Integration validation uses temporary CAO homes, servers, and installation directories. It runs no live models or remote GitHub writes and generates validation artifacts such as server logs.

The recorded local suite passed **116 tests + 29 subtests**. Actual Codex Global/Project Skill discovery, isolation probes, six CAO Workflow dry-run submissions, and status queries across sessions were verified. **Actual model selection from natural language and live Planner/Developer/Reviewer and GitHub E2E remain unverified**. The earlier, separately authorized [GitHub adapter live test](docs/github-live-validation.md) is distinct from model execution through these Skills. See the [validation report](docs/validation-report.md) and [Sprint progress and remaining work](docs/implementation-progress.md).

## 8. Update and uninstall

For updates, rerun installation and validation for the same scope. Inspect conflicts if you edited installed owned files. Keep CAO Workflows and execution evidence while resumable runs remain.

If you installed Global Skills, uninstall in this order.

```bash
./scripts/uninstall-codex-skills.sh --global --dry-run
./scripts/uninstall-codex-skills.sh --global
```

For Project Skills, replace `--global` in the two commands above with `--project "$TARGET_PROJECT"`. Uninstallation removes only manifest-owned files, restores backups, and preserves other Skills. Uninstall CAO Workflows separately.

```bash
./scripts/uninstall.sh --cao-home "$CAO_HOME_DIR" --dry-run
./scripts/uninstall.sh --cao-home "$CAO_HOME_DIR"
```

## Workflows and detailed documentation

| Workflow | Responsibility |
| --- | --- |
| spec-planner / spec-plan | Installed Spec Kit Skills → spec/plan/tasks → independent review; ends for human approval |
| spec-update | Process explicit spec change requests |
| tdd-developer / spec-tdd | Separate Test Agent RED → Developer GREEN/refactor → configured quality gates |
| development-orchestrator | Approved-spec TDD ↔ independent Spec Reviewer, bounded cycles |
| spec-review | Read-only spec/test/code review |
| issue-orchestrator | Trusted Issue intake → planning/policy → development → draft PR → review/apply loop |
| pr-create | Owned Feature branch commit/push and reusable draft PR |
| pr-review | Latest SHA/diff/CI review and authorized inline comments |
| pr-apply | Unresolved Thread fixes → tests → push → CI → reply → confirmed Resolve |

See [architecture](docs/architecture.md), [operator configuration](docs/usage.md), [troubleshooting](docs/troubleshooting.md), and the [Java example](examples/java-spring-kafka/README.md). Optional [Jira inputs and PR webhook/timer triggers](docs/triggers.md) use separate authentication, execution policy, and deduplication. Installation alone enables no timer, public listener, or external integration.
