# Code/Docs Knowledge Graph

TSA can materialize a whole-project code and documentation knowledge graph from
the existing SQLite AST cache and unified edge store.

## Storage Roles

- SQLite remains the canonical parser cache: AST rows, FTS5 search, file hashes,
  and compatibility for existing tools.
- LadybugDB is the preferred embedded graph mirror for interactive traversal:
  install with `tree-sitter-analyzer[graph]`. The default
  `--knowledge-graph-backend auto` writes a LadybugDB mirror when the extra is
  installed, plus a JSON fallback.
- The knowledge graph JSON sidecar remains the stable export/fallback format and
  is written under the local `.ast-cache` directory.

LadybugDB is a rebuildable mirror, not the canonical parser cache. The writer
uses CSV `COPY` into a fresh temporary database and swaps it into
`.ast-cache/knowledge-graph.lbug` only after the import succeeds. This avoids
row-by-row Cypher inserts, keeps stale WAL files from surviving a rebuild, and
falls back to the slower insert path only if `COPY` is unavailable on the local
LadybugDB build. On this repository's 100,000-node / 99,839-edge sidecar, the
LadybugDB mirror import completed in 1.805 seconds on 2026-06-23.

Materialization is uncapped by default: `--knowledge-graph-max-nodes 0` and
`--knowledge-graph-max-edges 0` mean "store the whole graph." Browser/API
views still use LOD and `max_nodes`/`max_edges` response caps so large projects
are explored in slices instead of rendered all at once.

Scale benchmark results for synthetic Java-shaped graphs are tracked in
[`docs/knowledge-graph-scale-benchmark.md`](../knowledge-graph-scale-benchmark.md).
The 200,000-file run materialized 602,000 nodes and 1,000,000 edges into
LadybugDB in 5.418 seconds.

## CLI

```bash
uv run python -m tree_sitter_analyzer --knowledge-graph-index --format json
uv run python -m tree_sitter_analyzer --knowledge-graph-index \
  --knowledge-graph-index-mode build \
  --knowledge-graph-backend auto \
  --format json
uv run python -m tree_sitter_analyzer --knowledge-graph-serve
uv run python -m tree_sitter_analyzer --knowledge-graph-export \
  --knowledge-graph-lod file \
  --knowledge-graph-export-max-nodes 10000 \
  --format json
```

`update` mode uses the content-hash incremental sync path and then rebuilds the
materialized graph from persisted rows. It deliberately performs a full-project
safe scan rather than honoring a low `max_files` cap, because a low cap in the
underlying incremental sync engine can make old indexed files look deleted.

## MCP Facades

- `index action=knowledge` builds, updates, or reports status.
- `viz action=knowledge` exports Graphology/Sigma.js JSON, raw JSON, or a compact
  summary.

## Graph Contents

Current node kinds include packages, files, Markdown documents, and indexed
symbols such as classes, functions, methods, constants, and variables.

Current edge kinds include `contains`, persisted code relationships from the
unified edge store (`calls`, `imports`, `extends`, `implements`, and related
kinds), and `doc_links` from Markdown file references.

## Visualization

`--knowledge-graph-serve` starts the local interactive Graph Studio service.
On startup it runs the same incremental update path as
`--knowledge-graph-index --knowledge-graph-index-mode update`, refreshes the
JSON fallback and LadybugDB mirror when needed, then opens the browser service.
Its API prefers LadybugDB for node details and neighborhood traversal, then
falls back to the JSON sidecar when LadybugDB is unavailable.

`--knowledge-graph-export-format graphology` emits Graphology-compatible JSON
with deterministic positions and node styling, suitable for Sigma.js or another
programmatic viewer. `--knowledge-graph-export-format html` emits a standalone
canvas viewer for people: pan/zoom, search, kind filters, node details, Markdown
doc links, file relationships, and code edges all use the same capped LOD
payload. `--knowledge-graph-export-format uml` emits Mermaid UML-style text;
select `--knowledge-graph-uml-kind class|package|component|sequence` for class
relationships, package dependencies, component/file/doc dependencies, or a call
sequence diagram from `calls` edges. Use `--knowledge-graph-lod
package|file|symbol|docs` to control level of detail and
`--knowledge-graph-focus TEXT` for focused subgraphs.
