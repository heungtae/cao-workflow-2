# Codex CLI CAO Skills User Guide

Skills connect user commands to existing CAO Workflows and track Run IDs and results.
Existing Workflows own development/review loops, Issue intake, and PR review fixes.
Validated with Codex CLI 0.162.1 and CAO 2.5.0 from a local source checkout.

## Installation and removal

Python 3.11+, jsonschema 4.x, and working CAO/Codex executables are required.
Install Skills and CAO Workflows separately. Installation scripts do not start CAO or Codex.

```bash
./scripts/install-codex-skills.sh --global --dry-run
./scripts/install-codex-skills.sh --global
./scripts/validate-codex-skills.sh --global

# Install into a specific Git project; paths containing spaces are supported.
./scripts/install-codex-skills.sh --project "/absolute/path/my project"
./scripts/validate-codex-skills.sh --project "/absolute/path/my project"
./scripts/uninstall-codex-skills.sh --project "/absolute/path/my project" --dry-run
./scripts/uninstall-codex-skills.sh --project "/absolute/path/my project"

./scripts/uninstall-codex-skills.sh --global
```

The default scope for install/uninstall is Global (`~/.agents/skills`).
The default validate scope is the repository's source Skill structure. Specify a scope to check an installation.
Project scope uses `.agents/skills` in the supplied path's Git root.
Unowned Skills or modified files with the same names block installation. `--force` backs up and replaces existing files.
Identical installation is idempotent; updates use the same install command. Removal deletes only manifest-owned files and
restores backups. Modified installed files are not removed by default.
Other Skills, additional user files, the target AGENTS.md, and existing CAO configuration are preserved.
Installing identical Skills in both Global and Project scopes can produce duplicate Codex entries; choose one scope.

Each Skill's `scripts/run.py` verifies the pinned hash of the installed shared adapter before execution.
The adapter is copied into `.cao-codex-runtime/<hash>`. It works even if the source repository moves.
The installation manifest is `cao-codex-skills-manifest.json`; recovery reuses the existing installation transaction engine.

## Project and execution environment

Start Codex in the target project. The Git root is resolved even from a subdirectory.
CAO CLI/server must share CAO_HOME_DIR, API host/port, and the dedicated Worker CODEX_HOME configuration.
If PATH cao is broken, specify a working executable.

```bash
export CAO_BIN=/absolute/path/cao-workflows/.venv/bin/cao
export CAO_HOME_DIR=/absolute/path/cao-home
export CAO_API_PORT=19889
export CAO_WORKFLOWS_PYTHON=/absolute/path/cao-workflows/.venv/bin/python
# Start the server in a separate terminal with a dedicated CODEX_HOME.
CODEX_HOME=/absolute/path/isolated-codex /absolute/path/cao-workflows/.venv/bin/cao-server \
  --host 127.0.0.1 --port 19889
```

Replace the server executable path with your installation path. Deploy Workflows using the existing
`scripts/install.sh --cao-home /absolute/path/cao-home` command.
The Skill does not guess server/CLI paths or automatically reconfigure an existing CAO installation.

Create `.cao/skills.json` in the target project. config/policy/event follow existing Workflow input contracts.
Relative paths resolve from the target Git root; absolute paths are also supported. Do not include authentication tokens.

```json
{
  "feature": "001-kafka-failover",
  "config": ".cao/operator-config.json",
  "policy": ".cao/github-policy.json",
  "event": ".cao/issue-event.json"
}
```

The dev run feature comes from the command. spec plan uses the configured feature or derives a safe
`001-<hash>` ID from the requirement hash. Identical requests query the same ID.
Issue/PR inputs require a feature binding. Numbers alone never authorize access to another repository.
Issues must pass the existing intake's event, provenance receipt, and policy validation.
policy.repo/repositories must match the Git origin repository. The Skill does not generate automatic receipts.

