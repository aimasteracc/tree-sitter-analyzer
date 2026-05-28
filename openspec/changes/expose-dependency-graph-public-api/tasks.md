# Tasks: Expose DependencyGraph Public Accessors

## Phase 1 — TDD: Write Failing Tests

- [ ] **T1** Write test: `DependencyGraph.has_node()` returns True for existing node, False otherwise
  - File: `tests/unit/test_project_graph.py` — `TestDependencyGraphPublicAccessors`
  - 3 tests: `has_node` True/False, `node_count`, `edge_count`

## Phase 2 — Implementation

- [ ] **I1** Add `has_node()`, `node_count()`, `edge_count()` to `DependencyGraph`
  - File: `tree_sitter_analyzer/project_graph.py` — after `edges()` method
- [ ] **I2** Migrate call sites in production code (4 files, ~16 call sites)
  - `project_graph.py:695,720`
  - `smart_context_tool.py:220,222`
  - `symbol_lineage_tool.py:410`
  - `dependency_analysis_tool.py:229,236,243,249,254,255,258,262,314,315`
  - `safe_to_edit_helpers.py:639,643`

## Phase 3 — Verification

- [ ] **V1** Tests pass (focused: test_project_graph, test_dependency_analysis_tool, etc.)
- [ ] **V2** Run `uv run python -m tree_sitter_analyzer --change-impact --format json`
- [ ] **V3** Push + PR to develop
