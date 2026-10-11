# Optional Jira and PR trigger operation

Jira is a read-only input adapter for `spec-planner`; it never enters the CAO-generated GitHub Issue auto-development policy. Its fixed Jira Cloud v3 `GET /rest/api/3/issue/{key}` reads summary/description/project only, with host/project allowlists, bounded response/timeout and denied redirects. Credentials come from JIRA_EMAIL/JIRA_API_TOKEN and are not stored in bindings, prompts or logs. The generated specs still require human approval.

PR triggers support one-shot scheduling and authenticated localhost webhooks. GitHub HMAC-SHA256 is verified before parsing; other event types/closed events/forks are ignored or rejected. Repo/PR/SHA metadata is checked again through the read adapter before execution. Explicit execution prepares a clean detached latest-SHA worktree outside the source tree; no base branch is changed. A digest-bound run ID plus durable checkpoint prevents repeated submissions; an unknown submit response must reconcile CAO status before retry.

Operator binding example:

```json
{
  "project": "/absolute/path/project",
  "feature": "001-feature",
  "config": "/absolute/path/operator-config.json",
  "policy": "/absolute/path/policy.json",
  "state_file": "/absolute/path/operator-state/triggers.db",
  "worktree_root": "/absolute/path/operator-worktrees",
  "pr_numbers": [1],
  "jira_url": "https://tenant.atlassian.net",
  "jira_keys": ["APP-1"]
}
```

Policy adds `trigger_workflows: ["pr-review", "spec-planner"]`, `jira_hosts: ["tenant.atlassian.net"]`, `jira_projects: ["APP"]` and the existing repository/API operation policy. `allow_trigger_publication` is false unless explicitly enabled.

```bash
# One-shot read/preflight; safe to invoke from an operator-managed timer.
.venv/bin/python scripts/trigger.py --binding /absolute/path/binding.json
.venv/bin/python scripts/trigger.py --binding /absolute/path/binding.json --source jira
# Offline fixture preflight: no reads or submissions; execute is refused in this mode.
.venv/bin/python scripts/trigger.py --binding /absolute/path/binding.json --events-file /absolute/path/events.json
# Explicit prior authorization to launch read-only PR review/planning agents.
.venv/bin/python scripts/trigger.py --binding /absolute/path/binding.json --execute
# Webhook listener; secret must be configured in the environment.
.venv/bin/python scripts/trigger.py --binding /absolute/path/binding.json --serve --port 19890
```

The listener binds only 127.0.0.1. External delivery requires an operator-managed HTTPS proxy and GitHub webhook registration, neither of which is deployed automatically. `--serve` without `--execute` remains preflight only. To publish inline review comments, both `--execute --authorize-publication` and the GitHub operation/repository/publication policy are required. Jira submission can only plan; no trigger grants Merge/Issue Close privileges.

Schedule the one-shot command with your existing timer (for example every three minutes); this repository does not modify cron/systemd or expose a public port. A poll has a 100-event cap, finite timeouts, active-run exclusion and durable dedup. The CLI and adapters are fixture/Mock tested; live Jira credentials/webhook delivery are unqualified.

API sources: [Atlassian Jira Cloud v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro), [GitHub webhook validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).
