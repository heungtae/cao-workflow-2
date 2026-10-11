# Repository instructions

Implement the final build specification with tests first. Keep sprint evidence in docs/validation-report.md. Never merge, enable auto-merge, enqueue merge, push base/protected branches or close Issues. No external GitHub writes during repository validation. Do not weaken tests or specs to pass gates. Agents must run inside a verified isolated executor before live development is enabled.

Write all repository documentation, including build specifications and Skill instructions, in English.

## Codex CAO commands

When installed skills are available, route `spec plan/update` to `$cao-spec`,
`dev run/status/resume/cancel` to `$cao-dev`, `issue run` to `$cao-issue`,
`pr review` to `$cao-pr-review`, and `pr apply` to `$cao-pr-apply`.
For `pr status RUN_ID`, use either PR skill's common runner and the stored workflow identity.
Read the selected SKILL.md and call its bundled scripts/run.py from the current Git project.
General requests to plan CAO requirements, execute approved feature development, process an eligible
automated Issue, review a PR, or apply inline review fixes use the same mappings.
Show the Run ID, track CAO status, and check retained business evidence before declaring completion.
Implicit selection is best effort; explicit `$cao-*` is the documented fallback.
Never infer remote-write authorization from these aliases. Project instruction examples are in
docs/codex-skills.md; installation preserves target AGENTS.md.
