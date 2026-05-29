# 🌳 Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

> **The MCP code-intelligence server for AI agents — fewer tokens, fewer tool calls, 100 % local.**
> Pre-indexed AST cache + 60 MCP tools + 13 curated agent skills + TOON-compressed output.
> Beats CodeGraph on 6-repo head-to-head median (**−11 % cost vs CodeGraph's −4 %**), with a strict CLI superset.
> Now with **BM25-ranked symbol search** across all 60 tools — results sorted by relevance, not file path.

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-18583%20passed-brightgreen.svg)](#-quality--testing)
[![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

---

## Get Started

One-line install for **Claude Code**:

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

Restart your agent, then say: *"Set the project root to my repo and run codegraph_status."*

[Other agents (Cursor, Copilot, Cline, Continue, Claude Desktop, Roo Code) →](#-supported-agents)

---

## Why Tree-sitter Analyzer

* **Token-efficient by default.** Every MCP response uses **TOON** — a tabular JSON variant that cuts payload by ~50-70 % vs raw JSON.
* **Verdict envelopes.** Every response carries `verdict: SAFE | CAUTION | UNSAFE | INFO | WARN | ERROR | NOT_FOUND`, so orchestrators branch on outcomes without re-prompting.
* **Project health grading (A–F).** No other open-source tool grades your whole project on size / complexity / coverage / duplication / dependencies / structure / git-hotspots in one call.
* **13 curated workflows (Skills).** Pre-baked tool subsets for "find symbol", "trace call chain", "score health", "safe-to-edit before refactor", "PR review", etc.
* **5 layers of safety.** `safe_to_edit` + `modification_guard` + constraint DSL + `change_impact` + verdict envelopes — designed so agents *know* before they touch.
* **Beats the leading competitor (CodeGraph) on multiple head-to-head benchmarks.** See below.

---

## Benchmark Results

Headless Claude Code (Haiku 4.5) asked one architecture question per repo. 3 arms: no-MCP / CodeGraph MCP / Tree-sitter Analyzer MCP. Single run per arm — indicative, not statistically settled.

| Codebase | Lang / files | Baseline | CodeGraph | **TSA** | Winner |
|---|---|---|---|---|---|
| **Gin** | Go / 99 | $0.164 | $0.094 (−43 %) | **$0.080 (−51 %)** | **TSA** ⭐ |
| **Alamofire** | Swift / 98 | $0.201 | $0.219 (+9 %) | **$0.147 (−27 %)** | **TSA** ⭐ |
| **Excalidraw** | TS / 603 | $0.204 | **$0.179 (−12 %)** | $0.212 (+4 %) | CodeGraph |
| **Django** | Py / 2 910 | $0.162 | **$0.106 (−35 %)** | $0.205 (+27 %) | CodeGraph |
| **Tokio** | Rust / 778 | **$0.214** | $0.285 (+33 %) | $0.303 (+42 %) | both lose |
| **OkHttp** | Java / 596 | **$0.169** | $0.200 (+18 %) | $0.178 (+5 %) | both lose |
| **Median Δ vs baseline** | | | **−4 %** | **−11 %** | **TSA** |

TSA wins outright on **2 of 6 repos**, has a lower **median cost saving (−11 %)**, and matches CodeGraph's reported direction on every repo where the indexer-class tools should help.

> Why the median diverges from CodeGraph's published −35 % claim: we used Haiku for cost control; they used Opus + 4-run median. See `docs/internal/CODEGRAPH_BENCHMARK_FINAL_2026-05-24.md` for raw envelopes + reproducer scripts.

---

## Key Features

### Pre-indexed code intelligence (CodeGraph parity + superset)

| Capability | TSA tool | Status |
|---|---|---|
| Symbol search (FTS5 + **BM25 ranked**) | `codegraph_symbol_search` | **ahead** — results sorted by relevance score, not file path |
| Go-to-def / find-refs / call hierarchy in one call | `codegraph_navigate` | PRIMARY entry point |
| Bulk-fetch N related symbols + relationship map | `codegraph_explore` | parity |
| Function-level blast radius + risk score | `codegraph_impact` | parity + risk score |
| Who-calls-X / what-X-calls | `codegraph_callers` / `codegraph_callees` | parity |
| Index health at-a-glance (+ edge count) | `codegraph_status` | **ahead** — reports `total_edges` for graph density signal |
| Pre-built call graph cache | `codegraph_autoindex` / `codegraph_full_index` / `codegraph_incremental_sync` | parity |
| Tests affected by a change (CLI) | `--affected FILE...` | parity |

### Tree-sitter Analyzer exclusive

| Capability | TSA tool | Note |
|---|---|---|
| **BM25-ranked symbol search** | all search tools | relevance_score on every result; sort(by='confidence') in DSL |
| **Semantic search (133× faster)** | `codegraph_query semantic()` | BM25 pre-filter narrows 40k symbols to ~400 before cosine rerank |
| **Project A–F health grading** | `check_project_health` | 7 dimensions (size/complexity/deps/coverage/duplication/structure/git-hotspot), no competitor offers this |
| **TOON output** | every tool, `output_format: "toon"` (default) | 50-70 % token saving |
| **Verdict envelopes** | every tool | `SAFE/CAUTION/UNSAFE/INFO/WARN/ERROR/NOT_FOUND` |
| **Safe-to-edit gate** | `safe_to_edit` + `modification_guard` | refuses high-risk edits before they happen |
| **Architectural constraint DSL** | `check_constraints` | "module A cannot import B" → enforced |
| **Code health (file-level)** | `check_file_health` | block/long-method/smell detection |
| **Class hierarchy** | `codegraph_class_hierarchy` | type-inheritance tree |
| **Dependency matrix** | `codegraph_dependency_matrix` | module-coupling matrix |
| **Dead code** | `codegraph_dead_code` | transitive unreachable analysis |
| **Complexity heatmap** | `codegraph_complexity_heatmap` | per-fn cyclomatic + project view |
| **AST-structural clone detection** | `codegraph_similarity` | beyond text similarity |
| **Mermaid call-graph export** | `codegraph_visualize` | paste-ready in docs |
| **UML Mermaid export** | `codegraph_uml` | class / package / component / sequence diagrams |
| **PR review** | `codegraph_pr_review` | AST-diff + semantic classify + blast radius |
| **agent_summary** | every response | next-step hint baked into the envelope |
| **Synapse cross-file resolver** | internal | import-aware, beats regex guessing |
| **Temporal activation** | `symbol_lineage` | per-symbol git-modification frequency |

### Skills (13 curated workflows)

CodeGraph has zero skills. We ship 13 under `.claude/skills/tsa-*/`:

`tsa-landing`, `tsa-find`, `tsa-graph`, `tsa-structure`, `tsa-deps`, `tsa-index`, `tsa-health-watch`, `tsa-edit-safety`, `tsa-edit-then-verify`, `tsa-constraints`, `tsa-pr-review`, `tsa-refactor-queue`, `tsa-temporal`.

Each skill ships an `allowed-tools` subset + procedure recipe + decision-surface schema, so the agent doesn't have to triage 60 tools on every question.

### 252 CLI flags

Strict superset of CodeGraph's 15-command CLI. Highlights:

```bash
tree-sitter-analyzer --table full <file>          # method/signature/complexity table
tree-sitter-analyzer --partial-read --start-line N --end-line M <file>
tree-sitter-analyzer --project-health             # A-F grade across the project
tree-sitter-analyzer --callers <symbol>           # who-calls
tree-sitter-analyzer --codegraph-impact <fn>      # blast radius + risk
tree-sitter-analyzer --affected <file...>         # tests transitively affected
tree-sitter-analyzer --dead-code                  # transitive unreachable
tree-sitter-analyzer --check-constraints          # architectural rules
tree-sitter-analyzer --safe-to-edit <file>        # refuse if risky
tree-sitter-analyzer --uml class                  # Mermaid UML class diagram
```

See [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md) for the full surface.

---

## Quick Start

### 1. Install dependencies

```bash
# uv (required)
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep (required for search)
brew install fd ripgrep                                # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC      # Windows
```

### 2. Install Tree-sitter Analyzer

```bash
uv add "tree-sitter-analyzer[all,mcp]"
```

### 3. Hook it into your agent

See **[Supported Agents](#-supported-agents)**. Most clients want this MCP server entry:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project" }
    }
  }
}
```

After restart: *"Set the project root to my repo and call codegraph_status."*

---

## How It Works

```
Source code → tree-sitter parse → SQLite + FTS5 index (.ast-cache/index.db)
                                         ↓
        codegraph_navigate / codegraph_explore / codegraph_callers / ...
                                         ↓
                            TOON-compressed envelope
                            (verdict + agent_summary + data)
                                         ↓
                              MCP client / CLI consumer
```

The index is built lazily on first query, refreshed on file change via a content-hash diff (`codegraph_incremental_sync`). All 60 tools read from the same `.ast-cache/`, so a query and its follow-up share work.

---

## Supported Agents

<details>
<summary><b>📘 Claude Code</b> (recommended)</summary>

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

Verify: `claude mcp list`. The 13 `tsa-*` skills auto-discover from `.claude/skills/`.
</details>

<details>
<summary><b>📗 Claude Desktop</b></summary>

Edit `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`, Linux: `~/.config/Claude/`):

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project" }
    }
  }
}
```
</details>

<details>
<summary><b>📙 GitHub Copilot (VS Code)</b></summary>

Create `.vscode/mcp.json` (note: `servers`, not `mcpServers`):

```json
{
  "servers": {
    "tree-sitter-analyzer": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}" }
    }
  }
}
```
</details>

<details>
<summary><b>🖱 Cursor / Cline / Continue / Roo Code</b></summary>

All read the same `mcpServers` schema as Claude Desktop. Cursor: **Settings → MCP**. Cline: MCP panel → Edit settings. Continue: `~/.continue/config.json` under `experimental.modelContextProtocolServers`. Roo Code: MCP panel → Edit MCP Settings.
</details>

> ⚠️ `TREE_SITTER_PROJECT_ROOT` must be **absolute**. The server enforces a security boundary against escapes via `SecurityBoundaryManager`.

---

## Supported Languages

21 language plugins; 13 fully wired into the indexer (full symbol + call graph) + 5 (data/markup) reachable via the single-file CLI path + 3 scaffold (plugin exists, indexer wiring pending). The 2026-05-24 patch unblocked Swift / Kotlin / Ruby / PHP / C# that had been silently skipped for months.

| Tier | Languages |
|---|---|
| **Full index + symbol + call graph** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |
| **Single-file analysis (CLI)** | HTML · CSS · Markdown · SQL · YAML |
| **Scaffold (plugin exists, indexer wiring pending)** | bash · scala · json |

CodeGraph supports a similar set; the only popular code languages neither tool ships yet are **Dart, Vue, Svelte, Lua** (next-sprint backlog).

---

## Configuration

Mostly nothing. The defaults are designed so you can hook it into your agent and forget:

* **Output format**: TOON. Override per-call with `output_format: "json"`.
* **Project root**: `TREE_SITTER_PROJECT_ROOT` (env var, MCP) or `--project-root` (CLI).
* **Cache location**: `<project>/.ast-cache/`. Safe to delete — auto-rebuilds.
* **Optional**: `TREE_SITTER_OUTPUT_PATH` for large-output write target.

---

## Quality & Testing

| Metric | Value |
|---|---|
| Tests passed | 18,583 ✅ |
| Coverage | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| Type safety | 100 % mypy |
| Platforms | macOS · Linux · Windows |
| Pre-commit gates | bandit · mypy · pyupgrade · detect-secrets · codemap-sync · smell-ratchet |

```bash
uv run pytest -q                                # full suite
uv run python check_quality.py --new-code-only  # quality gate
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `unsupported language` on `.swift / .kt / .rb / .php / .cs` | Update to ≥ 1.12.x — the 5-language gap was patched in commit `50e99a8f`. |
| MCP server doesn't appear in client | `TREE_SITTER_PROJECT_ROOT` must be **absolute**; restart the client after config edit. |
| `database is locked` | Stop any other process holding `.ast-cache/index.db`; if persistent, `rm -rf .ast-cache && tree-sitter-analyzer --autoindex`. |
| Slow first call | First call builds the index. Subsequent calls are sub-second. Run `--full-index` upfront to amortise. |
| Agent picks the wrong tool | Use a `tsa-*` skill (`/tsa-graph`, `/tsa-find`, ...) — each skill restricts the visible tool set to one workflow. |

---

## Development

```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
uv run pytest -q
```

See **[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)** for the development guide.

---

## Contributing & License

* ⭐ A GitHub star helps surface this tool to other AI-agent users.
* 💖 [Sponsor](https://github.com/sponsors/aimasteracc) — supports continued MCP / Skills development.
* Lead sponsor: **[@o93](https://github.com/o93)**.
* MIT licensed — see [LICENSE](LICENSE).
* Release history: [CHANGELOG.md](CHANGELOG.md).
