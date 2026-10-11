# GitHub live functional validation — 2026-10-11

The user explicitly authorized creation of a GitHub test repository and live functional tests. This separate disposable integration exercise supersedes the earlier restriction on external writes for these test resources only. Ordinary repository validation continues to use mocks.

- Private repository: [heungtae/cao-workflow-2-live-test-20261011](https://github.com/heungtae/cao-workflow-2-live-test-20261011)
- Open fixture Issue: [#1](https://github.com/heungtae/cao-workflow-2-live-test-20261011/issues/1)
- Open draft PR: [#2](https://github.com/heungtae/cao-workflow-2-live-test-20261011/pull/2)
- Owned branch: `cao/live-fixture`
- Original base SHA: `46c1b9fd8a922932f625a1d39e1b94fa0ed317a3`
- No production repository was changed. The test repository is intentionally retained for inspection.

## Executed coverage

| Function | Actual execution |
|---|---|
| Issue intake | Real Issue created as an operator fixture; author/body/open state re-read; exact event digest and trusted origin policy accepted |
| Repository / PR create | Repository initialized by GitHub; operator fixture committed on feature branch; implementation's Repository.commit_push used exact non-force feature refspec; create_pr created one draft PR; second invocation reused it |
| Inline review | Two successive findings published through implementation's inline_review on real changed lines and current SHA; same finding replay did not duplicate the first thread |
| Negative gates | Stale SHA, unauthorized write and merge/auto-merge/queue/Issue-close operations rejected before publication |
| TDD corrections | Deterministic fix callbacks added regression tests, executed assertion-only RED, then changed code; existing tests preserved |
| Quality | Actual pytest, Ruff and stdlib trace coverage commands in network-isolated bubblewrap; both corrections passed |
| Required CI | Real GitHub Actions fixture-test check on each pushed SHA; CI-pending caused BLOCKED_ENVIRONMENT |
| Resume | apply_threads resumed from persisted SQLite state after actual CI; each cycle fixed and pushed exactly once |
| Reply and Resolve | Actual GraphQL replies and Resolve mutations followed by authoritative thread re-query |
| Safety | Main SHA unchanged; PR open/draft/unmerged; auto_merge null; Issue open; no merge/queue/Issue-close requests made |

The first correction changes label() from pending to ready. A second review on the new SHA changes value() from 0 to 42, verifying repeated review/apply scopes. Final fixture requirements are covered by three passing tests.

## Compatibility defect found and fixed

The installed GitHub CLI is 2.46.0 and does not implement `gh api --slurp`. The initial live run failed before PR creation. Added a failing regression test, then removed that option and decoded each JSON document from `gh api --paginate` into a page list. The same live run then progressed successfully.

Evidence: [initial live failure](github-live-integration-first-red.txt), [unit RED](gh-pagination-red.txt), [unit GREEN](gh-pagination-green.txt). The fix covers list PRs, changed files, check runs and commit statuses without assuming a newer gh version.

## Evidence and reproduction boundaries

- [First-cycle live log](github-live-integration.log)
- [Second-cycle live log](github-live-second-cycle.log)
- [Machine-readable results](github-live-result.json)
- [First fixture script](github-live-fixture-script.txt) and [second-cycle script](github-live-second-cycle-script.txt)
- Local working checkout and SQLite/quality evidence remain under `/tmp/cao-workflow-2-live-test-20261011` and `/tmp/cao-live-evidence-20261011`.

The fixture scripts are records of this specifically authorized exercise, not ordinary tests or a general-purpose production command. They contain real GitHub writes and a fixed repository identity. Do not rerun them against existing completed state or another repository without preparing a new identity and explicit authorization.

This verifies the real GitHub adapter, Git push, create_pr, inline_review, apply_threads, quality commands, CI and checkpoint continuation. Planner/provider Agent calls and the full issue-orchestrator/installed CAO Agent pipeline were **not executed**. Findings and fixes were deterministic callbacks; no claim is made about model quality or production permissions. The final AWAITING_HUMAN_MERGE label in the fixture result summarizes remotely verified state; it is not evidence of an executed issue-orchestrator run.

Regression after the compatibility fix: host-enabled **81 unittest tests passed with zero skips**, 11 deployed CAO workflows and 6 profile schemas validated, lifecycle integration PASS. Ordinary pytest: **79 passed, 2 host-only skips, 8 subtests passed**. Ruff, compilation and shell syntax checks pass. ShellCheck remains unavailable.
