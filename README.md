# 🌳 Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

> **The MCP code-intelligence server for AI agents — fewer tokens, fewer tool calls, 100 % local.**
> Pre-indexed AST cache + **8 MCP tools** (down from 63) + 13 curated agent skills + TOON-compressed output.
> **~80% less tool-definition overhead** vs v1.x — the only code-intel MCP that is both rich-output (verdict + TOON) and Roo/Cursor-safe.
> A **strict CLI superset** of CodeGraph, with faster indexing, a one-call jQuery-style query DSL, and a **more complete + more correct call graph** (95.9% of call edges classified vs CodeGraph's same-name mis-wires). Token cost was CodeGraph's one edge — RFC-0006 progressive disclosure cut TSA's default context payload **53%**, closing most of that gap. See [How TSA compares](#how-tsa-compares-to-codegraph).
> **BM25-ranked symbol search** across all 8 facades — results sorted by relevance, not file path.
>
> Competing tool count: CodeGraph ~12 · Rhizome 1 · **TSA 8 (rich-output)** · TSA v1.x was 63.
> Upgrading from v1.x? See [docs/MIGRATION.md](docs/MIGRATION.md).

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-17456%20passed-brightgreen.svg)](#-quality--testing)
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
* **Strict CLI superset of CodeGraph, faster indexing, and a one-call query DSL** — with an honest cost comparison ([below](#how-tsa-compares-to-codegraph)).

---

## How TSA compares to CodeGraph

> **Correction (2026-06).** An earlier version of this section claimed TSA beat CodeGraph on agent token cost (a "−11 % median" table). That benchmark had a harness bug: the TSA arm's MCP server was started without an explicit project root and analysed *tree-sitter-analyzer's own source* instead of the target repo, so its numbers were meaningless. The bug is fixed (the harness now passes `--project-root`), the inflated claim is withdrawn, and the honest picture is below.

### Agent token cost — RFC-0006 cut the default context payload 53%

Token cost was the one axis where CodeGraph led. [RFC-0006](rfcs/0006-context-progressive-disclosure.md) progressive disclosure closes most of the gap at the source: `nav context` now returns a **lean default** — entry points + a compact `related_symbols` list + code blocks — and moves the flat node/edge graph behind an opt-in `include_graph=true`. Measured on this repo (4 representative queries, TOON):

| context payload | chars |
|---|---|
| TSA default, before RFC-0006 | ~13,900 |
| **TSA default, after (lean)** | **~6,600 (−53%)** |
| TSA `include_graph=true` (full, opt-in) | ~13,900 |
| CodeGraph baseline | ~4,400 |

The dominant context call went from **~2.9× CodeGraph's payload to ~1.5×**.

For context, the per-task `$` cost measured **before** RFC-0006 (corrected harness — Claude Sonnet, gin + django, MCP arms, no errors):

| arm | median cost (pre-RFC-0006) | tool calls | file reads |
|---|---|---|---|
| CodeGraph MCP | **~$0.27** | 7 | 2 |
| Tree-sitter Analyzer MCP | ~$0.42 | 7 | 1 |
| no-MCP (grep/read) | ~$0.34 | 14 | 7 |

A full per-task `$` re-benchmark is the next measurement (harness command below). We report the payload proxy straight rather than restate the old table as if RFC-0006 hadn't shipped.

### Where TSA leads

- **Index build speed.** Removing a redundant post-index edge-refresh pass cut a cold django index (~2 950 files) from **181 s → 97 s (−46 %)**; the win grows with repo size. Re-index of unchanged files is a content-hash lookup.
- **Strict CLI superset.** Every MCP tool has a CLI equivalent (CodeGraph's CLI is thinner); *behavioural* defaults (ranking, limits, truncation) are kept in lock-step between the two surfaces. Output format is the one intentional divergence — MCP defaults to TOON (token-efficient for agents), the CLI to JSON (human/`jq`-friendly).
- **One-call expressiveness.** A jQuery-style chain DSL — `search('X').callees(depth=2).explore(include_code=true).answer(compact=true)` — returns an entire flow's subgraph + source in a single call, with JS-style `true`/`false` so agents can write it naturally.
- **Output is structured + token-aware.** TOON default for MCP (50–70 % smaller than JSON), per-call truncation hints, consistent test-file de-prioritisation across every ranking path.
- **Breadth.** Health scoring, safe-to-edit / change-impact gating, 13 curated Skills, and broad language coverage.

### Call-graph correctness — TSA resolves what CodeGraph mis-wires

Token cost is one axis; a code-intelligence tool's *first* job is a **correct graph**. Dogfooding both tools' live indexes on this repository surfaced a class of mis-resolution where CodeGraph binds a call to the wrong same-name definition — and TSA's resolver was fixed to avoid it:

| call (Python `_resolve_entry_points` / `build_response`) | CodeGraph | TSA |
|---|---|---|
| `sorted()` (Python builtin) | ❌ callee = **`tests/golden/corpus_swift.swift` — a Swift `func sorted`** (the one Swift def is wired as a callee of **~293** functions repo-wide) | ✅ left `unknown` — no cross-language edge |
| `fts_search()` / `fts_search_ranked()` | ❌ bound to the **test mock** (`FallbackCache`) instead of the real method | ✅ resolves to the source method (`_ast_cache_query.py` / `ast_cache.py`) |

Telling an agent that a Python function *calls a Swift method*, or that a production call targets a test mock, is wrong structural data. TSA's resolver now gates every binding by **language family** (JS/TS are one family; Python never binds to Swift/JS) and **demotes test-only definitions** for non-test callers, across all of its resolution paths.

#### Correct *and* complete — 95.9% of call edges classified

A correct graph that leaves most edges `unknown` is still half a graph. TSA's resolution cascade now classifies **95.9%** of call edges (up from 83.9%), with **zero** cross-language or test-shadow mis-wires — every gain is gated on the project owning no compatible-language symbol of that name, so shadowing is always preserved:

| resolver tier | what it resolves | source |
|---|---|---|
| binding cascade | local / self / import / unique-method / single-global | RFC-0002 |
| stdlib **method** names (`write_text`, `strip`, `items`) | `str` / `Path` / `dict` / `re` / `argparse` methods → `stdlib` | [RFC-0004](rfcs/0004-stdlib-method-resolution.md) |
| external **library** methods (`raises`, `given`, `MagicMock`) | pytest / hypothesis / mock → `external` | [RFC-0005](rfcs/0005-external-method-resolution.md) |

The remaining ~4% `unknown` is dominated by genuinely-unresolvable dynamic dispatch (`BaseTool.execute()`), constructors, and ambiguous same-name project methods — the false-positive floor of static analysis, left honest rather than guessed.

> **Symbol kinds, too.** TSA classifies class members as `kind=method` (20,348 method rows on this repo) — `search action=symbol kind=method` returns them; CodeGraph parity, not a stub. The `index status` payload breaks symbols down by kind and language and edges by kind (`edges_by_kind` — a breakdown CodeGraph does not surface).

Reproduce the correctness fixes on any repo both tools have indexed:

```bash
# CodeGraph: emits the cross-language / test-shadow callee
#   (e.g. `sorted` → corpus_swift.swift, `fts_search` → test mock)
# TSA after the resolver fix: language-correct, source-preferring
tree-sitter-analyzer --callees _resolve_entry_points --format json
```

> Reproduce the cost numbers: `uv run python benchmarks/codegraph_compare/run.py phase full-warm --repos gin,django`. Raw envelopes + the harness fix live in that directory.

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
| **BM25-ranked symbol search** | all search tools | relevance_score on every result (min-max normalized: best=1.0, weakest=0.0); sort(by='confidence') in DSL |
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
| **One-shot file orientation** | `smart_context` | health + exports + deps + edit-risk in one call (replaces 3-4 calls) |
| **Architectural decision journal** | `decision_journal` | persists reasoning across sessions — no competitor exposes this |

### Skills (13 curated workflows)

CodeGraph has zero skills. We ship 13 under `.claude/skills/tsa-*/`:

`tsa-landing`, `tsa-find`, `tsa-graph`, `tsa-structure`, `tsa-deps`, `tsa-index`, `tsa-health-watch`, `tsa-edit-safety`, `tsa-edit-then-verify`, `tsa-constraints`, `tsa-pr-review`, `tsa-refactor-queue`, `tsa-temporal`.

Each skill ships an `allowed-tools` subset + procedure recipe + decision-surface schema, so the agent doesn't have to triage 8 tools on every question.

### 270 CLI flags

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

The index is built lazily on first query, refreshed on file change via a content-hash diff (`codegraph_incremental_sync`). All 8 tools read from the same `.ast-cache/`, so a query and its follow-up share work.

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
| Tests passed | 17,456 ✅ |
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
