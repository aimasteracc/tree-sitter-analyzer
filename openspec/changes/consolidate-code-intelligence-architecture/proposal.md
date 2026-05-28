# Consolidate Code Intelligence Architecture

## Problem

Code intelligence features have grown through parallel implementations:

- callee resolution exists in multiple modules
- definition lookup is split between symbol and xref paths
- AST call extraction is duplicated between cache extraction and call graph code
- Synapse resolver context is loaded eagerly
- codegraph search is limited to lexical FTS/B-tree lookup

This makes new query features such as chain-style traversal and UML output harder to
extend safely, because each feature can accidentally pick a different resolver path.

## Goals

- Establish one shared home for callee resolution.
- Establish one shared backend for definition and codegraph symbol lookup.
- Establish one shared function/call extraction helper for AST cache and call graph.
- Make Synapse resolver context lazy and bounded by an in-process LRU cache.
- Add an offline semantic search step to the codegraph query DSL.
- Make UML/Mermaid output available from the chained query answer-pack.
- Preserve CLI/MCP defaults and existing output contracts.

## Non-Goals

- Replace local search with a remote embedding service.
- Change MCP default output from TOON to JSON.
- Change project-root canonicalisation behavior.
- Rewrite the entire MCP tool surface in this change.
- Remove the standalone UML tool before chain-based UML has public usage evidence.

## Verification Strategy

- Write focused unit tests for each architectural invariant before or alongside code.
- Use `--change-impact` to select the affected verification surface.
- Run focused tests with coverage and the local patch coverage gate for Python changes.
- Run the default full suite before the slice is considered complete.
