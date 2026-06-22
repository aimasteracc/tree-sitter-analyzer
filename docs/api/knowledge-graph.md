# Code/Docs Knowledge Graph

TSA can materialize a whole-project code and documentation knowledge graph from
the existing SQLite AST cache and unified edge store.

## Storage Roles

- SQLite remains the canonical parser cache: AST rows, FTS5 search, file hashes,
  and compatibility for existing tools.
- The knowledge graph JSON sidecar is the default visualization/program export
  and is written under the local `.ast-cache` directory.
- LadybugDB is an optional embedded graph mirror for Cypher traversal:
  install with `tree-sitter-analyzer[graph]` and use `--knowledge-graph-backend ladybug`
  or `hybrid`.

## CLI

```bash
uv run python -m tree_sitter_analyzer --knowledge-graph-index --format json
uv run python -m tree_sitter_analyzer --knowledge-graph-index \
  --knowledge-graph-index-mode build \
  --knowledge-graph-backend hybrid \
  --format json
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

`--knowledge-graph-export-format graphology` emits Graphology-compatible JSON
with deterministic positions and node styling, suitable for Sigma.js or another
programmatic viewer. `--knowledge-graph-export-format html` emits a standalone
canvas viewer for people: pan/zoom, search, kind filters, node details, Markdown
doc links, file relationships, and code edges all use the same capped LOD
payload. Use `--knowledge-graph-lod package|file|symbol|docs` to control level
of detail and `--knowledge-graph-focus TEXT` for focused subgraphs.
