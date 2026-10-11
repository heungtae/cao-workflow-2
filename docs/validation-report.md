# Final validation and resume ledger

Specification: CAO_WORKFLOWS_BUILD_SPEC_FINAL.md. Sections 11–12 take precedence over the earlier four-workflow descriptions.
Baseline: LICENSE, .gitignore, and two user specification files; no existing application implementation. The original specifications and LICENSE were preserved.
Implementation release: 1.0.0. Runtime qualified locally against CAO 2.5.0 from the installed local source checkout. No default CAO home or user Codex configuration was replaced.

## Sprint completion

All mandatory implementation work for Sprints 0–9 is complete and passes the local gates below. This status does not claim live provider or production GitHub qualification.

| Sprint | Status | Executed evidence |
|---|---|---|
| 0 | COMPLETE locally | Actual CLI/help/source/API discovery; real CAO server and profile JSON schema |
| 1 | COMPLETE locally | Install/dry-run/reinstall/uninstall; ownership, collisions, rollback, interrupted transaction recovery |
| 2 | COMPLETE locally | Installed-skill fixtures, planning-only scope, complete artifacts, independent read-only review, explicit spec approval |
| 3 | COMPLETE locally | Separate RED/GREEN/refactor; actual assertion failure → passing test; static/coverage commands; protected spec/test checks |
| 4 | COMPLETE locally | GitHub operation allowlists, inline finding schema, current SHA/changed-line checks, LEFT deletion/RIGHT addition comments; deployed CAO validation |
| 5 | COMPLETE locally | Bounded retries, frozen inputs, checkpoints, process exclusion, cancellation, unknown-write reconciliation, isolated DAG worktrees |
| 6 | COMPLETE locally | Committed approved-spec development/review loop, feedback, cycle cap, no planner or PR actions in development orchestrator |
| 7 | COMPLETE locally | Trusted origin receipt/author/repository validation, risk/file policy, deduplication and resumable intake |
| 8 | COMPLETE locally | Mock draft PR reuse, exact owned branch, fix/test/push/CI/reply/Resolve, stale SHA/permission/dispute/failure paths |
| 9 | COMPLETE locally | Mock Issue-to-OPEN-PR end-to-end, latest SHA and CI gate, AWAITING_HUMAN_MERGE, lifecycle integration and safety checks |

[Requirements matrix](requirements-matrix.md) maps each requirement to implementation and regression tests. Sprint RED/GREEN files and subsequent regression evidence are retained in this directory. Jira read-only planning input, HMAC PR webhook/timer entrypoints, compatibility manifests and observed command metrics are also implemented and tested; installation does not activate an external trigger.

## Final executed gates

- Full integration: `.venv/bin/python scripts/verify-local.py` — PASS, see [local-integration.log](local-integration.log).
- Full host-enabled suite: **81 unittest cases passed, zero skips**. Two Linux isolation cases that the ordinary sandbox suite skips were executed successfully by the host-enabled integration gate.
- Ordinary pytest: **79 passed, 2 skipped, 8 subtests passed**; see [pytest-final.txt](pytest-final.txt). The skips are the same host-only isolation cases, covered above.
- Ruff lint and formatting — PASS; compilation and `bash -n` for all four lifecycle entrypoints — PASS.
- Real CAO 2.5.0: all **11 installed Python workflows** validated; all **6 deployed profile frontmatters** passed the actual CAO profile schema.
- Install dry-run, real install, identical reinstall manifest, validation, uninstall dry-run and uninstall preserving unrelated user files — PASS.
- Installed workflow executed through the actual input/output shim in dry-run mode; status and cooperative cancel commands — PASS.
- Frozen entrypoint relocated and launched with CAO's restricted child environment — PASS. Content-addressed dependency bundles retain pinned runtime home and verify digests.
- Structured BLOCKED_ENVIRONMENT output and nonzero script exit on explicit missing isolated Codex configuration — PASS before any Agent step.
- Offline trigger CLI — PASS without GitHub reads, writes or CAO Agent submissions.
- Mock failure/retry/cancellation/resume, CI-pending continuation, duplicate-write avoidance and no-merge gates — PASS.
- Real isolated TDD fixture: assertion RED exit 1, GREEN/refactor and quality commands exit 0. No real model generated the fixture edits.

Validation fixes include an incompatible unrelated libtmux pytest plugin, pytest import-path configuration, malformed review findings, deleted-line comment sides, CAO child environment/frozen-script imports, and failure exit codes required for CAO journal recovery. Their failed evidence was retained rather than recorded as PASS.

## Safety and qualification limits

During the initial mock/local validation, no actual external GitHub mutations were performed. The subsequently user-authorized disposable live exercise is recorded separately below. Mock adapters exercised permitted mutations; runtime allowlists and automated tests reject merge/queue/close/base-push operations. No Git commit or push was made in this implementation repository. The live fixture uses only its owned test feature branch.

The following remain explicitly **LIVE_UNVERIFIED**, rather than completed production qualification:

1. Actual provider Agent execution and its output quality; the installed Agent shim contract and isolation configuration were inspected/tested, but no model session ran.
2. Production GitHub permissions, CI checks, branch protections, inline publication and Resolve behavior. These require operator credentials, repository policy and explicit external-write approval.
3. Production Jira authentication and webhook/timer deployment. Fixed read-only/HMAC adapters were tested with mocks and offline inputs.
4. Real target Spec Kit setup. `specify` is absent in this environment; discovery/dispatch used installed-skill fixtures. Live use requires the target's real five Spec Kit skills and a Git root.
5. Native CAO journal resume through an actual interrupted Agent session. Workflow checkpoint recovery and CAO's relocated frozen-entrypoint shape were tested, but no live Agent interruption was exercised.
6. ShellCheck is unavailable. Shell syntax and actual lifecycle execution passed; no ShellCheck PASS is claimed.
7. Linux bubblewrap/user namespaces and dedicated Codex sandbox profiles are operational prerequisites. Runtime fails closed if isolation/configuration cannot be established.
8. Monetary usage is unavailable from the installed shim. Observed durations/failures are reported; unobserved costs/human intervention counts remain null. A configured monetary cap blocks execution rather than claiming enforcement from estimated usage.
9. The Java Spring/Kafka directory is an operator configuration example; no Java application or Kafka service was provisioned or executed.

The PATH CAO installation initially failed to import its package. A repository-local venv with the compatible source checkout was used; the user's PATH installation was not repaired or replaced.

## Running and resuming

See [README](../README.md) and [usage](usage.md) for installation, config/policy examples and real verified CLI commands. Start with the full integration command above. For a target project, perform doctor → install → validate → planning → human spec review/commit/approval → development, then separately authorize permitted GitHub operations.

Progress is retained in SQLite run/step checkpoints, phase evidence, JSON/Markdown reports and the installation transaction journal. Unknown writing outcomes require reconciliation before rerun. Agent workflow failures return nonzero exit codes so CAO does not mark blocked work completed. The Issue pipeline's successful terminal state is an OPEN PR awaiting human merge.

[Change inventory](change-inventory.json) lists all implementation and evidence files, excluding the two pre-existing user specifications and local venv/cache files.

## Subsequent authorized disposable GitHub test

See [GitHub live validation](github-live-validation.md) for actual repository/Issue/draft PR creation, two inline review/apply cycles, isolated RED/GREEN gates, real CI wait/resume, replies and confirmed Resolve. The installed gh 2.46.0 pagination incompatibility was reproduced, regression-tested and fixed. The live adapter/feature-push/CI boundary is now qualified for this disposable repository; provider Agents, Planner and full Issue orchestration remain LIVE_UNVERIFIED.
