# Architecture

Python Workflow entrypoints contain only literal INPUTS and call shared deterministic functions. No nested Workflow API is assumed. spec-plan/spec-tdd are compatibility aliases.

Manual: spec-planner → human approval bound to approved artifact hashes → development-orchestrator (separate tdd-tester RED, tdd-developer GREEN/refactor, read-only spec-reviewer).

Automatic Issue: verified origin receipt/repository/author/risk/file policy → planner → independent spec gate → development → owned isolated branch → draft PR → latest-SHA inline review ↔ thread fixes/quality/commit/push/CI/reply/confirmed resolve → AWAITING_HUMAN_MERGE with open PR.

SQLite durable steps retain inputs/policy digests, run state and reconciliation evidence. OS locks ensure one active execution per repo/Issue. Unknown-completion writes block rather than duplicate. Cooperative cancellation occurs at stage boundaries. Agent execution is journaled by CAO; read-only steps declare idempotence, writes declare manual recovery.

The GitHub adapter exposes only named read/create-review/create-draft/reply/resolve operations. There is no Issue-close or merge capability. Git pushes require exact owned feature branch refspec; no force/base push. Executable source inspection and negative tests enforce this boundary. Untrusted text is passed as JSON data, never a shell command.

Target commands run in bubblewrap with no host home/credentials/network, target .git read-only, bounded timeout, scrubbed env and redacted logs. Quality status comes from process codes/JUnit evidence. Tests and approved specs are checked for tampering. CAO Codex profiles require never approval, confined writes/read-only review and disabled network. Providers/production sandboxes have not been live-qualified.

Deployment pins an immutable dependency bundle by SHA256 in each installed entrypoint, verifies it before imports, and retains older bundles for frozen CAO resume scripts. The entrypoint embeds its runtime home because CAO strips CAO_HOME_DIR/CODEX_HOME from script children. A moved snapshot therefore loads its original verified bundle. Manifest records release/CAO compatibility; transaction journals recover interrupted install/uninstall without overwriting subsequent user edits. Individual workflow entrypoints are atomically replaced and always point to a complete versioned bundle.

Read-only Jira inputs and signed GitHub PR triggers have their own authentication/policy layer. Jira can only invoke planning. Trigger execution and inline publication are separately opt-in; stable run IDs, latest-SHA checkout worktrees and durable submission checkpoints prevent duplicate scheduling. No timer/webhook integration is installed automatically.
