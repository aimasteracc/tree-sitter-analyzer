# RFC-0006: Progressive Disclosure for `nav action=context` / `codegraph_context`

- **Status**: implemented
- **Author(s)**: @backend-architect-agent
- **Created**: 2026-06-05
- **Last updated**: 2026-06-05
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/codegraph_context_tool.py`
  - `tree_sitter_analyzer/cli/argument_groups/_analysis_graph_nav.py`
  - `tree_sitter_analyzer/cli/commands/mcp_commands/_specs_extended.py`
  - `tests/unit/test_codegraph_context_tool.py`
  - `tests/unit/cli/test_mcp_commands.py`

## Summary

Add a boolean `include_graph` parameter (default `false`) to `nav action=context` /
`codegraph_context`. When `false` (the new default), the response omits the flat `edges`
list and replaces the verbose per-node dicts with a compact CG-style related-symbols list
(`file: name:line` entries, no bodies). Entry points and code blocks — the parts that
actually answer the agent's question — are preserved intact. When `true`, the full nodes +
edges are returned exactly as today. Totals and a `next_step` hint advertising the flag are
always present so the agent knows more graph is available on demand.

## Motivation

The PM measured the payload sizes for the query "ASTCache index_project indexing"
(max_nodes=30) and found a 3.8× gap between TSA and CodeGraph:

| Segment | TSA chars | % of total |
|---|---|---|
| nodes (30 items) | 5,373 | 32% |
| edges (37 items) | 4,850 | 29% |
| code_blocks (5 items) | 4,585 | 27% |
| entry_points | 894 | 5% |
| related_files | 470 | 3% |
| other fields | ~631 | 4% |
| **Total TSA** | **~16,803** | |
| **Total CodeGraph** | **~4,400** | |

Nodes + edges account for 61% of the TSA payload. Yet an agent answering "how does X work"
needs entry points and code blocks (the 32% that carries the actual source), not a flat
adjacency list. CodeGraph returns a compact "Related Symbols" list (`file: name:line, name:line`)
with no bodies and **no edge list at all** — and agents rate it more useful because the
signal-to-noise ratio is higher.

The token cost gap is the last axis where CG beats TSA. Closing it to ≤CG size for the
default call brings TSA to cost parity while keeping the full graph available opt-in.

## Detailed design

### New parameter

```python
"include_graph": {
    "type": "boolean",
    "description": (
        "When false (default) return a compact related-symbols list instead of "
        "the full nodes/edges graph. Set true to get the complete graph for "
        "visualization or impact analysis."
    ),
    "default": False,
}
```

### Response shape when `include_graph=false` (default)

```json
{
  "success": true,
  "verdict": "INFO",
  "task": "...",
  "candidates": [...],
  "entry_points": [...],
  "related_symbols": [
    {"file": "ast_cache.py", "symbols": ["ASTCache:82", "index_project:280"]},
    {"file": "codegraph_context_tool.py", "symbols": ["CodeGraphContextTool:52"]}
  ],
  "code_blocks": [...],
  "related_files": [...],
  "stats": {
    "entry_points": 4,
    "entry_points_total": 4,
    "nodes_total": 30,
    "edges_total": 37,
    "code_blocks": 5
  },
  "agent_summary": {
    "summary_line": "...",
    "verdict": "INFO",
    "next_step": "Answer from code_blocks now. For the full call graph add include_graph=true."
  }
}
```

Key differences from the current default response:
- `nodes` and `edges` fields are **absent** (omitted entirely to save chars)
- `related_symbols` is a new compact list grouped by file: `name:line` entries
- `stats` still exposes `nodes_total` and `edges_total` so the agent knows graph is available
- `next_step` names the `include_graph=true` flag explicitly

### Response shape when `include_graph=true`

Identical to today's response (full `nodes` + `edges` + all stats). The `related_symbols`
field is also present for symmetry. Back-compat: existing callers that pass no `include_graph`
get the lean response; callers that explicitly set `include_graph=true` get the full graph.

### Compact related-symbols format

```
grouped by file, sorted by line:
  {"file": "ast_cache.py", "symbols": ["ASTCache:82", "index_project:280"]}
```

This mirrors CodeGraph's "Related Symbols" format: `file: name:line, name:line`. No
language, no kind, no end_line, no id — just name and line number per symbol. The agent
has the file path to jump to and the line to navigate to; that is enough for follow-up
calls. Bodies are in `code_blocks`.

### Algorithm

In `execute()`, after the existing node/edge computation:

```python
include_graph = bool(arguments.get("include_graph", False))
related_symbols = _build_related_symbols(nodes)   # always built (tiny cost)

if include_graph:
    result = {... "nodes": nodes, "edges": edges, "related_symbols": related_symbols, ...}
else:
    result = {
        ... "related_symbols": related_symbols,
        # nodes/edges omitted
        "stats": {
            "entry_points": len(entry_points),
            "entry_points_total": total_entry_points,
            "nodes_total": total_nodes,
            "edges_total": total_edges,
            "code_blocks": len(code_blocks),
        },
        ...
    }
