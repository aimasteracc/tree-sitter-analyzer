# Tasks: Migrate CallGraph private attribute access in MCP tools

## Phase 1 — TDD: Write Failing Tests

- [x] **T1** Confirm existing tests cover the call sites (read test files)
  - `tests/unit/mcp/tools/test_codegraph_impact_tool.py`
  - `tests/unit/mcp/tools/test_codegraph_overview_tool.py`
  - `tests/unit/mcp/tools/test_codegraph_visualize_tool.py`

## Phase 2 — Implementation

- [x] **I1** Migrate `codegraph_impact_tool.py` (6 call sites)
  - `_callers.get(current, [])` → `caller_refs_of(current)`
  - `_callees.get(current, [])` → `callee_refs_of(current)`
- [x] **I2** Migrate `codegraph_overview_tool.py` (12 call sites)
  - `_functions` → `function_refs()`
  - `_callers.get(func, [])` → `caller_refs_of(func)`
  - `_callees.get(func, [])` → `callee_refs_of(func)`
  - `_callees.items()` → `for f in function_refs(): callee_refs_of(f)`
- [x] **I3** Migrate `codegraph_visualize_tool.py` (2 call sites)
  - `_functions` → `function_refs()`
  - `_callers.get(func, [])` → `caller_refs_of(func)`

## Phase 3 — Verification

- [x] **V1** Tests pass (focused suite)
- [x] **V2** Run `uv run python -m tree_sitter_analyzer --change-impact --format json`
- [x] **V3** Push + PR to develop
