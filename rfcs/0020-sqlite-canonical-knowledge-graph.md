# RFC-0020: SQLite-Canonical Knowledge Graph

- **Status**: draft
- **Author(s)**: project maintainers
- **Created**: 2026-07-15
- **Last updated**: 2026-07-15
- **Tracking issue**: TBD
- **Affected source paths**:
  - `tree_sitter_analyzer/knowledge_graph/`
  - `tree_sitter_analyzer/mcp/tools/knowledge_graph_tool.py`
  - `tree_sitter_analyzer/cache/indexer.py`
  - `tests/unit/test_knowledge_graph.py`

## Summary

SQLite is the only canonical knowledge-graph index. LadybugDB remains an
optional, rebuildable traversal projection. The persisted
`.ast-cache/knowledge-graph.json` sidecar and its `json`/`hybrid` backend modes
are removed. JSON and TOON remain response encodings, not storage backends.

## Motivation

The previous indexing path could expose three independently updated states:
SQLite AST/edges, a JSON snapshot, and LadybugDB. None shared an atomic commit,
so tools could observe different source versions. Removing the JSON store
eliminates one stale replica and makes the ownership rule explicit.

## Detailed design

- `index.db` owns files, symbols, imports, and graph edges.
- Read/export operations build their bounded projection directly from SQLite.
- LadybugDB is written only when selected and is invalidated after canonical
  SQLite changes.
- `auto` selects LadybugDB when installed and SQLite otherwise.
- The supported storage backend values are `auto`, `sqlite`, and `ladybug`.
- Raw, Graphology, DOT, GraphML, HTML, and UML exports remain available, but no
  export is implicitly persisted as the operational index.

### Error handling

Selecting `ladybug` without its optional dependency returns an explicit error.
Selecting `sqlite` requires no derived graph artifact.

## Three-Surface impact (CLI ↔ MCP parity)

- CLI: `--knowledge-graph-backend auto|sqlite|ladybug`
- MCP: `codegraph_knowledge_index.backend = auto|sqlite|ladybug`
- Python: `open_query_backend()` selects LadybugDB or SQLite.

MCP continues to default responses to TOON and CLI continues to default to
JSON, as required by the locked output-format decision.

## Drawbacks

SQLite fallback queries construct an in-memory projection and can be slower
than reading a precomputed snapshot. LadybugDB remains the intended backend for
large, repeated graph traversals.

## Alternatives

- Keep JSON as a fallback: rejected because it preserves an unversioned replica.
- Make LadybugDB canonical: rejected because it is optional and the parser,
  resolver, incremental invalidation, and non-graph queries already depend on
  SQLite.

## Test plan (RED-first)

- Assert backend schemas reject `json` and `hybrid`.
- Assert `auto` resolves to SQLite when LadybugDB is unavailable.
- Assert read/export operations work directly from SQLite.
- Assert indexing never creates `knowledge-graph.json`.
- Run focused knowledge-graph tests, patch coverage, and the full suite.

## Acceptance criteria

- [x] JSON store implementation and public export removed
- [x] Automatic JSON materialization removed
- [x] Query and export fallback reads SQLite
- [x] CLI and MCP expose only `auto|sqlite|ladybug`
- [x] Focused tests and patch-coverage gate green
- [ ] Full default suite exits successfully within its runtime contract
- [x] Docs/CODEMAPS updated

## What this RFC does NOT do (deferred)

Stable semantic symbol IDs and generation-based atomic index swaps are separate
schema changes and require a follow-up RFC.

## Open questions

None.
