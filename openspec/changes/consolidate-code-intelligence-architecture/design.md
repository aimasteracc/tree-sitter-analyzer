# Design

## Shared Resolver Layers

`callee_resolution.py` owns the cross-file callee matching algorithm. Call graph,
cross-file resolver, and Synapse resolution call this shared resolver instead of
maintaining local copies.

`codegraph_query_backend.py` owns shared definition and codegraph lookup behavior.
`xref.py`, `symbol_resolver.py`, and MCP codegraph query paths delegate through this
backend where practical.

`function_extraction.py` owns AST function and call extraction helpers. Cache edge
extraction imports from this module directly, so cache extraction does not depend on
the higher-level call graph module.

## Synapse Context Loading

Synapse resolver context is loaded lazily through properties. Context construction is
cached in a bounded in-process LRU keyed by the cache database identity:

- database path
- mtime nanoseconds
- file size

This keeps repeated resolver calls cheap while invalidating naturally when the cache
database changes.

## Semantic Search

`semantic_search.py` implements a deterministic local symbol-vector search. It builds
token-count vectors from symbol names, kinds, signatures, containers, and source path
fragments, then ranks candidates by cosine similarity.

The first slice is intentionally offline and dependency-free. This gives MCP and CLI
callers stable behavior in air-gapped or local-only environments, while leaving room
for a future persistent vector index or hybrid FTS-plus-vector reranker.

## Query DSL Integration

The codegraph query DSL supports `semantic("query", limit=N)` as a chainable seed or
expansion step. Results are normalized into the same symbol result shape used by
existing lookup paths, with an additional `semantic_score` field.

The DSL also supports `uml(...)` as an answer-pack facet. It renders the current
query selection and caller/callee relationships as Mermaid flowchart text. This keeps
UML usable from the same chain that found the symbols, instead of forcing agents to
switch to a separate tool and reconstruct context.

## Compatibility Wrappers

Existing dedicated MCP tools remain registered for compatibility while their shared
execution concerns move into smaller backend modules. The first slice keeps
`codegraph_callers` and `codegraph_callees` as public wrappers, but shares cache
selection, graph fallback, stale-cache detection, resolution classification, and
activation lookup through a relation helper module.

## Invariants

- There is one shared implementation home for callee resolution.
- Cache call-edge extraction must not import from `call_graph.py`.
- Synapse convenience context must be lazy and reuse an LRU entry for repeated reads.
- Semantic search must work without network access or external embedding services.
- Chain-based UML must reuse existing Mermaid renderers and must not create another
  MCP tool entry point.
- Compatibility wrappers must not reintroduce duplicated cache/bootstrap logic after
  a shared backend exists.
