# 🌳 Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) [![Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer) [![Works with Claude Code · Cursor · MCP](https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20MCP-6f42c1.svg)](#supported-agents)

**Code intelligence AI agents can trust** — correct cross-language structure across the [supported language inventory](#supported-languages), agent-native (MCP + CLI).

TSA indexes your codebase with tree-sitter and serves correct call graphs, symbol search, and structural queries to AI coding agents — locally, with no telemetry.

**Why it's different:**
* **Cross-language correctness is the moat.** Language-family gates prevent name-only cross-language bindings.
* **Built agent-native.** 8 MCP tools provide TOON output and verdict envelopes, with CLI access and curated workflows.
* **Broad and correctly classified.** The [generated support-depth inventory](#supported-languages) distinguishes pipeline evidence from unverified cross-file behavior.

> Upgrading from v1.x? See [docs/MIGRATION.md](docs/MIGRATION.md).

---

## Get Started

> **Requires Python 3.10+** (check: `python --version`). Install from [python.org](https://www.python.org/downloads/) if needed.

### Automated install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh | bash
```

Auto-installs `uv` if missing, detects Claude Desktop / Claude Code / Cursor / VS Code, and writes the MCP entry. Run `tree-sitter-analyzer --doctor` to verify.

> **Bootstrap trust:** for convenience, the command above downloads and executes the official `uv` installer when `uv` is missing or outdated. That installer is mutable and **not content-bound**; TSA warns before downloading it to a temporary file over TLS and performs a strict post-install version check. To avoid this unverified bootstrap, install `uv >= 0.11.0` manually first, or use the secure opt-out (which exits with manual-install instructions when bootstrap is needed):
> ```bash
> curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh \
>   | TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP=1 bash
> ```

Install command for **Claude Code**:

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

Restart your agent, then say: *"Run the `index` tool with action=status."*
CLI equivalent (no agent needed): `tree-sitter-analyzer --codegraph-status`

> **PyPI / uvx users — install skills:** the `tsa-*` skills are bundled in the wheel. Copy them once with:
> ```bash
> tree-sitter-analyzer --install-skills              # into ./.claude/skills/ (this project)
> tree-sitter-analyzer --install-skills-global       # into ~/.claude/skills/ (all projects)
> ```
> Git-clone users already have them under `.claude/skills/` — no action needed.

[Other agents (Cursor, Copilot, Cline, Continue, Claude Desktop, Roo Code) →](#supported-agents)

### Quick install

#### 1. Install dependencies

```bash
# uv (required). This official convenience installer is mutable/not content-bound;
# see https://docs.astral.sh/uv/ for alternative manual installation methods.
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

**See the correctness edge on your own repo** — no install, no CodeGraph (it re-indexes first):

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

It reports possible cross-language name collisions so you can inspect resolver behavior on your own repository. Results are diagnostic, not a competitive benchmark claim.

---

## Why Tree-sitter Analyzer

* **Token-aware output.** MCP responses default to **TOON**; payload behavior is guarded by [output-cost invariants](tests/unit/mcp/test_output_cost_invariants.py), including known decision-tool limitations tracked in [RFC-0018](rfcs/0018-response-envelope-normalization-and-adaptive-toon.md).
* **Verdict envelopes.** Every response carries `verdict: SAFE | CAUTION | UNSAFE | INFO | REVIEW | WARN | ERROR | NOT_FOUND`, so orchestrators branch on outcomes without re-prompting.
* **Project health grading (A–F).** TSA grades projects across size, complexity, coverage, duplication, dependencies, structure, and git hotspots.
* **Curated workflows (Skills).** Pre-baked tool subsets for "find symbol", "trace call chain", "assess health", "safe-to-edit before refactor", "PR review", etc.
* **Layered safety.** `edit action=safe` + `edit action=guard` + constraint DSL + `edit action=impact` + verdict envelopes — designed so agents *know* before they touch.
* **CLI/MCP parity and a unified query DSL.** The same analysis primitives are available to agents and shell users.

---

## Key Features

### Pre-indexed code intelligence (CodeGraph parity + superset)

| Capability | TSA tool | Status |
|---|---|---|
| Symbol search (FTS5 + **BM25 ranked**) | `search` action=symbol | **ahead** — results sorted by relevance score, not file path |
| Go-to-def / find-refs / call hierarchy in a combined request | `nav` action=navigate | PRIMARY entry point |
| Bulk-fetch N related symbols + relationship map | `structure` action=explore | parity |
| Function-level blast radius + risk score | `nav` action=impact | parity + risk score |
| Who-calls-X / what-X-calls | `nav` action=callers / action=callees | parity |
| Index health at-a-glance (+ edge count) | `index` action=status | **ahead** — reports `total_edges` for graph density signal |
| Pre-built call graph cache | `index` action=auto / action=full / action=sync | parity |
| Tests affected by a change (CLI) | `--affected FILE...` | parity |

### Tree-sitter Analyzer exclusive

| Capability | TSA tool | Note |
|---|---|---|
| **BM25-ranked symbol search** | all search tools | min-max normalized relevance_score on every result; sort(by='confidence') in DSL |
| **Semantic search (BM25 pre-filtered)** | `search` action=chain (`semantic()` DSL) | lexical pre-filter before cosine rerank |
| **Project A–F health grading** | `health` action=project | combines size, complexity, dependencies, coverage, duplication, structure, and git hotspots |
| **TOON output** | every tool, `output_format: "toon"` (default) | compact tabular encoding; decision tools tracked by RFC-0018 |
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
| **File orientation** | `project` action=smart | health + exports + deps + edit-risk in a combined response |
| **Architectural decision journal** | `project` action=journal | persists reasoning across sessions — uncommon among code-intel tools |

### Skills

TSA ships curated workflows under `.claude/skills/tsa-*/`:

`tsa-landing`, `tsa-find`, `tsa-graph`, `tsa-structure`, `tsa-deps`, `tsa-index`, `tsa-health-watch`, `tsa-edit-safety`, `tsa-edit-then-verify`, `tsa-constraints`, `tsa-pr-review`, `tsa-refactor-queue`, `tsa-temporal`.

Each skill ships an `allowed-tools` subset + procedure recipe + decision-surface schema, so the agent doesn't have to triage 8 tools on every question.

### 323 CLI flags

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

Installing the package also registers standalone search helpers (thin
entry points over the same engine, handy in shell pipelines):

```bash
list-files <dir>          # fd-style file discovery
search-content <pattern>  # ripgrep-style content search
find-and-grep <pattern>   # two-stage fd + ripgrep
```

See [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md) for the full surface.

---

## Quantitative claim governance

Public benchmark, performance, or competitive numbers are emitted only from the
provenance-bound registry in
[`benchmarks/codegraph_compare/claim_registry.json`](benchmarks/codegraph_compare/claim_registry.json).
E4 evidence must bind exact tool names and versions, measurements, corpus,
benchmark date/version, and an artifact digest. Evidence below E4 remains
internal and cannot emit wording. See the [benchmark runbook](benchmarks/codegraph_compare/README.md).

<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->
<!-- END GENERATED QUANTITATIVE CLAIMS -->

The absence of a generated item means that no quantitative public claim is
currently authorized. Qualitative descriptions above are bounded product
capabilities, not measured superiority claims.

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

Verify: `claude mcp list`. The bundled `tsa-*` skills auto-discover from `.claude/skills/`.

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

<!-- BEGIN GENERATED LANGUAGE SUPPORT INVENTORY -->
Generated from runtime registries; see [`docs/CODEMAPS/languages.md`](docs/CODEMAPS/languages.md) for the full capability matrix. **22 plugins**: 13 pipeline-registered, 2 index-admitted, 1 call-dispatch-only, 5 data/markup, 1 scaffold. `pipeline_registered` is registration evidence, not positive cross-file binding proof.
`pipeline_registered`: C, C++, C#, Go, Java, JavaScript, Kotlin, PHP, Python, Ruby, Rust, Swift, TypeScript | `index_admitted`: Bash, Scala | `call_dispatch_only`: Lua | `data_markup`: CSS, HTML, Markdown, SQL, YAML | `scaffold`: JSON
<!-- END GENERATED LANGUAGE SUPPORT INVENTORY -->

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
| Tests passed | Comprehensive test suite ✅ |
| Coverage | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| Type safety | mypy |
| Platforms | macOS · Linux · Windows |
| Pre-commit gates | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # bounded local quick gate
uv run pytest tests/ -q --timeout=120 -m "not e2e and not network and not benchmark"  # comprehensive local suite
PYTEST_XDIST_AUTO_NUM_WORKERS=1 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # one-worker mode for lower CPU load
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # two-worker balanced mode
uv run pytest --lf --maxfail=1                  # rerun only failed tests from last run
uv run python check_quality.py --new-code-only  # quality gate
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `unsupported language` on `.swift / .kt / .rb / .php / .cs` | Update to a current supported release — the missing-language gap was patched in commit `50e99a8f`. Grammar modules for extras-gated languages are not bundled in the base install; run `pip install "tree-sitter-analyzer[swift]"` (or `kotlin`, `ruby`, `php`, `csharp`) to add them. |
| MCP server doesn't appear in client | `TREE_SITTER_PROJECT_ROOT` must be an **absolute path** (e.g. `$(pwd)` or `/home/user/project`); a relative path causes the server to resolve against the wrong directory. Restart the client after editing. Run `tree-sitter-analyzer --doctor` to verify. |
| `database is locked` | Stop any other process holding `.ast-cache/index.db`; if persistent, `rm -rf .ast-cache && tree-sitter-analyzer --full-index`. |
| Slow first call | First call builds the index. Run `--full-index` upfront to amortise future calls. |
| Agent picks the wrong tool | Use a `tsa-*` skill (`/tsa-graph`, `/tsa-find`, ...) — each skill restricts the visible tool set to its dedicated workflow. |

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
