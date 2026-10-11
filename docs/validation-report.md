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

## Codex Skills — Sprint 0 (2026-10-11)

- Read both complete build specs, existing INPUTS, installation transactions, runtime approval and issue intake contracts.
- Codex CLI 0.162.1; repository venv CAO 2.5.0. PATH cao fails ModuleNotFoundError; it was not modified.
- Actual CLI: workflow get/run/status/result/resume/cancel; run supports --detach/--run-id/--input/--json; resume is blocking and never a new submission.
- Official Codex documentation confirms name/description frontmatter, explicit $ invocation, implicit description matching, ~/.agents/skills and project .agents/skills: https://learn.chatgpt.com/docs/build-skills.
- CAO_TEST_ISOLATION=1 .venv/bin/python -m pytest tests/test_gate_execution.py -q: 2 passed; real bubblewrap has no host credentials/network.
- No running CAO server found. Subsequent local smoke will use temporary CAO_HOME and loopback server; no external GitHub writes.

## Codex Skills — final local validation (2026-10-11)

**Local implementation and automation gates passed. Overall operational acceptance is LIVE_UNVERIFIED; Sprint 5 is partial.** This does not claim that a real model selected a skill, generated specs, ran Developer↔Reviewer or published GitHub changes.

| Sprint | Result | Evidence |
| --- | --- | --- |
| 0 | PASS | Both complete specifications, existing runtime/INPUTS/install contracts, CAO 2.5.0 actual help/source, Codex 0.162.1 and official Skills/CLI docs inspected; actual bwrap isolation passed. |
| 1 | PASS | Five valid YAML Skills, natural command routing metadata plus explicit invocation, input validation. `codex-skills-red.txt` -> `codex-skills-s1-green.txt`; strict YAML RED -> GREEN and all five official skill-creator validators PASS. |
| 2 | PASS | Durable pre-submit ID, existing-ID deduplication, safe argv, project/server/home binding, frozen config/event/policy, terminal and query error separation, bounded read retries, existing-run resume/cancel. Lifecycle and retained-output RED -> GREEN logs. |
| 3 | PASS | Global/Project transactional deployment, collision/force backups, latest customized-file restoration, rollback, manifest ownership, immutable hash checks, symlink protection and safe removal. Install/bundle/update RED -> GREEN logs. |
| 4 | PASS | Full offline Mock integration of all command routes, approved-spec checks, provenance/number/repository binding, terminal/no-evidence/CI/SHA/thread reply/Resolve checks, static and runtime never-merge gates. |
| 5 | PARTIAL / LIVE_UNVERIFIED | Actual Codex Global/Project discovery PASS; native write/read-only profile probes PASS; actual 6 CAO dry-run submissions/status/result PASS and fresh-session status PASS. Model selection and live provider Workflow are not verified. |
| 6 | PASS locally | README/user guide/progress/evidence recorded; final 116 pytest cases and 29 subtests passed, zero skips; existing Workflow installation/regression and syntax/quality gates passed. Overall completion awaits Sprint 5. |

### Executed final gates

