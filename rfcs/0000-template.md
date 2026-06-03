# RFC-NNNN: <Title>

- **Status**: draft
- **Author(s)**: @username
- **Created**: YYYY-MM-DD
- **Last updated**: YYYY-MM-DD
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/...`
  - `tests/...`

## Summary

One paragraph. What is this RFC proposing, in plain language?

## Motivation

Why are we doing this? What problem are we solving? Who feels the pain today
(humans? AI agents?) and what outcome do we want? Be concrete — numbers help
(turns, tokens, latency, dogfood deltas).

## Detailed design

The bulk of the RFC. Specify the change so someone other than you can
implement it.

- API change → proposed API in **Python** syntax with docstrings.
- Storage/schema change → schema + migration plan (ast_cache schema version).
- Query-language change → grammar (EBNF) + examples.
- MCP surface change → tool/facade name, `action`, params, return shape.

### Sub-sections as needed

#### Data structures

#### Algorithms

#### MCP surface (facade + action)

#### Error handling

#### Concurrency / async

## Three-Surface impact (CLI ↔ MCP parity)

TSA holds a hard CLI↔MCP parity rule. State the CLI flag, the MCP
facade/action, and confirm they stay 1:1. If a surface is intentionally
asymmetric (e.g. TOON default on MCP, JSON on CLI), say so and cite the
locked design decision.

## Drawbacks

What are the costs? Why might we not do this? RFCs without drawbacks are
under-considered.

## Alternatives

- **Alternative A**: … — Pros / Cons / Rejected because …
- **Alternative B**: …

## Prior art

What can we learn from? Cite and compare — note where we adopt and where we
diverge:

- Other code-intelligence systems (codegraph, rust-analyzer, Sourcegraph, mycelium)
- Academic papers, other projects (tree-sitter, Salsa, DuckDB, …)

## Test plan (RED-first)

The failing tests this RFC will be implemented against (Charter-style TDD).
Unit / integration / e2e / dogfood.

## Acceptance criteria

Checkboxes that flip `[ ]` → `[x]` as the implementation lands. The RFC is not
"shipped" until all are checked and the linked PR is merged.

- [ ] …
- [ ] …
- [ ] CLI↔MCP parity test green
- [ ] Docs/CODEMAPS updated

## What this RFC does NOT do (deferred)

Explicitly scope out what is out of scope, so reviewers don't expect it.

## Open questions

Numbered questions for review.
