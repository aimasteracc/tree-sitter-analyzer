# Spec: Expose MCP Tool CallGraph/Cache Lazy-Init as Public API

## Status: proposed → implementing

## Problem

Four MCP tools (`codegraph_navigate_tool`, `codegraph_impact_tool`,
`codegraph_overview_tool`, `codegraph_visualize_tool`) have private lazy
initializers `_get_call_graph()` and `_get_cache()` plus private instance
attributes `_call_graph` and `_cache`.

Tests currently inject mock graphs by writing directly to private attributes
(`tool._call_graph = mock_graph`) and replacing private methods
(`tool._get_cache = MagicMock(return_value=None)`). This violates the
private-attribute API contract and couples tests to implementation details.

Additionally, the `codegraph_query_tool` has `_get_cache()` used in tests.

## Scope

### Production changes

For each of `CodeGraphNavigateTool`, `CodeGraphImpactTool`,
`CodeGraphOverviewTool`, `CodeGraphVisualizeTool`:

- Add `get_call_graph() -> CallGraph` — public alias for `_get_call_graph()`
- Add `call_graph_initialized: bool` — property returning `self._call_graph is not None`
- Make `execute()` call `self.get_call_graph()` instead of `self._get_call_graph()`

For tools with `_get_cache()` (navigate, query):

- Add `get_cache() -> Any` — public alias for `_get_cache()`
- Add `cache_initialized: bool` — property returning `self._cache is not None`

### Test migration

| File | Pattern → Fix |
|------|---------------|
| `test_codegraph_navigate_tool.py` | `tool._call_graph = m` → `patch.object(tool, "get_call_graph", return_value=m)` |
| `test_codegraph_navigate_tool.py` | `tool._get_cache = M()` → `patch.object(tool, "get_cache", return_value=...)` |
| `test_codegraph_navigate_tool.py` | `tool._call_graph is None` → `not tool.call_graph_initialized` |
| `test_codegraph_navigate_tool.py` | `tool._cache is None` → `not tool.cache_initialized` |
| `test_codegraph_impact_tool.py` | `tool._call_graph = m` → `patch.object(tool, "get_call_graph", return_value=m)` |
| `test_codegraph_overview_tool.py` | `tool._get_call_graph()` → `tool.get_call_graph()` |
| `test_codegraph_overview_tool.py` | `tool._call_graph is [not] None` → `[not] tool.call_graph_initialized` |
| `test_codegraph_visualize_tool.py` | `patch.object(tool, "_get_call_graph")` → `patch.object(tool, "get_call_graph")` |
| `test_codegraph_query_tool_core.py` | `tool._get_cache()` → `tool.get_cache()` |
| `test_codegraph_query_tool_core.py` | `tool._cache is None` → `not tool.cache_initialized` |

### Intentional write-to-private (kept with `# noqa: SLF001`)

`TestProjectRootChanged.test_resets_caches` in `test_codegraph_navigate_tool.py`:
- `tool_with_root._call_graph = MagicMock()  # noqa: SLF001` — test setup write to prime cache state
- `tool_with_root._cache = MagicMock()  # noqa: SLF001` — test setup write to prime cache state
- These two writes are intentional test scaffolding to populate internal state before testing the reset behavior
- The subsequent reads are changed to use the public property: `assert not tool_with_root.call_graph_initialized`

## Acceptance

`uv run pytest tests/unit/test_codegraph_navigate_tool.py tests/unit/test_codegraph_impact_tool.py tests/unit/test_codegraph_overview_tool.py tests/unit/test_codegraph_visualize_tool.py tests/unit/test_codegraph_query_tool_core.py -q` → all pass
