# Tasks: Expose Remaining MCP Tool Private Attrs

## Phase 1 — Production (add public aliases + properties)

- [x] **P1** `CodeGraphRelationToolMixin.get_call_graph()` + `call_graph_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_relation_tool.py`
  - Automatically propagates to `CodeGraphCallersTool` + `CodeGraphCalleesTool`
- [x] **P2** `CodeGraphPRReviewTool.get_call_graph()` + `call_graph_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_pr_review_tool.py`
- [x] **P3** `ASTCacheTool.get_cache()` + `cache_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/ast_cache_tool.py`

## Phase 2 — Test migration

- [x] **T1** `test_callers_callees_tools.py` — replace `_get_call_graph()` → `get_call_graph()` and `_call_graph is None/not None` → `call_graph_initialized`
- [x] **T2** `test_ast_cache_tool.py` — replace `_get_cache()` → `get_cache()` and `_cache is None` → `cache_initialized`; direct write `_cache = MagicMock()` → `# noqa: SLF001`

## Phase 4 — Extended scan (dogfood-discovered, same session)

- [x] **P4** `CodeGraphOverviewTool.get_call_graph()` + `call_graph_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_overview_tool.py`
- [x] **P5** `CodeGraphImpactTool.get_call_graph()` + `call_graph_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_impact_tool.py`
- [x] **P6** `CodeGraphNavigateTool.get_call_graph()` + `call_graph_initialized` + `get_cache()` + `cache_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_navigate_tool.py`
- [x] **P7** `CodeGraphQueryTool.get_cache()` + `cache_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_query_tool.py`
- [x] **T3** `test_codegraph_overview_tool.py` — all `_get_call_graph()`/`_call_graph` reads → public API
- [x] **T4** `test_codegraph_impact_tool.py` — `_call_graph` write → `# noqa: SLF001`
- [x] **T5** `test_codegraph_navigate_tool.py` — writes → `# noqa: SLF001`; state reads → public properties
- [x] **T6** `test_codegraph_query_tool_core.py` — `_get_cache()`/`_cache` → `get_cache()`/`cache_initialized`
- [x] **T7** `test_call_graph_tool.py` — all violations fixed
- [x] **T8** `test_graph_cache_invalidation.py` — `tool._call_graph` identity checks → `tool.get_call_graph()`
- [x] **T9** `test_ast_cache_tool.py` fixture write → `# noqa: SLF001`

## Phase 3 — Verification

- [x] **V1** Run targeted test suite (175 tests pass across all 9 affected test files)
- [x] **V2** Final private-attr scan: zero violations remain in MCP tool tests
- [x] **V3** All commits on feature/code-intelligence-architecture
