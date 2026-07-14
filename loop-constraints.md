# Loop Constraints

> These constraints are **binding** — the agent MUST follow them every run.
> The `loop-constraints` skill reads this file at the start of every run.

## Push & Merge
- Don't push before telling me
- Never auto-merge to develop or main without human approval
- Always create a draft PR first; let me review before marking ready

## Paths — Never Edit
- `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- `corpus/` — test corpus data; never modified by automation
- `.env`, `.env.*`
- `synapse_resolver/_registry.py` — moat registry; human review required for any change

## Code
- Always run `pytest tests/ -x --timeout=60` before proposing any fix
- Never disable tests or add xfail markers to make CI green
- Never refactor unrelated code — one fix per run
- Max 3 fix attempts per item; log each attempt to `loop-run-log.md` and escalate after 3

## Architecture
- Every new language resolver needs a matching test in `tests/unit/` before merging
- Never change the entry-point group name (`tree_sitter_analyzer.plugins`) in pyproject.toml
- Complexity changes (RFC-0019 scope): design review required before any code change
- Never wire `mcp/tsa_explore.py` into `server.py` until Phase 1b benchmark results confirm benefit

## Dogfood Protocol
- Always call `mcp__tree-sitter-analyzer__health action=overview` at the start of every run
- Report what TSA found about itself before proposing any action
- TSA MCP is the primary discovery tool — not grep, not Read, not memory

## Budget
- If token spend hits 80% of daily cap, switch to report-only
- If `loop-pause-all` appears in STATE.md High Priority, exit immediately

---
<!-- Add project-specific rules below. The loop reads this verbatim. -->
