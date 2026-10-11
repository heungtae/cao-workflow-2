# Assumptions

- Section 11 is authoritative. spec-plan/spec-tdd are compatibility entrypoints for spec-planner/tdd-developer. Planning ends with approval required.
- External mutation defaults to dry run. Live mutations require explicit run authorization AND repository policy; a policy alone is insufficient. Merge/close/base push are never granted.
- Spec Kit is not initialized automatically. Installed skill files must be present before planner execution.
- Project quality commands are operator-owned argv arrays, never taken from Issue or review text. Coverage/static checks are explicit mandatory configured gates.
- Agent results are untrusted JSON and verified against disk, command evidence and API state. Prompts are not a security boundary; live agent execution requires an operator-provided isolation policy that removes GitHub credentials, confines filesystem writes and denies network/process escapes.
- Unknown completion of external writes is not blindly retried. Reconcile by operation marker or block for an operator.
