# Spec: Expose Remaining MCP Tool Private Attrs as Public API

## Status
`APPROVED`

## Branch
`feature/code-intelligence-architecture`

## Context
The stacked PRs (#203–#206) on the `develop` branch exposed `get_call_graph()` /
`call_graph_initialized` / `get_cache()` / `cache_initialized` for five tools:
`CodeGraphNavigateTool`, `CodeGraphImpactTool`, `CodeGraphOverviewTool`,
`CodeGraphVisualizeTool`, `CodeGraphQueryTool`, and `CodeGraphCallTool`.

The `feature/code-intelligence-architecture` branch has THREE additional tools that
were not covered (TSA dogfood scan found them via `--callers _get_call_graph`):

| Tool class | File | Missing public API |
|---|---|---|
| `CodeGraphRelationToolMixin` | `mcp/tools/codegraph_relation_tool.py` | `get_call_graph()`, `call_graph_initialized` |
| `CodeGraphPRReviewTool` | `mcp/tools/codegraph_pr_review_tool.py` | `get_call_graph()`, `call_graph_initialized` |
| `ASTCacheTool` | `mcp/tools/ast_cache_tool.py` | `get_cache()`, `cache_initialized` |

## Test violations (found via TSA `--callers _get_call_graph`)

- `tests/unit/test_callers_callees_tools.py`: 6 violations (CallersTool + CalleesTool)
- `tests/unit/test_ast_cache_tool.py`: 5 violations (ASTCacheTool)
- `tests/unit/test_call_graph_tool.py`: multiple violations (CodeGraphCallTool — same as PR #206)

## Design

Same duck-typed protocol used for all other tools:
```python
def get_call_graph(self) -> CallGraph:
    """Public alias for _get_call_graph() — use this instead of accessing _call_graph."""
    return self._get_call_graph()

@property
def call_graph_initialized(self) -> bool:
    """True if the call graph has been lazily initialized."""
    return self._call_graph is not None
```

For `CodeGraphRelationToolMixin`: adding to the Mixin automatically propagates to
`CodeGraphCallersTool` and `CodeGraphCalleesTool` without touching either.

## Constraints
- MCP defaults TOON → DO NOT CHANGE
- Do NOT rename or remove `_get_call_graph()` — it is the implementation
- `# noqa: SLF001` for test setup writes (priming state before reset-test)
