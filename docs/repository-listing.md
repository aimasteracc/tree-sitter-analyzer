# Repository listing

The text in this file is the project's published listing: the GitHub repository
description, its topics, and the MCP registry entry in `server.json`. It is
versioned here so a release can be checked before it ships, and so the claim
rules below have something to bind to.

Agents and users read this text before they read the README, so it is held to
the same standard as the README: it advertises only current capabilities, and
publishes no quantitative competitive claim that the claim registry does not
authorize.

## GitHub description

```
Cross-language-safe code-intelligence MCP for AI agents: 13 languages, family-gated call graph, blast radius, health grading, 8 facade tools, JSON envelopes, 100% local. Run miswire-audit on your repo.
```

The language count must match the generated inventory in
`README.md` (`13 pipeline-registered`). `server.json` carries a shorter variant
of the same text for the MCP registry.

## Topics

```
ai, ai-agents, ai-coding, anthropic, ast, call-graph, claude-code, code-analysis, code-intelligence, codegraph, cross-language, developer-tools, llms, mcp, mcp-server, static-analysis, tree-sitter, tree-sitter-analyzer, vibe-coding
```

## Rules

- **No removed capability.** A listing must not name an output format, tool, or
  wrapper that a released breaking change removed. `CHANGELOG.md` is the record
  of what was removed; `TOON`, `search-content`, and `find-and-grep` are gone as
  of 1.30.0.
- **No unauthorized quantitative claim.** A ratio or competitor comparison may
  appear only when `benchmarks/codegraph_compare/claim_registry.json` carries a
  matching claim at evidence level `E4`. Below `E4` the measured detail belongs
  in its benchmark report, where it is read together with its methodology,
  corpus, and measurement date — not in a one-line listing.
- **Counts come from the generator.** A language or tool count in a listing
  restates the generated inventory; it is not maintained by hand.

`tests/governance/test_repository_listing_contract.py` enforces the first two
rules against this file and `server.json`.