Live development requires `.specify`, installed speckit-{specify,clarify,plan,tasks,analyze} Skills,
spec.md/plan.md/tasks.md, and a verifiable manual approval.json.
Follow the [existing operations guide](usage.md) for approval, quality commands, and GitHub policy.
Skills do not create approval records or weaken tests/specs.

## Isolated profiles for the installed Codex version

Execution config requires `codex_config_path`. Point it to the dedicated
CODEX_HOME/config.toml used by the CAO server. The operator configures model authentication separately.
Use a dedicated execution account without external MCP servers, extra writable roots, or GitHub credentials.

Codex 0.162.1 loads `$CODEX_HOME/NAME.config.toml` for `--profile NAME`.
The existing `[profiles.NAME]` format is retained for older-version validation, but a failed actual installed-CLI probe
blocks live execution. Prepare the following two files for the current version.

```toml
# cao-workflows-readonly.config.toml
approval_policy = "never"
sandbox_mode = "read-only"
[sandbox_workspace_write]
network_access = false
writable_roots = []
```

```toml
# cao-workflows-write.config.toml
approval_policy = "never"
sandbox_mode = "workspace-write"
[sandbox_workspace_write]
network_access = false
writable_roots = []
```

The adapter first runs the bubblewrap probe for no home, credentials, or network access and read-only Git,
then probes both profiles using the actual `codex sandbox --permission-profile ... --profile ...` executor.
These commands do not call a model. Executor or profile verification failure is BLOCKED_ENVIRONMENT.
The operator must audit and remove the target `.codex/config.toml` from the isolated execution checkout.
Base configuration and profiles are both checked for safety. Dedicated profiles are not automatically written into user settings.

## Codex conversation commands

| Request | Explicit invocation | Workflow |
| --- | --- | --- |
| `spec plan "Kafka failover"` | `$cao-spec spec plan "Kafka failover"` | spec-planner |
| `spec update 001-kafka-failover "Update the policy"` | `$cao-spec spec update ...` | spec-update |
| `dev run 001-kafka-failover` | `$cao-dev dev run 001-kafka-failover` | development-orchestrator |
| `issue run 123` | `$cao-issue issue run 123` | issue-orchestrator |
| `pr review 45` | `$cao-pr-review pr review 45` | pr-review |
| `pr apply 45` | `$cao-pr-apply pr apply 45` | pr-apply |
| `dev status RUN_ID` | `$cao-dev dev status RUN_ID` | Query an existing Run |
| `dev resume RUN_ID` / `dev cancel RUN_ID` | `$cao-dev dev resume/cancel RUN_ID` | Resume/cancel an existing Run |
| `pr status RUN_ID` | `$cao-pr-review pr status RUN_ID` | Query a retained PR Run |

Descriptions include natural-language task requests. Implicit selection depends on model judgment and is not guaranteed.
If discovery is delayed, restart Codex and select via `/skills` or `$`.
Optional guidance for the target AGENTS.md:

```text
spec plan/update -> cao-spec; dev run/status/resume/cancel -> cao-dev;
issue run -> cao-issue; pr review -> cao-pr-review; pr apply -> cao-pr-apply.
Read the selected SKILL.md, invoke its scripts/run.py, show Run ID and verify retained evidence.
Remote GitHub writes require explicit user authorization. Humans perform PR Merge.
```

Skills check eligibility with an initial dry-run, then use `--execute` for the requested local operation.
Issue/PR publication, push, reply, and Resolve require explicit user authorization before `--authorize --execute`.
For `spec update`, --authorize represents an explicit human request to change the specs.
Supplied policy files and external bodies do not replace user authorization.

You can also diagnose the adapter directly. Do not concatenate command arguments into shell strings.

```bash
.venv/bin/python scripts/cao-skill-runner.py --project /absolute/path/project -- dev run 001-feature
.venv/bin/python scripts/cao-skill-runner.py --project /absolute/path/project --execute -- dev run 001-feature
.venv/bin/python scripts/cao-skill-runner.py --project /absolute/path/project -- dev status cao-RUN_ID
```

