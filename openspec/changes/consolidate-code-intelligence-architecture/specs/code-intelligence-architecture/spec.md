# Code Intelligence Architecture Specification

## ADDED Requirements

### Requirement: Shared callee resolution

The analyzer MUST resolve cross-file callees through a shared resolver implementation.

#### Scenario: call graph and Synapse resolve through the same algorithm

- **WHEN** call graph, cached call graph, cross-file resolver, or Synapse resolution
  needs to match a call to a definition
- **THEN** it MUST delegate to the shared callee resolver
- **AND** it MUST NOT keep an independent local matching algorithm

### Requirement: Shared definition lookup backend

Definition and xref lookup MUST use a shared codegraph lookup backend where cache
schema access is required.

#### Scenario: xref and symbol resolver inspect cache definitions

- **WHEN** a caller resolves definitions from AST cache data
- **THEN** the lookup MUST go through the shared codegraph query backend
- **AND** FTS, normalized symbol rows, and legacy JSON rows MUST be handled consistently

### Requirement: Shared AST function extraction

AST function and call extraction MUST live outside the call graph orchestration module.

#### Scenario: AST cache extracts call edges

- **WHEN** AST cache extraction extracts call edges
- **THEN** it MUST import extraction helpers from the shared function extraction module
- **AND** it MUST NOT depend on `call_graph.py`

### Requirement: Lazy Synapse context

Synapse resolver context MUST load expensive cache-derived indexes lazily.

#### Scenario: repeated resolver context access

- **WHEN** a resolver context is requested repeatedly for the same unchanged cache
- **THEN** the context MUST reuse a bounded LRU entry
- **AND** expensive indexes MUST only be loaded when their property is first accessed

### Requirement: Offline semantic symbol search

Codegraph query MUST provide an offline semantic search step for symbol discovery.

#### Scenario: semantic query seeds a codegraph chain

- **WHEN** a user runs `semantic("user formatting", limit=5)`
- **THEN** the analyzer MUST rank matching symbols by local semantic similarity
- **AND** it MUST return normalized symbol results with `semantic_score`
- **AND** it MUST NOT require network access or external embedding services

### Requirement: Chain-based UML output

Codegraph query MUST render UML-style Mermaid output from the current chain state.

#### Scenario: relation query renders Mermaid flowchart

- **WHEN** a user runs `search("run").callees().uml(direction="TD")`
- **THEN** the analyzer MUST include a UML facet with Mermaid flowchart text
- **AND** the diagram MUST use the current query symbols and caller/callee edges
- **AND** it MUST reuse the existing Mermaid rendering helpers
- **AND** it MUST NOT add a new MCP tool entry point for this chain output

### Requirement: Thin compatibility wrappers

Dedicated legacy MCP tools MUST delegate shared execution concerns to backend helpers
when a hub or shared relation layer exists.

#### Scenario: caller and callee tools share relation bootstrap

- **WHEN** `codegraph_callers` or `codegraph_callees` needs cache selection or graph fallback
- **THEN** it MUST use the shared relation helper
- **AND** the public tool names and response fields MUST remain compatible
- **AND** cache/bootstrap logic MUST NOT be copied independently into both wrappers
