# Implementation work list and requirement evidence

Baseline had no implementation. All existing user specification files and LICENSE were preserved. Section 11 overrides the earlier four-workflow shape. Every row below has executable implementation and regression coverage; the final gate outcome is recorded in validation-report.md.

| Sprint / requirement | Implementation | Evidence |
|---|---|---|
| 0: actual CAO CLI/API/profile/source | versions.md, captured CLI help, real 2.5.0 venv/server | verify-local.py, Agent shim contract tests, deployed profile schema validation |
| 1: safe install/reinstall/collision/rollback/uninstall | installation.py, cli.py, four shell entrypoints | test_install.py; manifest ownership, force backup restoration, symlink protection, interruption journal recovery |
| 2: target Git/feature/skills/artifacts, Planner-only, read-only review | project.py, dispatcher.py, approvals.py | test_workflows.py; fixture planning, scope, missing artifacts, reviewer mutation detection |
| 3: separate RED/GREEN/refactor, assertion-vs-infrastructure, protected tests/specs | tdd.py, quality_gate.py, spec_traceability.py | test_quality_gate.py, test_gate_execution.py, test_real_tdd.py; real isolated pytest/static/coverage commands |
| 4: allowlisted PR reads/inline finding contracts, installed CAO validation | github_pr.py, review.py, contracts/*.json | test_pr_review_threads.py; latest changed-line/SHA gate; all 11 actual CAO validates |
| 5: bounded retry, checkpoint/recovery, DAG/worktree isolation, reporting | issue_state.py, parallel.py, reporters.py | test_recovery.py, test_reporters.py, bounded GREEN attempts and completed TDD replay |
| 6: committed human-approved specs, Developer↔Reviewer only | approvals.py, orchestrators.development | test_development_orchestrator.py; no Planner/PR calls, spec drift, GREEN failure, cycle cap |
| 7: trusted CAO origin/author/receipt/repo, low-risk/file gate, dedup | issue_intake.py, issue_state.py, orchestrators.issue | test_issue_orchestrator.py; high risk/changed receipt rejected, dry run and one active run |
| 8: draft PR reuse, exact owned branch, inline threads, fix/test/push/reply/Resolve | pr_create.py, review.py, review_threads.py | test_pr_apply.py, test_never_merge.py; CI/permission/stale/SHA/resolve failure and disputed specs |
| 9: latest-SHA re-review loop, OPEN PR terminal state, E2E, lifecycle/security | runtime.py, workflows/*.py, verify-local.py | test_end_to_end.py; AWAITING_HUMAN_MERGE, CI resume, no duplicate fix/push/reply, no merge/Issue Close |
| Immutable frozen-script resume | installed RUNTIME_HOME/bundle digest, retained version bundles | deployment test; relocated snapshot with CAO's stripped environment; modified bundles fail before imports |
| Post-MVP: Jira input | jira.py → spec-planner only | test_triggers.py; fixed GET, host/project gates, no automatic Issue development |
| Post-MVP: PR webhook/timer triggers | triggers.py, trigger.py | HMAC/dedup/policy tests; offline CLI integration, bounded one-shot scheduling, opt-in localhost listener |
| Post-MVP: version/compatibility/metrics | manifest release 1.0.0/CAO 2.5.0, command durations, failures | reporter tests; unavailable costs/human counts remain null; monetary limits fail closed |

The safety gate inspects Python AST constants/literal command arrays and executable shell lines, as well as the runtime Git/GitHub allowlists. Test/documentation/prohibition text is excluded from executable scans. The normal Mock Issue completion has exactly zero Merge/Auto-Merge/Queue/Issue Close operations.

Live provider/Jira/GitHub production qualification is separate from these locally executed gates. Installation does not create app specs here, initialize target Spec Kit, enable schedulers, register webhooks or modify existing user CAO/Codex configuration.
