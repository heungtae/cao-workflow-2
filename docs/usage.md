# Usage

## Agent containment

Use a **dedicated Codex home/account for the CAO server**, with no GitHub credentials, external MCP servers or extra writable roots. Do not point it at your unrestricted interactive configuration. Provide Codex authentication using your approved operational procedure. This repository does not overwrite user auth/config.

Create these named profiles in that dedicated `CODEX_HOME/config.toml`. Start the CAO server with that CODEX_HOME, and pass its absolute config path through operator config `codex_config_path` (CAO does not forward CODEX_HOME into script processes):

The following profile-table example applies to older Codex releases. The installed Codex 0.162.1
loads `cao-workflows-readonly.config.toml` and `cao-workflows-write.config.toml` from CODEX_HOME
for `--profile`. Use the [current profile-file setup](codex-skills.md#isolated-profiles-for-the-installed-codex-version)
for this version; the Skills runner tests both actual native executors before enabling live work.

```toml
[profiles.cao-workflows-readonly]
approval_policy = "never"
sandbox_mode = "read-only"

[profiles.cao-workflows-write]
approval_policy = "never"
sandbox_mode = "workspace-write"
[profiles.cao-workflows-write.sandbox_workspace_write]
network_access = false
writable_roots = []
```

Agent profiles select these names and also pass explicit sandbox/no-network/web-search-disabled overrides. A missing/unsafe config fails closed. Target `.codex/config.toml` must be audited and removed from the isolated execution checkout to avoid inherited capabilities. Use separate operational credentials for the trusted workflow GitHub adapter. CAO tool allowlists alone are not a Codex security boundary.

## Target quality configuration

The operator supplies a JSON file via `--input config=/absolute/path/config.json`. Issue/comment text never defines commands. Every mandatory gate is an argv array, with an explicit test JUnit report or glob. Commands execute inside bubblewrap; no host home or network is exposed. Dependencies must be installed/cached before execution. Optional `readonly_roots` mounts are operator-approved tool/dependency directories, and must contain no credentials.

```json
{
  "codex_config_path": "/absolute/path/to/isolated-codex/config.toml",
  "quality": {
    "test": {"argv": [".venv/bin/python", "-m", "pytest", "--junitxml=.cao-runs/junit.xml"], "junit": ".cao-runs/junit.xml"},
    "static": {"argv": [".venv/bin/ruff", "check", "."]},
    "coverage": {"argv": [".venv/bin/python", "-m", "pytest", "--cov=app", "--cov-fail-under=85"]},
    "max_green_attempts": 3,
    "timeout_seconds": 300
  },
  "max_agent_steps": 40,
  "max_text_bytes": 2000000
}
```

Coverage thresholds are project policy, not repository defaults. Install pytest-cov in the target before using this example. Add `.cao-runs/` and generated reports/build directories to the target Git ignore file. RED expected failures use JUnit identity `classname::name` when classname is present; no skipped-only suite counts as a success. Reports archive each phase's XML/log/command/exit code.

Workflow result JSON/Markdown and SQLite state are under `$CAO_HOME_DIR/workflow-data/`. Human approval requires specs committed in Git, and binds their commit/content hash. Any missing/changed artifact, approval mutation or unresolved high-risk condition blocks development. Reviewer loops do not change specs.

## Issue execution policy

An operator-owned policy binds the exact trusted origin receipt (`event_digest` canonical SHA256), author, repository, event ID, low-risk declaration and allowed files. A label is insufficient. The remote Issue must still be open, with matching author/body. Sensitive scope always requires a human.

```json
{
  "repo": "owner/repo",
  "repositories": ["owner/repo"],
  "trusted_authors": ["cao-bot"],
  "origins": {"origin-1": {"event_id": "event-1", "digest": "CANONICAL_EVENT_SHA256"}},
  "auto_low_risk": true,
  "allowed_files": ["app.py", "tests/test_app.py"],
  "base": "main",
  "allow_feature_push": true,
  "github_operations": ["create_pr", "create_review", "reply", "resolve"],
  "required_checks": ["test", "lint"],
  "max_pr_cycles": 3,
  "max_agent_steps": 40,
  "max_text_bytes": 2000000
}
```

`contracts/issue-event.schema.json` defines the event. Compute its digest with `workflow_lib.issue_intake.event_digest` in the trusted intake process; changing event content invalidates the receipt. GitHub/Issue automation is opt-in, and production policies must reflect all required CI contexts. Exact currency/usage metering is not available through this installed shim; text bytes/step count/time/cycle limits are enforced. Setting `max_cost` blocks Agent execution before any request, instead of declaring an unobservable monetary budget verified.

Invoke `issue-orchestrator` with project/feature/config/event/policy absolute paths. Default dry run creates no worktree or PR. An authorized execution uses `dry_run=false authorized=true`, creates a separate `cao/issue-*` worktree and never changes/pushes the source base branch. Only declared implementation/test files and feature specs may be committed. There is one active state key `owner/repo#ISSUE_NUMBER`; resume must keep the same run ID and input/policy digests.

For standalone PR workflows, `policy.repo`, `config.branch`, policy base/required checks and a clean latest-HEAD checkout are required. `pr-create` additionally needs config title/body. `pr-review` with `authorized=false` writes only its local result. `pr-apply` requires authorization, quality config and the exact owned branch; unresolved outdated/disputed threads block. Existing tests cannot be weakened; new regression tests may be added. Reply/Resolve happen only after verified commit, local gates and required CI. CI delay produces BLOCKED_ENVIRONMENT and can be resumed without another push or duplicate reply.

## Status, cancellation and recovery

```bash
.venv/bin/python scripts/cli.py status --key 'owner/repo#1'
.venv/bin/python scripts/cli.py cancel --key 'owner/repo#1'
```

CAO lifecycle `status/result/cancel/resume` operates on the CAO run ID. Workflow-owned cancellation is checked between operations; in-flight Agent calls or commands have finite timeouts. SQLite and CAO journals are distinct evidence stores. Preserve both. Completed external writes are reused. Unknown-completion writes are reconciled by PR/commit/thread markers or blocked for operator investigation. A cancelled identity is intentionally not automatically resumed.

## Parallel API

`workflow_lib.parallel.isolated_fanout` accepts tasks `{id,depends,files}`, validates a DAG and disjoint ownership per parallel layer, creates detached worktrees and checkpoints results. Dependency commits are cherry-picked only into downstream detached worktrees; the original/base checkout is never modified. Conflicts or undeclared writes stop the DAG. The API returns isolated commits for human integration; no merge or automatic base integration is performed. Keep stable run IDs/task catalogs and retain its state/worktree directory for recovery.

Installer backups and pending-transaction recovery are manifest-owned. Old immutable dependency bundles are retained for resumed runs; uninstall only after active/resumable runs are no longer needed. Version upgrades that remove non-bundle resources require uninstall first, so old resources never become silently unowned.

GREEN correction attempts are capped at 1..5 (default 3 for configured QualityGate workflows). Each retry receives failed-command evidence, has a stable distinct step ID/log/checkpoint, and preserves all protected tests/specs. Timeouts/missing executable stop for environment repair; exhausted attempts never advance to refactor/review/completion.
