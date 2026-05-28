# Spec: Migrate CallGraph private attribute access in MCP tools

## Problem

Three MCP tools bypass `CallGraph`'s public API by directly accessing private
attributes: `_callers`, `_callees`, `_functions`.

| File | Violations |
|------|-----------|
| `codegraph_impact_tool.py` | 6 (4× `_callers.get`, 2× `_callees.get`) |
| `codegraph_overview_tool.py` | 12 (8× `_callers.get`, 3× `_callees.get`, 1× `_callees.items()`, 3× `_functions`) |
| `codegraph_visualize_tool.py` | 2 (`_functions`, `_callers.get`) |

## Existing public API (added in PR #200)

PR #200 (`refactor: add CallGraph.call_edges() public accessor`) added:

```python
def function_refs(self) -> list[FunctionRef]: ...
def callee_refs_of(self, func: FunctionRef) -> list[FunctionRef]: ...
def caller_refs_of(self, func: FunctionRef) -> list[FunctionRef]: ...
def call_edges(self) -> list[tuple[FunctionRef, FunctionRef, int]]: ...
```

## Migration map

| Old pattern | New pattern |
|-------------|-------------|
| `graph._functions` (as iterable) | `graph.function_refs()` |
| `graph._callers.get(func, [])` | `graph.caller_refs_of(func)` |
| `graph._callees.get(func, [])` | `graph.callee_refs_of(func)` |
| `graph._callees.items()` | `for f in graph.function_refs(): callees = graph.callee_refs_of(f)` |

Note: `callee_refs_of`/`caller_refs_of` return `list[FunctionRef]` (sorted by
name+file). The dict `.get()` pattern returned a `set[FunctionRef]`. Downstream
code that needs sorted iteration should be consistent — verify no test asserts
dict-order.

## Scope

No new public API needed. Only call-site migration.

## Verification

```bash
uv run pytest tests/unit/mcp/tools/test_codegraph_impact_tool.py \
    tests/unit/mcp/tools/test_codegraph_overview_tool.py \
    tests/unit/mcp/tools/test_codegraph_visualize_tool.py \
    -v --tb=short
```
