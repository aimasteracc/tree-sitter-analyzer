`APPROVED`

## Branch
`feature/code-intelligence-architecture`

## Problem

Dogfood scan (2026-05-28) found **106 cross-class private attribute accesses**
in production MCP tools against `CallGraph` and `DependencyGraph` internals:

| Private attr | Access count | Object |
|---|---|---|
| `._nodes` | 30 | DependencyGraph |
| `._callers` | 22 | CallGraph |
| `._callees` | 20 | CallGraph |
| `._resolve_targets()` | 18 | CallGraph (method) |
| `._functions` | 12 | CallGraph |
| `._deps` | 4 | DependencyGraph |
| `._func_by_file` | 2 | CallGraph |
| `._edges` | 2 | DependencyGraph |

These violate the same duck-typed contract that exposed-mcp-tool-private-attrs cleaned up,
but at the `CallGraph`/`DependencyGraph` layer instead of the MCP tool layer.

## Solution

Add public accessor API to `CallGraph` and `DependencyGraph` covering the accessed attrs.

### CallGraph public API additions

```python
# Expose FunctionRef objects (not just dicts)
def all_function_refs(self) -> list[FunctionRef]: ...

# Expose adjacency maps (read-only copies)
def callers_map(self) -> dict[FunctionRef, list[FunctionRef]]: ...
def callees_map(self) -> dict[FunctionRef, list[FunctionRef]]: ...
def functions_by_file(self) -> dict[str, list[FunctionRef]]: ...

# Expose private method as public
def resolve_targets(self, func_name: str, file_path: str | None = None) -> list[FunctionRef]: ...
```

### DependencyGraph public API additions

```python
# Expose graph nodes and edges
def all_nodes(self) -> list[...]: ...
def all_edges(self) -> list[...]: ...
def all_deps(self) -> dict[...]: ...
```

## Scope

- Phase 1: CallGraph (higher traffic — `._callers`, `._callees`, `._functions`, `._resolve_targets`)
- Phase 2: DependencyGraph (`._nodes`, `._deps`, `._edges`)
- Phase 3: Fix all callers in MCP tools to use new public API
- Phase 4: Tests for new public methods
- Phase 5: Verify with full test suite
