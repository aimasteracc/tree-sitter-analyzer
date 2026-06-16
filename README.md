# 🌳 Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) [![Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer) [![Works with Claude Code · Cursor · MCP](https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20MCP-6f42c1.svg)](#supported-agents)

**Code intelligence AI agents can trust** — correct cross-language structure across 20+ languages, agent-native (MCP + CLI).

TSA indexes your codebase with tree-sitter and serves correct call graphs, symbol search, and structural queries to AI coding agents — locally, with no telemetry.

**Why it's different:**
* **Cross-language correctness is the moat.** A name-only index wires Python `sorted()` to a Swift `func sorted`. TSA doesn't. ~390× fewer cross-language call-graph mis-wires than alternatives ([reproducible audit](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md)).
* **Built agent-native.** 8 MCP tools, TOON output (~50-70% smaller than JSON on bulk responses), verdict envelopes, and 13 curated Skills — designed for Claude Code, Cursor, and any MCP client.
* **Broad and correctly classified.** 13 languages with full call-graph indexing (Python · Go · Rust · Java · JS · TS · C · C++ · C# · Swift · Kotlin · Ruby · PHP), 8 more symbol-indexed or CLI-reachable.

> **Proof:** on HuggingFace `tokenizers` (Rust+Python+JS+TS), a name-only resolver mis-wires **1,259** call edges — TSA: **0**. Run it on your repo in seconds: `uvx --from tree-sitter-analyzer miswire-audit .`

> Upgrading from v1.x? See [docs/MIGRATION.md](docs/MIGRATION.md).

---

## Get Started

> **Requires Python 3.10+** (check: `python3 --version`). Install from [python.org](https://www.python.org/downloads/) if needed.

One-line install for **Claude Code**:

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

Restart your agent, then say: *"Run the `index` tool with action=status."*
CLI equivalent (no agent needed): `tree-sitter-analyzer --codegraph-status`

> **PyPI / uvx users — install skills:** the 13 `tsa-*` skills are bundled in the wheel. Copy them once with:
> ```bash
> tree-sitter-analyzer --install-skills              # into ./.claude/skills/ (this project)
> tree-sitter-analyzer --install-skills-global       # into ~/.claude/skills/ (all projects)
> ```
> Git-clone users already have them under `.claude/skills/` — no action needed.

[Other agents (Cursor, Copilot, Cline, Continue, Claude Desktop, Roo Code) →](#supported-agents)

### Quick install

#### 1. Install dependencies

```bash
# uv (required)
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep (required for `search action=content` text search; symbol search uses SQLite FTS5 and needs neither)
brew install fd ripgrep                                # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC      # Windows
```

#### 2. Install Tree-sitter Analyzer

```bash
# Standalone install (persistent CLI command):
uv tool install "tree-sitter-analyzer[all,mcp]"
# — or skip installing entirely: the MCP entry below runs via uvx on demand.
# Inside a uv-managed Python project, use: uv add "tree-sitter-analyzer[all,mcp]"
```

#### 3. Hook it into your agent

See **[Supported Agents](#supported-agents)**. Most clients want this MCP server entry:

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

After restart: *"Run the `index` tool with action=status."*
CLI equivalent (no agent needed): `tree-sitter-analyzer --codegraph-status`

**See the correctness edge on your own repo** — no install, no CodeGraph (it re-indexes first; seconds on a small repo, a minute or two on a large one):

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

It prints how many call edges a name-only code index (the design most tools use) *would* mis-wire across a language boundary — e.g. a Python `sorted()` wired to a Swift `func sorted` — versus how many TSA does (≈0). On [HuggingFace `tokenizers`](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md): **1,259 → 0**.

---

## Why Tree-sitter Analyzer

* **Token-efficient by default.** Every MCP response uses **TOON** — a tabular JSON variant that cuts bulk/tabular payloads by ~50-70 % vs raw JSON ([measured invariant](tests/unit/mcp/test_output_cost_invariants.py); RFC-0012 measured 0.52× ratio on representative decision tools).
* **Verdict envelopes.** Every response carries `verdict: SAFE | CAUTION | UNSAFE | INFO | WARN | ERROR | NOT_FOUND`, so orchestrators branch on outcomes without re-prompting.
* **Project health grading (A–F).** Few code-intel tools expose a whole-project quality grade — TSA grades on size / complexity / coverage / duplication / dependencies / structure / git-hotspots in one call.
* **13 curated workflows (Skills).** Pre-baked tool subsets for "find symbol", "trace call chain", "score health", "safe-to-edit before refactor", "PR review", etc.
* **5 layers of safety.** `edit action=safe` + `edit action=guard` + constraint DSL + `edit action=impact` + verdict envelopes — designed so agents *know* before they touch.
* **Strict CLI superset of CodeGraph, faster indexing, and a one-call query DSL** — with an honest cost comparison ([below](#how-tsa-compares-to-codegraph)).

---

## Key Features

### Pre-indexed code intelligence (CodeGraph parity + superset)

| Capability | TSA tool | Status |
|---|---|---|
| Symbol search (FTS5 + **BM25 ranked**) | `search` action=symbol | **ahead** — results sorted by relevance score, not file path |
| Go-to-def / find-refs / call hierarchy in one call | `nav` action=navigate | PRIMARY entry point |
| Bulk-fetch N related symbols + relationship map | `structure` action=explore | parity |
| Function-level blast radius + risk score | `nav` action=impact | parity + risk score |
| Who-calls-X / what-X-calls | `nav` action=callers / action=callees | parity |
| Index health at-a-glance (+ edge count) | `index` action=status | **ahead** — reports `total_edges` for graph density signal |
| Pre-built call graph cache | `index` action=auto / action=full / action=sync | parity |
| Tests affected by a change (CLI) | `--affected FILE...` | parity |

### Tree-sitter Analyzer exclusive

| Capability | TSA tool | Note |
|---|---|---|
| **BM25-ranked symbol search** | all search tools | relevance_score on every result (min-max normalized: best=1.0, weakest=0.0); sort(by='confidence') in DSL |
| **Semantic search (BM25 pre-filtered)** | `search` action=chain (`semantic()` DSL) | BM25 pre-filter narrows 40k symbols to ~400 before cosine rerank |
| **Project A–F health grading** | `health` action=project | 7 dimensions (size/complexity/deps/coverage/duplication/structure/git-hotspot), uncommon among code-intel tools |
| **TOON output** | every tool, `output_format: "toon"` (default) | 50-70 % token saving on bulk/tabular output |
| **Verdict envelopes** | every tool | `SAFE/CAUTION/UNSAFE/INFO/WARN/ERROR/NOT_FOUND` |
| **Safe-to-edit gate** | `edit` action=safe / action=guard | refuses high-risk edits before they happen |
| **Architectural constraint DSL** | `edit` action=constraints | "module A cannot import B" → enforced |
| **Code health (file-level)** | `health` action=file | block/long-method/smell detection |
| **Class hierarchy** | `structure` action=class_tree | type-inheritance tree |
| **Dependency matrix** | `health` action=matrix | module-coupling matrix |
| **Dead code** | `health` action=dead | transitive unreachable analysis |
| **Complexity heatmap** | `health` action=heatmap | per-fn cyclomatic + project view |
| **AST-structural clone detection** | `viz` action=similarity | beyond text similarity |
| **Mermaid call-graph export** | `viz` action=graph | paste-ready in docs |
| **UML Mermaid export** | `viz` action=uml | class / package / component / sequence diagrams |
| **PR review** | `edit` action=pr | AST-diff + semantic classify + blast radius |
| **agent_summary** | every response | next-step hint baked into the envelope |
| **Synapse cross-file resolver** | internal | import-aware, beats regex guessing |
| **Temporal activation** | `nav` action=lineage | per-symbol git-modification frequency |
| **One-shot file orientation** | `project` action=smart | health + exports + deps + edit-risk in one call (replaces 3-4 calls) |
| **Architectural decision journal** | `project` action=journal | persists reasoning across sessions — uncommon among code-intel tools |

### Skills (13 curated workflows)

CodeGraph has zero skills. We ship 13 under `.claude/skills/tsa-*/`:

`tsa-landing`, `tsa-find`, `tsa-graph`, `tsa-structure`, `tsa-deps`, `tsa-index`, `tsa-health-watch`, `tsa-edit-safety`, `tsa-edit-then-verify`, `tsa-constraints`, `tsa-pr-review`, `tsa-refactor-queue`, `tsa-temporal`.

Each skill ships an `allowed-tools` subset + procedure recipe + decision-surface schema, so the agent doesn't have to triage 8 tools on every question.

### 295 CLI flags

Superset of CodeGraph's CLI surface. Highlights:

```bash
tree-sitter-analyzer --table full <file>          # method/signature/complexity table
tree-sitter-analyzer --partial-read --start-line N --end-line M <file>
tree-sitter-analyzer --project-health             # A-F grade across the project
# Note: --callers / --callees require the call-graph index — run --full-index first
tree-sitter-analyzer --full-index                 # build call-graph index (run once)
tree-sitter-analyzer --callers <symbol>           # who-calls
tree-sitter-analyzer --codegraph-impact <fn>      # blast radius + risk
tree-sitter-analyzer --affected <file...>         # tests transitively affected
tree-sitter-analyzer --dead-code                  # transitive unreachable
tree-sitter-analyzer --check-constraints          # architectural rules
tree-sitter-analyzer --safe-to-edit <file>        # refuse if risky
tree-sitter-analyzer --uml class                  # Mermaid UML class diagram
```

Installing the package also registers three standalone search utilities (thin
entry points over the same engine, handy in shell pipelines):

```bash
list-files <dir>          # fd-style file discovery
search-content <pattern>  # ripgrep-style content search
find-and-grep <pattern>   # two-stage fd + ripgrep
```

See [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md) for the full surface.

---

## How TSA compares to CodeGraph

### Call-graph correctness — TSA resolves what CodeGraph mis-wires

Token cost is one axis; a code-intelligence tool's *first* job is a **correct graph**.

**Head-to-head on this repo, both tools' live indexes** (count every call edge whose caller language differs from the callee's — a cross-language mis-wire by construction; [reproducible](benchmarks/codegraph_compare/REPORT-v1.21.0.md)):

| tool | cross-language mis-wires | total call edges | rate |
|---|---|---|---|
| CodeGraph | **745** | 38,103 | 1.96 % |
| **Tree-sitter Analyzer** | **6** | 114,160 | **0.005 %** |

**~390× cleaner on cross-language correctness, while resolving 3× more call edges.** CodeGraph's mis-wires span 19+ language pairs (python→swift **408**, python→typescript 195, python→ruby 81, …); TSA's 6 are all `java→python/php` from single-word Java method names.

> **Don't trust this table — run it on your own repo (no CodeGraph install needed):**
> ```bash
> uvx --from tree-sitter-analyzer miswire-audit .
> ```
> It indexes your code and prints how many call edges a name-only resolver (the design most indexes use) *would* mis-wire across a language boundary vs how many TSA does — with the offending edges listed (`Python sorted() → Swift func at file:line`). Add `--card` for a shareable scorecard.
>
> **Real runs:** on [HuggingFace `tokenizers`](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md) (Rust+Python+JS+TS) a name-only resolver would mis-wire **1,259** call edges (incl. a JS `tokenize()` → Rust def) — TSA: **0**. On a single-language repo (`gin`, Go) both are **0** — no false positives. [More examples →](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md)

Concretely:

| call (Python `_resolve_entry_points` / `build_response`) | CodeGraph | TSA |
|---|---|---|
| `sorted()` (Python builtin) | ❌ callee = **`tests/golden/corpus_swift.swift` — a Swift `func sorted`** (wired as a callee of **299** Python functions repo-wide) | ✅ `builtin` — no cross-language edge |
| `fts_search()` / `fts_search_ranked()` | ❌ bound to the **test mock** (`FallbackCache`) instead of the real method | ✅ resolves to the source method (`_ast_cache_query.py` / `ast_cache.py`) |

TSA's per-language resolver gates every binding by **language family** across **13 languages** (Python · Java · Go · JS · TS · C · C++ · Rust · C# · Kotlin · Ruby · PHP · Swift) and **demotes test-only definitions** for non-test callers, across all of its resolution paths. Telling an agent that a Python function *calls a Swift method*, or that a production call targets a test mock, is wrong structural data — and it is the dominant failure mode of a name-only index.

#### Correct *and* complete — 96.3% of call edges classified

A correct graph that leaves most edges `unknown` is still half a graph. TSA's resolution cascade now classifies **96.3%** of call edges (up from 83.9%), with **zero** cross-language or test-shadow mis-wires — every gain is gated on the project owning no compatible-language symbol of that name, so shadowing is always preserved:

| resolver tier | what it resolves | source |
|---|---|---|
| binding cascade | local / self / import / unique-method / single-global | RFC-0002 |
| stdlib **method** names (`write_text`, `strip`, `items`) | `str` / `Path` / `dict` / `re` / `argparse` methods → `stdlib` | [RFC-0004](rfcs/0004-stdlib-method-resolution.md) |
| external **library** methods (`raises`, `given`, `MagicMock`) | pytest / hypothesis / mock → `external` | [RFC-0005](rfcs/0005-external-method-resolution.md) |

The remaining ~4% `unknown` is dominated by genuinely-unresolvable dynamic dispatch (`BaseTool.execute()`), constructors, and ambiguous same-name project methods — the false-positive floor of static analysis, left honest rather than guessed.

> **Now multi-language.** Cross-language-safe resolution is no longer Python-only. A per-language **resolver registry** ([RFC-0010](rfcs/0010-resolver-language-registry.md)) gives each language its own classification cascade with conservative stdlib/external tiers, gated by language family so a binding does not cross into an incompatible language. **Active classified call graph (call-edge extraction + per-language resolver), 13 languages: Python · Java · Go · JavaScript · TypeScript · C · C++ · Rust · C# · Kotlin · Ruby · PHP · Swift.** Each has its own conservative stdlib/external tiers and is adversarially verified to never bind across a language boundary. **Swift is notable**: CodeGraph's flagship mis-wire binds 299 Python `sorted()` callers to a Swift `func sorted` — TSA resolves Swift correctly *and* refuses that exact cross-language bind (verified both directions). Measured on the active set: **6** cross-language edges (6 of ~57,000 resolved edges, all generic 1-word Java method names) — **~390× cleaner than CodeGraph** on cross-language correctness, which wires **299** Python `sorted()` callers to a single Swift `func sorted` (TSA binds **0** of 298). Full reproducible audit: [`benchmarks/codegraph_compare/REPORT-v1.21.0.md`](benchmarks/codegraph_compare/REPORT-v1.21.0.md). Adding a language is one new resolver file (RFC-0010) plus a small call-extraction wiring.

> **Symbol kinds, too.** TSA classifies class members as `kind=method` (20,348 method rows on this repo) — `search action=symbol kind=method` returns them; CodeGraph parity, not a stub. The `index status` payload breaks symbols down by kind and language and edges by kind (`edges_by_kind` — a breakdown CodeGraph does not surface).

### Where TSA leads

- **Index build speed.** Removing a redundant post-index edge-refresh pass cut a cold django index (~2 950 files) from **181 s → 97 s (−46 %)**; the win grows with repo size. Re-index of unchanged files is a content-hash lookup.
- **Strict CLI superset.** Every MCP tool has a CLI equivalent (CodeGraph's CLI is thinner); *behavioural* defaults (ranking, limits, truncation) are kept in lock-step between the two surfaces. Output format is the one intentional divergence — MCP defaults to TOON (token-efficient for agents), the CLI to JSON (human/`jq`-friendly).
- **One-call expressiveness.** A jQuery-style chain DSL — `search('X').callees(depth=2).explore(include_code=true).answer(compact=true)` — returns an entire flow's subgraph + source in a single call, with JS-style `true`/`false` so agents can write it naturally.
- **Output is structured + token-aware.** TOON default for MCP (50–70 % smaller than JSON on bulk/tabular output), per-call truncation hints, consistent test-file de-prioritisation across every ranking path.
- **Breadth.** Health scoring, safe-to-edit / change-impact gating, 13 curated Skills, and broad language coverage.

### On token cost — and a benchmark we corrected

> **Correction (2026-06).** An earlier version of this section claimed TSA beat CodeGraph on agent token cost (a "−11 % median" table). That benchmark had a harness bug: the TSA arm's MCP server was started without an explicit project root and analysed *tree-sitter-analyzer's own source* instead of the target repo, so its numbers were meaningless. The bug is fixed (the harness now passes `--project-root`), the inflated claim is withdrawn, and the honest picture is below.

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
| Tree-sitter Analyzer MCP | ~$0.44 | 7 | 1 |
| no-MCP (grep/read) | ~$0.34 | 14 | 7 |

A full per-task `$` re-benchmark is the next measurement (harness command below). We report the payload proxy straight rather than restate the old table as if RFC-0006 hadn't shipped.

### Reactive push + edge-kind breakdown — two things CodeGraph can't do

CodeGraph (and most one-shot indexers) only answer on poll: you ask, it replies with a snapshot, and you re-ask to learn whether anything changed. TSA exposes two capabilities that close that loop:

- **Reactive push / subscription ([RFC-0001](rfcs/0001-reactive-push.md), implemented).** `search action=subscribe` registers a Hyphae selector and returns a `tsa://hyphae/{selector}` MCP resource URI. When the watched code changes, the server emits a resource-updated notification — the agent re-reads the resource instead of polling. `search action=unsubscribe` cancels it. CodeGraph has no push or subscription channel.
- **`edges_by_kind` in `index action=status`.** Status returns a per-edge-kind count (calls / extends / implements / imports …), not just a single `total_edges` — so an agent can read the graph's shape (how call-heavy vs inheritance-heavy a repo is) before drilling in. CodeGraph surfaces only a flat total.

Reproduce the correctness fixes on any repo both tools have indexed:

```bash
# CodeGraph: emits the cross-language / test-shadow callee
#   (e.g. `sorted` → corpus_swift.swift, `fts_search` → test mock)
# TSA after the resolver fix: language-correct, source-preferring
tree-sitter-analyzer --callees _resolve_entry_points --format json
```

> Reproduce the cost numbers: `uv run python benchmarks/codegraph_compare/run.py phase full-warm --repos gin,django`. Raw envelopes + the harness fix live in that directory.

---

## How It Works

```
Source code → tree-sitter parse → SQLite + FTS5 index (.ast-cache/index.db)
                                         ↓
        nav (navigate) / structure (explore) / nav (callers) / ...
                                         ↓
                            TOON-encoded envelope
                            (compact for tabular output;
                             verdict + agent_summary + data)
                                         ↓
                              MCP client / CLI consumer
```

The index is built lazily on first query, refreshed on file change via a content-hash diff (`index` action=sync). All 8 tools read from the same `.ast-cache/`, so a query and its follow-up share work.

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

**PyPI / uvx users** — install the bundled skills once with:
```bash
tree-sitter-analyzer --install-skills              # into ./.claude/skills/ (this project)
tree-sitter-analyzer --install-skills-global       # into ~/.claude/skills/ (all projects)
```
Git-clone users already have them — no action needed.
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

<details>
<summary><b>🐳 Docker</b> (no local Python / uv)</summary>

The repo ships a [`Dockerfile`](Dockerfile) that builds the MCP server (stdio transport) from source, so the image always matches the committed code.

```bash
# Build once
docker build -t tree-sitter-analyzer-mcp .

# Run against the current repo (server speaks MCP over stdio; -i keeps stdin open)
docker run --rm -i --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" -w /work tree-sitter-analyzer-mcp
```

`--user "$(id -u):$(id -g)"` runs as your host UID/GID, so the `.ast-cache/`, decision journal, and any `edit` writes under the bind-mounted repo are owned by you, not root.

MCP client config (the project root inside the container is the mount point `/work`):

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--user", "1000:1000",
        "-v", "/absolute/path/to/your/project:/work",
        "-w", "/work",
        "-e", "TREE_SITTER_PROJECT_ROOT=/work",
        "tree-sitter-analyzer-mcp"
      ]
    }
  }
}
```
</details>

> ⚠️ `TREE_SITTER_PROJECT_ROOT` must be **absolute**. The server enforces a security boundary against escapes via `SecurityValidator`.

---

## Supported Languages

21 language plugins; 13 fully wired into the indexer (full symbol + call graph) + 2 symbol-indexed (call-graph wiring pending) + 5 (data/markup) reachable via the single-file CLI path + 1 scaffold (plugin exists, indexer wiring pending). bash and scala graduated in v1.22.0; the 2026-05-24 patch unblocked Swift / Kotlin / Ruby / PHP / C# that had been silently skipped for months.

| Tier | Languages |
|---|---|
| **Full index + symbol + call graph** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |
| **Full index + symbols (call-graph wiring pending)** | Bash · Scala |
| **Single-file analysis (CLI)** | HTML · CSS · Markdown · SQL · YAML |
| **Scaffold (plugin exists, indexer wiring pending)** | json |

CodeGraph supports a similar set. **Dart, Vue, Svelte, Lua** are not yet shipped — aspirational backlog, no committed date.

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
| Tests passed | 18,493 ✅ |
| Coverage | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| Type safety | 100 % mypy |
| Platforms | macOS · Linux · Windows |
| Pre-commit gates | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # full suite
uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # fast local loop
PYTEST_XDIST_AUTO_NUM_WORKERS=1 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # one-worker mode for lower CPU load
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # two-worker balanced mode
uv run pytest --lf --maxfail=1                  # rerun only failed tests from last run
uv run python check_quality.py --new-code-only  # quality gate
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `unsupported language` on `.swift / .kt / .rb / .php / .cs` | Update to ≥ 1.12.x — the 5-language gap was patched in commit `50e99a8f`. Grammar modules for extras-gated languages are not bundled in the base install; run `pip install "tree-sitter-analyzer[swift]"` (or `kotlin`, `ruby`, `php`, `csharp`) to add them. |
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