```

`_build_related_symbols(nodes)` groups the full node set by file, produces
`{"file": ..., "symbols": ["name:line", ...]}` entries, sorted by (file, line).

### MCP surface

`codegraph_context` tool schema gains `include_graph: boolean, default: false`.
`nav action=context` bespoke route passes `include_graph` through to `context_inner.execute()`.
The existing `inner_keys` tuple in `_context_route` is extended with `"include_graph"`.

### Error handling

`include_graph` is coerced with `bool()` — no validation error for string `"true"` etc.
(callers may pass strings; tolerate silently).

### Concurrency / async

No change — `execute()` is already `async`. The compact path skips the edge-cap loop
(cheaper) and calls one new pure function `_build_related_symbols`.

## Three-Surface impact (CLI ↔ MCP parity)

| Surface | Parameter | Default | Notes |
|---|---|---|---|
| MCP `codegraph_context` | `include_graph` (bool) | `false` | New |
| MCP `nav action=context` | `include_graph` (bool) | `false` | Passed through bespoke route |
| CLI `--codegraph-context` | `--codegraph-context-include-graph` (store_true) | `False` | New flag |

The CLI flag maps to `include_graph=True` when present, `False` when absent — identical
semantics to the MCP default. The one allowed asymmetry is the existing TOON-vs-JSON
output format (CLAUDE.md §1, locked), which this RFC does not touch.

## Drawbacks

- Adds one new boolean parameter and a new `related_symbols` field to the response.
  Existing callers that depended on `nodes`/`edges` being present in the default call
  will need to add `include_graph=true`. This is justified because: (a) CG never returned
  edges in its default context call; (b) the lean path is strictly better for the 99% case.
- The `related_symbols` field is new — a minor schema addition, not a breaking change.

## Alternatives

- **Alternative A: keep nodes/edges, just cap them harder** — Tried (current inline caps).
  Still 61% overhead because even 12-node + 12-edge dumps are verbose vs. name:line lists.
  Rejected: the format mismatch with CG persists.
- **Alternative B: separate `codegraph_context_lean` tool** — More surface area, harder
  to keep in parity. Rejected: one tool with a flag is cleaner.
- **Alternative C: TOON format compression** — TOON already saves 50-70% over JSON.
  The gap being measured IS the TOON-format payload. Further TOON compression of nodes/edges
  is a diminishing return; omitting them entirely is a step-change.

## Prior art

- **CodeGraph `codegraph_context`**: returns entry_points + compact related-symbols list
  (`file: name:line`) + code blocks. No edge list. This RFC adopts that contract as the
  default, keeping the full graph opt-in.
- **LSP incremental disclosure**: `textDocument/hover` returns a summary; callers drill
  down with `textDocument/definition` / `textDocument/references`. Same progressive pattern.
- **Sourcegraph**: compact "find references" view (name + file + line) with "load more" —
  the same progressive disclosure contract.

## Test plan (RED-first)

Tests written BEFORE implementation, verified RED against current code:

1. **`test_context_lean_default_omits_nodes_edges`** — default call (`include_graph`
   absent) → response has no `nodes` key and no `edges` key; has `related_symbols`;
   has `code_blocks`; payload chars materially smaller than `include_graph=true` call.
   **RED** on current code (current code always returns nodes/edges).

2. **`test_context_include_graph_true_returns_full_nodes_edges`** — `include_graph=true`
   → `nodes` present and non-empty; `edges` key present; back-compat.

3. **`test_context_lean_stats_advertise_graph_totals`** — lean call → `stats` contains
   `nodes_total` and `edges_total`; `next_step` mentions `include_graph`.

4. **`test_context_related_symbols_grouped_by_file`** — `related_symbols` format:
   list of `{"file": str, "symbols": [str]}` where each symbol is `"name:line"`.

5. **CLI parity** — `--codegraph-context-include-graph` flag present in parser and wired
   to `include_graph` in `build_tool_args`.

## Acceptance criteria

- [x] `include_graph` parameter added to `codegraph_context` tool schema with default `false`
- [x] Default response (no `include_graph`) omits `nodes`/`edges`, includes `related_symbols`
- [x] `include_graph=true` returns full nodes + edges (back-compat)
- [x] `stats` always includes `nodes_total` and `edges_total`
- [x] `next_step` names the `include_graph=true` flag when graph is available
- [x] `related_symbols` field present in both lean and full responses
- [x] Default payload ≥40% smaller than `include_graph=true` payload
- [x] `--codegraph-context-include-graph` CLI flag added and wired
- [x] CLI↔MCP parity test green
- [x] `uv run ruff check` clean
- [x] `uv run mypy tree_sitter_analyzer/mcp/tools/codegraph_context_tool.py` clean
- [x] `uv run pytest tests/unit/test_codegraph_context_tool.py tests/unit/test_agent_contracts.py tests/unit/cli/ -q` green
- [x] `uv run pytest tests/unit/ -q -n auto` full suite green

## What this RFC does NOT do (deferred)

- Does not change the `output_format` default (TOON stays TOON — CLAUDE.md §1 locked).
- Does not change the `nodes`/`edges` data structure when `include_graph=true` (back-compat).
- Does not add pagination or streaming for large graphs.
- Does not touch any other nav facade actions.

## Open questions

1. Should `related_symbols` be included in the TOON format verbatim, or should TOON
   render it as a compact markdown table? Answer: TOON passes through the dict as-is;
   no special treatment needed for this RFC.
