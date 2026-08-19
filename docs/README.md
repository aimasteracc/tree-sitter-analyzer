# tree-sitter-analyzer — Documentation

Index of all project documentation. Start here, then jump to the area you need.
For the project overview and install-and-go instructions, see the
[top-level README](../README.md) ([日本語](../README_ja.md) / [中文](../README_zh.md)).

> **Agents**: read [`AGENTS.md`](../AGENTS.md) first, then the matching
> [`CODEMAPS/`](CODEMAPS/) topology map. Those maps are kept in sync with the
> code registries — prefer them over scanning the source tree.

## Getting Started

| Doc | What it covers |
|---|---|
| [installation.md](installation.md) | Install via pip/uv, system dependencies (fd, ripgrep) |
| [cli-reference.md](cli-reference.md) | All CLI flags and commands |
| [features.md](features.md) | Feature overview (languages, token optimisation, UML diagrams) |
| [index-lifecycle.md](index-lifecycle.md) | Index operations: build / full / sync / auto, partial-cache trap, health check |
| [smart-workflow.md](smart-workflow.md) | The SMART five-step workflow for AI-assisted analysis |

## Output Formats

| Doc | What it covers |
|---|---|
| [toon-format-guide.md](toon-format-guide.md) | TOON — the token-efficient default for MCP output |
| [format_specifications.md](format_specifications.md) | Canonical output schema |
| [format-testing-guide.md](format-testing-guide.md) | How output formats are tested |
| [sql-format-guide.md](sql-format-guide.md) | SQL analysis output |

## Architecture & Internals

| Doc | What it covers |
|---|---|
| [architecture.md](architecture.md) | High-level system design |
| [CODEMAPS/](CODEMAPS/) | Registry-synced topology maps (MCP tools, CLI, languages, formatters, security) |
| [api/mcp_tools_specification.md](api/mcp_tools_specification.md) | MCP tool API reference |
| [MIGRATION.md](MIGRATION.md) | Version migration notes |
| [../rfcs/](../rfcs/) | RFCs — design proposals for substantial changes |

## Contributing & Development

| Doc | What it covers |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guide (GitFlow, PR flow, quality gates) |
| [CONTENT_GUIDELINES.md](CONTENT_GUIDELINES.md) | Rules for externally published content (articles, GitHub metadata) — prohibited citations |
| [developer_guide.md](developer_guide.md) | Developer setup and internals |
| [new-language-support-checklist.md](new-language-support-checklist.md) | ⭐ Adding a new language plugin |
| [ai-coding-rules.md](ai-coding-rules.md) | Rules for AI-assisted contributions |
| [pre-commit-setup.md](pre-commit-setup.md) | Pre-commit hooks |
| [debugging_guide.md](debugging_guide.md) | Debugging techniques |
| [troubleshooting_guide.md](troubleshooting_guide.md) | Common problems and fixes |

## Testing

| Doc | What it covers |
|---|---|
| [TESTING.md](TESTING.md) | Testing overview |
| [regression-testing-guide.md](regression-testing-guide.md) | Golden-master regression tests |
| [grammar-coverage-framework.md](grammar-coverage-framework.md) | Grammar coverage framework |
| [mcp_compatibility_test_standard.md](mcp_compatibility_test_standard.md) | MCP compatibility test standard |
| [corpus-generator.md](corpus-generator.md) | Test corpus generation |

## CI/CD

| Doc | What it covers |
|---|---|
| [ci-cd-overview.md](ci-cd-overview.md) | CI/CD pipeline overview |
| [ci-cd-troubleshooting.md](ci-cd-troubleshooting.md) | Fixing CI failures |
| [ci-cd-secrets-reference.md](ci-cd-secrets-reference.md) | Required CI secrets |

## Operations & History

| Doc | What it covers |
|---|---|
| [sql-cross-platform-compatibility.md](sql-cross-platform-compatibility.md) | SQL grammar cross-platform notes |
| [POSTMORTEM_v1.13.md](POSTMORTEM_v1.13.md) | v1.13 release postmortem (anti-patterns referenced by AGENTS.md) |
| [AUTONOMOUS_DEV.md](AUTONOMOUS_DEV.md) | Autonomous-development workflow notes |
| [agent-tooling-gap-report.md](agent-tooling-gap-report.md) | Agent tooling gap analysis |

## Vision & Articles

| Doc | What it covers |
|---|---|
| [VISION-proprioception-scenarios.md](VISION-proprioception-scenarios.md) | TSA as proprioception for AI agents — scenarios A–E (design lives in `rfcs/0025`) |
| [articles/polyglot-miswire-article.md](articles/polyglot-miswire-article.md) | Cross-language miswire detection |
| [articles/ast-oracle-shootout.md](articles/ast-oracle-shootout.md) | AST oracle comparison |
| [articles/security-posture.md](articles/security-posture.md) | Security posture walkthrough |