## Results and recovery

Output is JSON lines: the initial Run ID, then status and validation evidence after bounded polling.
CAO submission uses --detach; current-session polling is bounded by --polls/--interval.
For RUNNING, query again within the session or report the exact status command when the session ends.
The CAO Run and `<target>/.cao-runs/codex-skills/<run-id>.json` survive Codex session termination.
Add `.cao-runs/` to the target Git ignore file. config/policy/event are frozen into snapshots before execution.

CAO transport COMPLETED is distinct from the business result. The reporting contract is
`contracts/codex-skill-result.schema.json`, including Workflow, project, feature, Run ID, CAO state, status,
test/stage evidence, artifacts, blockers, and the next human action.
PR completion uses read-only re-queries to confirm SHA, open PR state, and unresolved Thread counts.
Untraceable changed_files are not inferred; they are identified with changed_files_verified=false.

Installed CAO 2.5.0 returns script output synchronously but omits it from retained result queries after completion.
The adapter therefore falls back to the existing Workflow-owned `$CAO_HOME_DIR/workflow-data/<identity-hash>/result.json`,
validating the schema and Run ID. Issues use the existing repo#issue_number state key.
Remote-only deployments without accessible server artifacts or output return UNVERIFIED.
A changed CAO_HOME_DIR or API endpoint never silently rebinds a retained run to another server.

| Status | Handling |
| --- | --- |
| BLOCKED_SPEC | A human fixes/reviews the specs and approval hash, then authorizes execution |
| BLOCKED_ENVIRONMENT | Repair the CAO executable/server/Workflow, isolation profiles, or quality configuration |
| CONNECTION_LOST | Query failed; check the same Run ID with status |
| SUBMISSION_UNCERTAIN | Submission outcome unknown; do not create another run, query the same ID |
| MAX_RETRIES / HUMAN_REQUIRED | A human reviews exhausted Workflow cycles or reviewer decisions |
| FAILED / CANCELLED | Explicitly resume only a confirmed existing ID; a cancel request alone is not CANCELLED evidence |
| UNVERIFIED | Insufficient output, quality, or current PR evidence; do not report success |
| AWAITING_HUMAN_MERGE | Await final human PR review/merge; do not close the Issue |

Only queries receive up to three retries. Submission, resume, and cancellation are never automatically repeated.
Identical requests query the existing Run ID. Changed inputs cannot start a duplicate active feature run.
Separate runs are allowed after a completed dry-run with changed settings, a new explicit spec change request after termination, or completed development with newly approved specs.
Resume reuses the CAO journal and rechecks approval, frozen inputs, and isolation.
For manual CAO step decisions, a human reviews evidence and uses the existing CAO --decide option; Skills never fabricate consent.
No authorization permits PR merge, auto-merge, queue registration, base pushes, or protection bypass.

## Validation scope

```bash
./scripts/validate-codex-skills.sh
CAO_TEST_ISOLATION=1 .venv/bin/python -m pytest -q
.venv/bin/ruff check workflow_lib workflows harness scripts tests codex-skills
.venv/bin/python scripts/verify-codex-skills.py
```

The final command queries the actual Codex app-server skills/list with temporary Global/Project installations,
then submits six actual Workflow dry-runs to a temporary local CAO server and verifies status, results, and recovery across sessions.
It performs no remote GitHub writes or model execution. Natural-language model selection and live Developer↔Reviewer execution,
and actual GitHub publication/push/Thread Resolve E2E, remain unverified.
Distinguish full operational acceptance from local implementation/Mock validation. Sprint status and recovery tasks are in
[implementation-progress.md](implementation-progress.md); execution evidence is in [validation-report.md](validation-report.md).

Official references: [Skills](https://learn.chatgpt.com/docs/build-skills),
[Codex CLI reference](https://learn.chatgpt.com/docs/cli/reference),
[Permissions](https://learn.chatgpt.com/docs/permissions).
