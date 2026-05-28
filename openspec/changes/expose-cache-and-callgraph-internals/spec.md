# OpenSpec: Expose ASTCache.fts5_available and CallGraph.resolve_targets()

## Problem

MCP tool code accesses private internals directly:

- `cache._fts5_available` (4 sites, 3 files) — lazy boolean on ASTCache
- `graph._resolve_targets()` (9 sites, 3 files) — private method on CallGraph
- `cg._func_by_file` (1 site) — private dict on CallGraph

These bypass the intended public interface and make the cache/graph classes
harder to evolve without breaking callers.

## Solution

### ASTCache
Add a `@property fts5_available: bool` that returns `self._fts5_available`.
The internal lazy-init logic stays as-is. External callers get a stable name.

### CallGraph
1. Add `resolve_targets(func_name, file_path=None) -> list[FunctionRef]` as
   a public alias for `_resolve_targets` (keep private for internal use).
2. Add `function_refs_in_file(file_path) -> list[FunctionRef]` that returns
   raw FunctionRef objects (unlike `functions_in_file()` which returns dicts).

## Files to change

Production:
- `tree_sitter_analyzer/ast_cache.py`
- `tree_sitter_analyzer/call_graph.py`
- `tree_sitter_analyzer/mcp/tools/ast_cache_tool.py`
- `tree_sitter_analyzer/mcp/tools/symbol_search_tool.py`
- `tree_sitter_analyzer/mcp/tools/_fts_fast_path.py`
- `tree_sitter_analyzer/mcp/tools/call_graph_tool.py`
- `tree_sitter_analyzer/mcp/tools/codegraph_impact_tool.py`
- `tree_sitter_analyzer/mcp/tools/codegraph_visualize_tool.py`

Tests:
- `tests/unit/test_ast_cache.py`
- `tests/unit/test_call_graph.py` (or equivalent)

## Constraints

- `_fts5_available` internal lazy logic in ASTCache MUST NOT change.
- `_resolve_targets` private method MUST remain (used internally by CallGraph).
- No default changes: TOON format defaults stay.
