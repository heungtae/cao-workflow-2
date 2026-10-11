# Troubleshooting

- `cao` import failure: select a compatible isolated installation via `CAO_BIN`; this build left the broken PATH launcher unchanged.
- `validate` connection failure: start a local CAO server with matching CAO_HOME_DIR/CAO_API_PORT. Install current source first; CAO rejects paths outside its workflow directory.
- Namespace error: Linux must permit bubblewrap namespaces. Quality execution fails closed; do not replace it with an unrestricted shell for untrusted targets.
- Missing Spec Kit: initialize the **target** using your installed, documented Spec Kit procedure. This repository never initializes it without authorization.
- BLOCKED_SPEC: commit and inspect artifacts, resolve risks, explicitly approve again. Development cannot call Planner or edit specs.
- RED infrastructure failure: fix command/dependencies/JUnit discovery. An import error, zero executed tests or missing report is not RED success.
- Test tamper detection: preserve existing test expectations/config; write additional regression tests during the Test Agent or PR fix stage. An Agent's PASS claim cannot override hashes/gates.
- Collision: install refuses existing files or modified owned files. `--force` backs up collisions in the manifest; uninstall restores original bytes. Link mode is deliberately rejected because deployment must be an immutable snapshot.
- Unknown write completion: inspect durable markers and remote PR/threads/HEAD before retry. Never force-push or assume a failed response means the write did not occur.
- CI delay: resume with unchanged identity; completed fixes/tests/pushes are checkpointed and rechecked against latest SHA before reply/Resolve.
- Cost budget: CAO shim lacks verified usage/currency data. `max_cost` fails closed before Agent execution; use observed limits and operator monitoring. Do not infer a cost PASS from narrative.
- OPEN/DISPUTED/BLOCKED/FIXED/RESOLVED thread results are independent of GitHub approval and merge. AWAITING_HUMAN_MERGE still requires a person.

- In the CAO development venv, libtmux registers a pytest plugin incompatible with pytest 9 fixture marks. Repository pytest config disables that unrelated plugin; the real TDD fixture also excludes it explicitly. Target projects should use their own dependency environment and required plugins. This was an infrastructure failure, never counted as intended RED.
