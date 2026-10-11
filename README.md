# CAO Workflows

Reusable CAO Python workflows for Spec Kit planning, approved-spec TDD, independent review, and policy-bound GitHub Issue/PR automation. Automation stops at `AWAITING_HUMAN_MERGE`. Humans merge PRs and close Issues.

## Codex CLI Skills

Five Skills connect Codex requests to existing Workflows and track durable Run IDs, bounded
query recovery, cancellation/resume and contract-validated business results.
Install globally or into a target Git project:

```bash
./scripts/install-codex-skills.sh --global
./scripts/validate-codex-skills.sh --global
# Alternative: --project /absolute/path/to/project
```

In the target project's Codex conversation: `spec plan "requirements"`,
`dev run 001-feature`, `issue run 123`, `pr review 45`, `pr apply 45`.
Explicit invocation is also supported: `$cao-dev dev run 001-feature`.
Use `dev status RUN_ID` after a session restart. CAO/server configuration, approved specs and
operator config must be ready; GitHub writes require explicit authorization.
See [the Skills guide](docs/codex-skills.md) for setup, current Codex profile files, updates,
safe uninstall, command examples and troubleshooting.

Actual Codex discovery, native sandbox probes and CAO dry-run submissions are tested locally.
Model selection and live Agent/GitHub execution through Skills remain unverified;
see [sprint evidence](docs/validation-report.md) and [remaining work](docs/implementation-progress.md).

## Five-minute local verification

Python 3.11+, a compatible CAO 2.5.0 install, `gh`, Git and Linux bubblewrap are required for live use. Validation needs a local CAO server. Existing CAO configuration is preserved.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'cli-agent-orchestrator==2.5.0' 'jsonschema>=4.19,<5' 'pytest>=8,<10' 'ruff>=0.9,<1'
# Full local gate: temporary server/home, Mock GitHub, no Agent execution.
.venv/bin/python scripts/verify-local.py
```

This build was validated against CAO 2.5.0 **from a local source checkout**, rather than independently qualifying the PyPI wheel. To reproduce that exact environment, replace the CAO package argument with your compatible source checkout path. See [versions](docs/versions.md).

## Install and lifecycle

Start your CAO server using its verified `--host`/`--port` options, with the same `CAO_HOME_DIR` as the CLI. Select `CAO_BIN` if your PATH installation is broken. For a temporary example:

```bash
export CAO_HOME_DIR=/tmp/my-cao-workflows
export CAO_API_PORT=19889
# Separate terminal:
.venv/bin/cao-server --host 127.0.0.1 --port 19889

./scripts/doctor.sh
./scripts/install.sh --dry-run
./scripts/install.sh
./scripts/validate.sh
# The target must already be a Git root with real Spec Kit skills installed.
.venv/bin/cao workflow run spec-planner --run-id plan-001 \
  --input project=/absolute/path/to/project --input feature=001-feature \
  --input requirement='Describe the requested feature' --input dry_run=true
.venv/bin/cao workflow status plan-001
.venv/bin/cao workflow result plan-001
./scripts/uninstall.sh --dry-run
./scripts/uninstall.sh
```

Dry run performs preflight without Agent or GitHub writes. `dry_run=false` starts Agents; configure the isolated Codex profiles described in [usage](docs/usage.md) first. GitHub mutations additionally require `authorized=true` and an operation/repository/feature-push policy. No such authorization can grant merge capabilities.

For manual development, run planning, review and commit `spec.md`, `plan.md`, `tasks.md`, then explicitly approve their hash:

```bash
.venv/bin/python scripts/cli.py approve-spec --project /absolute/path/to/project \
  --feature 001-feature --actor your-name
.venv/bin/cao workflow run development-orchestrator --run-id dev-001 \
  --input project=/absolute/path/to/project --input feature=001-feature \
  --input config=/absolute/path/to/operator-config.json --input dry_run=false
.venv/bin/cao workflow cancel dev-001
.venv/bin/cao workflow resume dev-001
```

Resume can halt for manual recovery of an uncertain writing step; actual CLI supports `--decide STEP_ID=rerun|skip`. Reconcile filesystem/GitHub evidence first. Workflow-owned `status` and cooperative `cancel` are also available through `scripts/cli.py`; see usage for Issue identity keys.

## Workflows

| Entry | Responsibility |
|---|---|
| spec-planner / spec-plan | Installed Spec Kit skills → spec/plan/tasks → independent review; ends for approval |
| spec-update | Explicit human request to update specs; never starts development |
| tdd-developer / spec-tdd | Separate Test Agent RED → Developer GREEN/refactor → real configured quality gates |
| development-orchestrator | Approved-spec TDD ↔ independent Spec Reviewer, bounded cycles |
| spec-review | Read-only spec/test/code findings |
| issue-orchestrator | Trusted Issue intake → plan/policy → development → draft PR → review/apply loop |
| pr-create | Exact owned feature branch commit/push and reusable draft PR |
| pr-review | Latest SHA/diff/CI review and authorized inline comments |
| pr-apply | Unresolved threads → fixes → tests → push → CI → reply → confirmed Resolve |

[Validation report](docs/validation-report.md) records sprint gates, evidence and qualification limits. [Architecture](docs/architecture.md), [usage](docs/usage.md), [troubleshooting](docs/troubleshooting.md), and [Java example](examples/java-spring-kafka/README.md) provide operational details.

Optional [Jira inputs and PR webhook/timer triggers](docs/triggers.md) are implemented with separate authentication, explicit execution policy and durable deduplication. Their default mode is preflight; no timer, public listener or external integration is enabled by installation.

The explicitly authorized disposable [GitHub live test](docs/github-live-validation.md) verifies real draft PR creation, two inline comment/fix/reply/Resolve cycles and actual CI continuation. Provider Agent execution remains separately unverified.
