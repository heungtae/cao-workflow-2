# Codex Skills implementation progress

Source of truth: CAO_CODEX_SKILLS_BUILD_SPEC.md and section 11 of CAO_WORKFLOWS_BUILD_SPEC_FINAL.md.

| Sprint | State | Gate / next work |
| --- | --- | --- |
| 0 | PASS | Clean initial worktree; Codex 0.162.1; local venv CAO 2.5.0; actual INPUTS and CLI inspected; isolated no-network execution test passed (2 tests). PATH cao is broken; use explicit CAO_BIN. |
| 1 | PASS | Five YAML-valid Skills; explicit/command mapping, input blocking and installed runner contracts. See codex-skills-yaml-green.txt. |
| 2 | PASS | Durable pre-submit ID, deduplication, frozen config, status/resume/cancel, transient reads, terminal/evidence distinction and retained-result fallback. RED/GREEN artifacts retained. |
| 3 | PASS | Global/Project installation, idempotency, collision/force backup, rollback, hash anchoring, modified-file and symlink protection, owned removal. |
| 4 | PASS | Full regression: 116 passed, 29 subtests, zero skips with CAO_TEST_ISOLATION=1; merge/remote-write restrictions and actual native executor probes. |
| 5 | PARTIAL / LIVE_UNVERIFIED | Actual Global/Project skills/list, native Codex isolation and all 6 CAO dry-run routes PASS. Actual user Global installation verified. Implicit model selection and live authenticated provider Workflow remain UNVERIFIED; no external GitHub writes authorized. |
| 6 | PASS locally | README/guide/evidence written; 116 tests plus 29 subtests with zero skips; Ruff, official Skill validator, bash syntax, never-merge scan and old Workflow installation regression PASS. Overall operational acceptance remains incomplete because Sprint 5 is partial. |

No agent/model development is enabled until isolated executor verification passes. Existing Workflow responsibilities remain unchanged. External GitHub E2E is separate and requires explicit authorization.

## Resume work

1. Use the installed Global Skills and an operational CAO_BIN; PATH cao remains broken and was preserved.
2. Configure an authenticated dedicated CAO server CODEX_HOME using the current named profile files described in docs/codex-skills.md. No unrestricted interactive configuration or GitHub credentials should reach workers.
3. In an isolated disposable target with real installed Spec Kit skills and a manually approved fixture, verify actual Codex natural/explicit selection and live Planner/Developer/Reviewer result quality. The current smoke uses fixture Spec Kit files and no model.
4. External GitHub E2E (publication/push/reply/Resolve) is a separate explicitly authorized stage. Never merge/queue/base-push/close Issues, including during E2E.
5. Do not mark Sprint 5 or overall operational acceptance complete based on dry-run HTTP success or Mock output.

Implementation validation performed no external GitHub writes. The user subsequently authorized a delivery commit and push to the unprotected feature branch; operational E2E remains separately unverified. Global local installation is present at ~/.agents/skills and owns only its manifest files; Project scope was installed, recognized and removed in temporary Git projects.
