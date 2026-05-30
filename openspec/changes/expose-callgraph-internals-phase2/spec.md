# Spec: Expose CallGraph Internal Methods — Phase 2

## Problem

`TestCallGraphInternalMethods` in `test_call_graph_integration.py` directly accesses
private `CallGraph` methods and attributes:

| Private access | File:line |
|---|---|
| `cg._find_enclosing_func(file_funcs, line)` | `test_call_graph_integration.py:232,241,249` |
| `cg._resolve_callee(call, file, imports)` | `test_call_graph_integration.py:258,264,271` |
| `cg._func_by_name["foo"].append(ref)` | `test_call_graph_integration.py:255,262` |
| `cg._is_excluded(path)` | `test_call_graph_integration.py:277` |
| `cg._iter_source_files(exts)` | `test_call_graph_integration.py:295` |
| `cg._built` | `test_call_graph_integration.py:42,68` |

`test_call_graph_cached.py` adds more violations:

| Private access | File:line |
|---|---|
| `cg._built = True` | `test_call_graph_cached.py:354` |
| `cg._functions = []` | `test_call_graph_cached.py:357` |
| `cg._call_edges = []` | `test_call_graph_cached.py:358` |
| `cg._func_by_name = {}` | `test_call_graph_cached.py:359` |
| `cg.call_edges() is cg._call_edges` | `test_call_graph_cached.py:394` |
| `cg.function_refs() is cg._functions` | `test_call_graph_cached.py:500` |

## Solution

### Phase 1 — Add public aliases on `CallGraph`

Add four public method aliases in `call_graph.py`:

```python
def find_enclosing_func(self, file_funcs, line_number):
    """Public alias for _find_enclosing_func."""
    return self._find_enclosing_func(file_funcs, line_number)

def resolve_callee(self, call, current_file, imports):
    """Public alias for _resolve_callee."""
    return self._resolve_callee(call, current_file, imports)

def is_excluded(self, path):
    """Public alias for _is_excluded."""
    return self._is_excluded(path)

def iter_source_files(self, extensions):
    """Public alias for _iter_source_files."""
    return self._iter_source_files(extensions)

@property
def is_built(self) -> bool:
    """True after build() has been called at least once."""
    return bool(self._built)
```

### Phase 2 — Update tests

- Replace `cg._find_enclosing_func(...)` → `cg.find_enclosing_func(...)`
- Replace `cg._resolve_callee(...)` → `cg.resolve_callee(...)`
- Replace `cg._is_excluded(...)` → `cg.is_excluded(...)`
- Replace `cg._iter_source_files(...)` → `cg.iter_source_files(...)`
- Replace `cg._built` reads → `cg.is_built`
- Replace `cg.call_edges() is cg._call_edges` → equality check (data contract, not identity)
- Replace `cg.function_refs() is cg._functions` → equality check

The write-to-private pattern (`cg._built = True`, `cg._functions = []`, etc.) in
`test_call_graph_cached.py` is for test isolation (bypassing `build()`).  
Keep these writes to private attrs — they are test-only setup, not production violation.
Note these with inline `# noqa: SLF001` or a comment.

## Scope

- **Touch**: `tree_sitter_analyzer/call_graph.py`, `tests/unit/test_call_graph_integration.py`,
  `tests/unit/test_call_graph_cached.py`
- **No other files changed**

## Validation

```bash
uv run pytest tests/unit/test_call_graph_integration.py tests/unit/test_call_graph_cached.py -x -q
uv run python -m tree_sitter_analyzer --change-impact --format json
```
