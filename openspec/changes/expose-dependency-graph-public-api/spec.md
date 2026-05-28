# Spec: Expose DependencyGraph Public Accessors

## Problem

`DependencyGraph` in `project_graph.py` has three private attributes accessed by
external modules:

| Attribute | Type | External accessors |
|-----------|------|--------------------|
| `_nodes`  | `set[str]` | 16 call sites in 4 files |
| `_edges`  | `set[tuple[str,str]]` | 1 call site (`dependency_analysis_tool.py`) |
| `_deps`   | `dict[str, set[str]]` | 1 call site (`dependency_analysis_tool.py`) |

This violates the private-attribute contract and makes refactoring fragile.

## Root cause

`DependencyGraph.nodes()` returns a sorted `list[str]` — good for deterministic
output but O(n) for membership checks. Callers that need `file_rel in graph._nodes`
(O(1) set lookup) reach for the private attribute because there's no public
`has_node()` equivalent.

Similarly, `edge_count` and the full `_deps` dict have no public surface.

## Design

Add three methods to `DependencyGraph`:

```python
def has_node(self, file_rel: str) -> bool:
    """O(1) membership test — True if file_rel is a node in the graph."""
    return file_rel in self._nodes

def node_count(self) -> int:
    """Return the number of nodes in the graph."""
    return len(self._nodes)

def edge_count(self) -> int:
    """Return the number of directed edges in the graph."""
    return len(self._edges)
```

The `_deps` direct access in `_deterministic_find_cycles` is replaced by:
- `nodes_sorted = graph.nodes()` (already sorted)
- `deps.get(node, ())` → `graph.dependencies_of(node)` (already sorted, returns list)

## Call site migration plan

| File | Old | New |
|------|-----|-----|
| `project_graph.py:695,720` | `file_rel not in self.graph._nodes` | `not self.graph.has_node(file_rel)` |
| `smart_context_tool.py:220` | `rel_path in graph._nodes` | `graph.has_node(rel_path)` |
| `smart_context_tool.py:222` | `for node in graph._nodes` | `for node in graph.nodes()` |
| `symbol_lineage_tool.py:410` | `f not in graph._nodes` | `not graph.has_node(f)` |
| `dependency_analysis_tool.py:229,236` | `in graph._nodes` | `graph.has_node(...)` |
| `dependency_analysis_tool.py:243` | `for node in graph._nodes` | `for node in graph.nodes()` |
| `dependency_analysis_tool.py:249` | `len(graph._nodes)` | `graph.node_count()` |
| `dependency_analysis_tool.py:254` | `len(graph._nodes)` | `graph.node_count()` |
| `dependency_analysis_tool.py:255` | `len(graph._edges)` | `graph.edge_count()` |
| `dependency_analysis_tool.py:258,262` | `for n in graph._nodes` | `for n in graph.nodes()` |
| `dependency_analysis_tool.py:314` | `sorted(graph._nodes)` | `graph.nodes()` |
| `dependency_analysis_tool.py:315` | `deps = graph._deps` | eliminated — use `graph.dependencies_of(node)` |
| `safe_to_edit_helpers.py:639` | `rel_path in graph._nodes` | `graph.has_node(rel_path)` |
| `safe_to_edit_helpers.py:643` | `for node in graph._nodes` | `for node in graph.nodes()` |

## Backward compatibility

No public API is broken. The private attributes remain (for internal use). Only
the encapsulation violation in external call sites is corrected.

## Verification

249+ tests must continue to pass. Run focused:

```bash
uv run pytest tests/unit/test_project_graph.py \
    tests/unit/mcp/tools/test_dependency_analysis_tool.py \
    tests/unit/mcp/tools/test_smart_context_tool.py \
    tests/unit/mcp/tools/test_safe_to_edit_tool.py \
    -v --tb=short
```
