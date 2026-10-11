# Verified interfaces (2026-10-11)

- Original PATH `cao`: broken uv tool import. Kept unchanged.
- Isolated `.venv`: CAO 2.5.0 installed from local `/home/heungtae/develop/ai-agent/cli-agent-orchestrator` source; actual CLI help captured in `cao-*-help.txt`.
- Python 3.14.4. Workflow library minimum Python 3.11, jsonschema 4.x.
- Actual shim: `get_inputs()`, `step(provider, agent, prompt, *, recovery, step_id, timeout, **opts)` and `emit_output(value)`. Recovery choices: idempotent, reconcile, manual. `run_step` exists but declares no recovery policy. Agent steps are not nested Workflow calls.
- Server accepts `working_directory` and `allowed_tools` options. Stable explicit step IDs are used. Replayed handle terminal IDs are never accessed.
- Loading: `$CAO_HOME_DIR/workflows/*.py`, profiles `$CAO_HOME_DIR/agent-store/*.md`; YAML frontmatter name/description/provider/role/allowedTools/codexProfile/codexConfig confirmed against CAO source/schema.
- Actual run syntax: `cao workflow run NAME --run-id ID --input key=value`; lifecycle: status, result, cancel, resume. validate requires a running CAO server.
- Spec Kit CLI absent, target skills required. No automated initialization, no invented specify API.
- Codex CAO defaults to yolo unless a named codexProfile is set. Dedicated named profiles plus inline never/read-only or workspace-write/no-network overrides are required; existing config is not overwritten.
- GitHub uses fixed REST create draft PR/review and GraphQL reviewThreads/addPullRequestReviewThreadReply/resolveReviewThread operations via `gh api`; auth/API results mocked in repository tests.

Sources: installed source and [CAO authoring guide](https://github.com/awslabs/cli-agent-orchestrator/blob/main/docs/workflow-scripts-authoring-guide.md), [Spec Kit](https://github.com/github/spec-kit). CLI help evidence is authoritative for this build.

- Source inspection of script_runner.build_script_env confirms only run identity, generation, API URL, serialized inputs, PATH and HOME are forwarded. CAO_HOME_DIR/CODEX_HOME are not forwarded; installed entrypoints pin runtime paths and bundle hashes, with an explicit operator codex_config_path. Relocated snapshot/stripped-environment execution is included in the integration gate.
