# Tasks: Expose ASTCache.fts5_available and CallGraph.resolve_targets()

## Phase 1 — Add public API to core classes

- [ ] **A1** `ASTCache` — add `@property fts5_available: bool`
  - File: `tree_sitter_analyzer/ast_cache.py`
  - After existing `get_conn()` method block

- [ ] **A2** `CallGraph` — add `resolve_targets()` public method
  - File: `tree_sitter_analyzer/call_graph.py`
  - Delegates to `_resolve_targets()`; keep private as well

- [ ] **A3** `CallGraph` — add `function_refs_in_file()` public method
  - Returns `list[FunctionRef]` (raw, unlike `functions_in_file()` which returns dicts)
  - Uses `self._func_by_file.get(file_path, [])`

## Phase 2 — Migrate call sites

- [ ] **M1** `ast_cache_tool.py` — `cache._fts5_available` → `cache.fts5_available`
- [ ] **M2** `symbol_search_tool.py` (3 sites) — same
- [ ] **M3** `_fts_fast_path.py` — same
- [ ] **M4** `call_graph_tool.py` (3 sites) — `graph._resolve_targets()` → `graph.resolve_targets()`
- [ ] **M5** `codegraph_impact_tool.py` (5 sites) — same
- [ ] **M6** `codegraph_visualize_tool.py`:
  - `cg._resolve_targets()` → `cg.resolve_targets()`
  - `cg._func_by_file.get()` → `cg.function_refs_in_file()`

## Phase 3 — Tests

- [ ] **T1** Add tests for `ASTCache.fts5_available` property
- [ ] **T2** Add tests for `CallGraph.resolve_targets()` and `function_refs_in_file()`
- [ ] **T3** Update any mocks using `cache._fts5_available` or `graph._resolve_targets`

## Phase 4 — Verification

- [ ] **V1** `uv run python -m tree_sitter_analyzer --change-impact --format json`
- [ ] **V2** Full focused test suite passes
- [ ] **V3** Push + PR to develop
