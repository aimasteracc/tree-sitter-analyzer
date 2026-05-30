# Tasks

- [x] Add `.gitignore` coverage for local runtime artifacts and untrack generated DBs.
- [x] Add shared codegraph query backend for definition lookup.
- [x] Route xref and symbol resolution through the shared backend.
- [x] Add shared callee resolution module.
- [x] Route call graph, cross-file resolver, cached call graph, and Synapse resolution through the shared resolver.
- [x] Add shared function extraction module and decouple AST cache extraction from call graph.
- [x] Add lazy Synapse resolver context with bounded LRU caching.
- [x] Add deterministic local semantic symbol search.
- [x] Expose semantic search through `codegraph_query` DSL as `semantic(...)`.
- [x] Expose Mermaid UML flow output through `codegraph_query` DSL as `uml(...)`.
- [x] Start MCP tool sprawl reduction by sharing callers/callees relation bootstrap.
- [x] Add focused unit tests for architectural invariants and semantic ranking.
- [x] Run change-impact verification.
- [x] Run focused affected tests.
- [x] Run focused coverage tests and patch coverage gate.
- [x] Run full pytest suite.

## Follow-ups

- [x] Decide whether to persist semantic vectors for very large repositories.
  **Decision (2026-05-28):** No — keep in-memory. Disk persistence adds staleness complexity;
  revisit only if profiling shows startup cost > 500ms on repos > 100k symbols.
- [x] Add agent-facing codemap examples for `semantic(...)`.
- [x] Add agent-facing codemap examples for chain-based `uml(...)`.
- [x] Evaluate hybrid FTS plus semantic reranking once resolver consolidation lands.
  **Decision (2026-05-28):** Defer. Resolver consolidation is complete; semantic DSL alone
  provides sufficient accuracy for current use cases. Revisit if recall deficiency is
  reported via codegraph_search feedback.