- `CAO_TEST_ISOLATION=1 .venv/bin/python -m pytest -q`: **116 passed, 29 subtests passed, zero skips**. [Full log](codex-skills-regression.txt).
- `.venv/bin/ruff check workflow_lib workflows harness scripts tests codex-skills`: PASS. `ruff format --check` on the same paths: **72 files already formatted**. `bash -n` for every scripts/*.sh: PASS. ShellCheck is unavailable and is not claimed PASS. [Quality evidence](codex-skills-quality-gate.txt).
- Official `/home/heungtae/.codex/skills/.system/skill-creator/scripts/quick_validate.py` for each of the 5 Skills: **Skill is valid!**. Includes proper YAML quoting, beyond regex metadata checks.
- `./scripts/validate-codex-skills.sh`: PASS for source structure and executable safety scan, including Skill helper scripts.
- `.venv/bin/python scripts/verify-local.py`: **LOCAL INTEGRATION PASS**, temporary CAO server/home, install/reinstall, 11 CAO Workflow validates, actual profile schema, full unittest regression, stripped-environment shim/durable result, status/cancel and owned uninstall. [Existing Workflow regression](codex-skills-workflow-regression.txt); regenerated server log [local-server.log](local-server.log).
- `.venv/bin/python scripts/verify-codex-skills.py`: PASS, real Codex app-server `skills/list` sees all five enabled Skills in both repo/user scopes. Both actual `codex sandbox` profiles enforce network denial. All six routes (spec-planner, spec-update, development-orchestrator, issue-orchestrator, pr-review, pr-apply) were actually submitted to a disposable CAO 2.5.0 server and returned validated **DRY_RUN**. No Agent/model or external GitHub operation started. [Actual integration](codex-skills-live.txt), [server requests](codex-skills-server.log).
- Global real user install: `install-codex-skills.sh --global --dry-run`, actual `--global`, `validate-codex-skills.sh --global`, installed independent launcher `--help`, fresh actual Codex `skills/list`: PASS. Installed under `/home/heungtae/.agents/skills/`, including owned shared runtime. [Installation evidence](codex-skills-global-install.txt). Temporary Project installations were recognized and uninstalled; unrelated files were preserved.
- GitHub writes/merge/auto-merge/queue/protected push/Issue close during this validation: **0**. Static executable scan includes codex-skills, scripts, Workflows and libraries; existing allowlisted GitHub operations and Mock never-merge/resolve-failure tests remain intact.

### Actual interface differences resolved

1. PATH `cao` still fails importing cli_agent_orchestrator. Use `CAO_BIN=/home/heungtae/develop/ai-agent/cao-workflow-2/.venv/bin/cao`. No unrelated global CAO installation was changed.
2. CAO 2.5.0 ScriptSpec returned by get has `path/source/inputs`, without a `mode` field; states are lowercase. Regression tests use the actual shapes.
3. CAO retained script `result` currently omits emitted business output. The adapter reads existing Workflow-owned `workflow-data/<identity-hash>/result.json`, validates schema and exact run_id, and marks result_source. Remote-only/unavailable artifacts return UNVERIFIED. Captured actual absence is in [debug evidence](codex-skills-live-debug.txt); RED/GREEN regression exists.
4. Current Codex `--profile NAME` reads CODEX_HOME/NAME.config.toml. Profile-file validation was added without removing legacy profile-table support. The live runner performs actual native CLI probes before enablement; an unresolvable/unsafe executor blocks execution. Documentation now distinguishes current and legacy formats.
5. CLI submission is asynchronous `--detach --run-id --input ... --json`; status/result are read-only, resume is blocking and may halt for human step decisions. The runner never invents wait options or blindly repeats writes.

### Remaining operational acceptance

- Dedicated authenticated provider environment and real Spec Kit skills have not been qualified through Skills. Disposable smoke profiles have no model authentication and fixture Spec Kit files; they are not live development evidence.
- Actual model implicit natural-language selection and explicit conversational completion are UNVERIFIED. Metadata, deterministic command mapping and real CLI discovery pass; implicit selection is best effort per official docs.
- Actual live Planner/Developer/Reviewer and GitHub publication/push/reply/Resolve E2E through these Skills remain UNVERIFIED. External writes require separate explicit user approval; repository validation does not perform them.
- Changed files not supported by retained evidence remain `changed_files_verified=false`; unavailable thread counts are null. Successful live PR results use read-only SHA/open-state/thread/CI confirmation; failures are never promoted to success.

### Changed file inventory and examples

- Added `codex-skills/{cao-spec,cao-dev,cao-issue,cao-pr-review,cao-pr-apply}/SKILL.md` and each bundled `scripts/run.py`.
- Added `workflow_lib/codex_skills.py`, `workflow_lib/skill_installation.py`, `contracts/codex-skill-result.schema.json`.
- Added `scripts/{install-codex-skills.sh,uninstall-codex-skills.sh,validate-codex-skills.sh,codex-skills-admin.py,cao-skill-runner.py,verify-codex-skills.py}`.
- Added `tests/test_codex_skills.py` and `tests/test_codex_skill_install.py`; extended existing installer/isolation/static scan without weakening old tests or Workflow responsibilities.
- Updated `AGENTS.md`, `README.md`, `pyproject.toml` (development-only YAML validation dependency), `workflow_lib/{installation.py,isolation.py,merge_guard.py}`, `docs/usage.md`, this report and generated local-server log.
- Added [Skills guide](codex-skills.md), [persistent Sprint progress](implementation-progress.md), and `docs/codex-skills-*.txt/.log` RED/GREEN and actual integration artifacts. Source code, schema and tests are the execution contracts.

In a configured target Codex session: `$cao-dev dev run 001-feature`; after session restart: `$cao-dev dev status RUN_ID`. Other examples: `spec plan "Kafka failover"`, `issue run 123`, `pr review 45`, `pr apply 45`. Setup and exact direct-run syntax are in the Skills guide.
