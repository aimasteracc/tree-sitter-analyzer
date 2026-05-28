# Tasks: Expose MCP Tool CallGraph/Cache API

## Phase 1 — Production (add public aliases + properties)

- [x] **P1** `CodeGraphNavigateTool.get_call_graph()` + `call_graph_initialized` + `cache_initialized` + `get_cache()`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_navigate_tool.py`
- [x] **P2** `CodeGraphImpactTool.get_call_graph()` + `call_graph_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_impact_tool.py`
- [x] **P3** `CodeGraphOverviewTool.get_call_graph()` + `call_graph_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_overview_tool.py`
- [x] **P4** `CodeGraphVisualizeTool.get_call_graph()` (alias only)
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_visualize_tool.py`
- [x] **P5** `CodeGraphQueryTool.get_cache()` + `cache_initialized`
  - File: `tree_sitter_analyzer/mcp/tools/codegraph_query_tool.py`

## Phase 2 — Test migration

- [x] **T1** `test_codegraph_navigate_tool.py` — replace `tool._call_graph = mock` with `patch.object(tool, "get_call_graph", return_value=mock)`
- [x] **T2** `test_codegraph_navigate_tool.py` — replace `tool._get_cache = MagicMock(...)` with `patch.object(tool, "get_cache", return_value=...)`
- [x] **T3** `test_codegraph_navigate_tool.py` — replace `tool._call_graph is None` / `_cache is None` with `call_graph_initialized` / `cache_initialized` properties
- [x] **T4** `test_codegraph_impact_tool.py` — replace `tool._call_graph = mock` with `patch.object`
- [x] **T5** `test_codegraph_overview_tool.py` — replace `_get_call_graph()` → `get_call_graph()` and `_call_graph is None` → `call_graph_initialized`
- [x] **T6** `test_codegraph_visualize_tool.py` — replace `patch.object(tool, "_get_call_graph")` → `patch.object(tool, "get_call_graph")`
- [x] **T7** `test_codegraph_query_tool_core.py` — replace `_get_cache()` → `get_cache()` and `_cache is None` → `cache_initialized`

## Phase 3 — Verification

- [x] **V1** Run targeted test suite → 97 passed
- [x] **V2** Run change-impact verification → 111 passed
- [x] **V3** Push + PR to develop (#206)
