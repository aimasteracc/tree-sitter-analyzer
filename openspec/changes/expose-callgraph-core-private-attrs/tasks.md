# Tasks: Expose CallGraph / DependencyGraph Core Private Attrs

## Phase 1 — CallGraph public API (call_graph.py)

- [x] **P1** `CallGraph.all_function_refs()` → `list[FunctionRef]`
  - Fix callers: `codegraph_overview_tool.py`, `codegraph_visualize_tool.py`, helper modules
- [x] **P2** `CallGraph.callers_map()` → `dict[FunctionRef, list[FunctionRef]]` (copy)
  - Fix callers: `codegraph_impact_tool.py`, `codegraph_overview_tool.py`
- [x] **P3** `CallGraph.callees_map()` → `dict[FunctionRef, list[FunctionRef]]` (copy)
  - Fix callers: `codegraph_impact_tool.py`, `codegraph_overview_tool.py`
- [x] **P4** `CallGraph.resolve_targets()` public alias for `_resolve_targets()`
  - Fix callers: `call_graph_tool.py`, `codegraph_impact_tool.py`
- [x] **P5** `CallGraph.functions_by_file()` → `dict[str, list[FunctionRef]]` (copy)
  - Fix callers: wherever `._func_by_file` is accessed

## Phase 2 — DependencyGraph public API (project_graph.py)

- [x] **P6** `DependencyGraph.all_nodes()` → `frozenset[str]`
- [x] **P7** `DependencyGraph.all_deps()` → `dict[str, set[str]]` (deep copy)
- [x] **P8** `DependencyGraph.all_edges()` → `frozenset[tuple[str, str]]`
  - Also added `FileDependencyView.all_nodes()` for duck-typing compatibility

## Phase 3 — Fix callers in MCP tools

- [x] **F1** `codegraph_impact_tool.py` — replace all `graph._callers`/`graph._callees`/`graph._resolve_targets` calls
- [x] **F2** `codegraph_overview_tool.py` — replace `graph._functions`/`graph._callers`
- [x] **F3** `call_graph_tool.py` — replace `graph._resolve_targets` calls
- [x] **F4** `dependency_analysis_tool.py` + helpers — replace DependencyGraph private access
  - Also fixed: `smart_context_tool.py`, `symbol_lineage_tool.py`, `safe_to_edit_helpers.py`,
    `codegraph_visualize_tool.py`

## Phase 4 — Tests

- [x] **T1** Tests for `all_function_refs()`, `callers_map()`, `callees_map()`, `resolve_targets()`, `functions_by_file()`
- [x] **T2** Tests for DependencyGraph public API (11 tests in `TestDependencyGraphPublicAPI`)

## Phase 5 — Verification

- [x] **V1** Run full test suite — 16638 passed, 73 skipped, 2 xfailed
- [x] **V2** Re-run cross-class private attr scan — 0 violations in MCP tool layer
- [x] **V3** Commit — committed in 2 batches on feature/code-intelligence-architecture
