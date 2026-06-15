<!-- Generated: 2026-05-22 -->
# Codemaps

Token-lean architecture documentation, optimized for AI context loading.
Each map under ~1k tokens — load only the one(s) you need.

## Index

| File | Scope |
|---|---|
| [architecture.md](./architecture.md) | High-level topology · data flow · cross-cutting concerns |
| [mcp-tools.md](./mcp-tools.md) | 8 facade tools + set_project_path registered in `mcp/_tool_registry.py` |
| [cli.md](./cli.md) | CLI flags / commands / `tree-sitter-analyzer` entry points |
| [languages.md](./languages.md) | 21 language plugins + grammar coverage |
| [formatters.md](./formatters.md) | Output formats (TOON / JSON / table / CSV / YAML) |
| [security.md](./security.md) | Boundary enforcement · project root resolution · path validation |

## When to Regenerate

- After major feature additions (new MCP tool, new language plugin, new formatter)
- After refactoring affecting boundaries (mcp/tools/, languages/, formatters/, security/)
- Before onboarding contributors
- After grammar coverage changes (`docs/grammar-coverage*`)

## See Also

- **[AGENTS.md](../../AGENTS.md)** — Agent runtime contracts (pytest setup, MCP/CLI parity)
- **[CLAUDE.md](../../CLAUDE.md)** — Project-specific Claude Code config (swarm, routing, memory)
- **[README.md](../../README.md)** — User-facing quick start (multi-environment MCP configs)
- **[docs/api/mcp_tools_specification.md](../api/mcp_tools_specification.md)** — Full MCP API reference
- **[docs/cli-reference.md](../cli-reference.md)** — Full CLI reference

## Discovery Path for AI Agents

```
1. Read AGENTS.md      → know the test/parity contracts
2. Read CODEMAPS/architecture.md → know the subsystem layout
3. Read CODEMAPS/<area>.md       → load only the area you're touching
4. (only if needed) read full source under tree_sitter_analyzer/<area>/
```
