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

## Phase 3 — Verification

- [x] **V1** Run targeted test suite (test_callers_callees_tools, test_ast_cache_tool)
- [x] **V2** Run change-impact verification
- [x] **V3** Commit on feature/code-intelligence-architecture
