<!-- Generated: 2026-05-22; doc-code re-sync: 2026-06-17 -->
# CLI Codemap

Three console-script entry points + flag-based dispatch through `cli_main.py`.

## Entry Points

| Command | Module | Default format |
|---|---|---|
| `tree-sitter-analyzer` | `cli_main.py` | `json` |
| `tree-sitter-analyzer-mcp` | `mcp/server.py` (stdio) | `toon` |
| `find-and-grep` | `cli/commands/find_and_grep_cli.py` | `json` |

Default format divergence is **intentional** (see `CLAUDE.md`): CLI users pipe into `jq`,
MCP callers are LLM agents and benefit from TOON's token savings.

## Command Modules

```
cli/commands/
├── base_command.py             ← shared file-path / output-format args
├── default_command.py          ← no-flag default behavior
├── advanced_command.py         ← --table / --summary / --filter
├── partial_read_command.py     ← --partial-read --start-line N --end-line M
├── query_command.py            ← --query-key, --filter, --output-format
├── structure_command.py        ← --table full
├── summary_command.py          ← --summary
├── table_command.py            ← table rendering helpers
├── find_and_grep_cli.py        ← fd + ripgrep subcommands
├── list_files_cli.py           ← `list-files` subcommand
├── search_content_cli.py       ← `search-content` subcommand
├── mcp_commands/               ← MCP-equivalent CLI flags (parity contract; package)
└── codegraph_index_commands.py ← cache commands: autoindex / full-index / incremental-sync / metrics / knowledge graph index
```

## Flag → Tool Mapping

The MCP/CLI parity contract requires that every MCP tool has a CLI flag. The mapping is
enforced by `tests/unit/cli/test_mcp_commands.py`.

Categories of CLI surface:

### Structural Analysis
- `--table full|compact|csv` — full structural AST table
- `--summary` — one-screen summary
- `--partial-read --start-line N --end-line M` — extract range

### Querying
- `--query-key methods|classes|imports|...` — predefined queries
- `--filter "public=true"` — field filter
- `--query "(method_declaration) @m"` — raw tree-sitter query

### Project-Level
- `--overview` — snapshot
- `--project-health` — health-score distribution
- `--smart-context` / `smart-context FILE` — SMART workflow context
- `--change-impact` — blast radius (`--change-impact-resource-profile local_low_impact` emits nice/xdist-capped local pytest commands plus the original CI command)
- `--call-graph` — caller/callee graph

### Code Quality
- `--code-patterns` — smell detection
- `--refactor` — concrete refactor recipes
- `--outline` — hierarchical outline (package → class → method, no bodies)
- `--safe-to-edit` — edit risk verdict
- `--file-health` — per-file score
- `--symbol-lineage NAME` — symbol history

### Discovery
- `list-files` subcommand — fd wrapper
- `search-content` subcommand — ripgrep wrapper
- `find-and-grep` subcommand — combined pipeline
- `--detect-routes` — framework route detection

### Cache & Index
- `--ast-cache index|stats|lookup|invalidate` — AST cache ops (project index default cap: 20k files)
- `--ast-cache-include-activation` — opt in to slower temporal git activation during project indexing
- `--autoindex [--autoindex-mode status|warm|reset]` — transparent auto-index
- `--full-index [--full-index-mode rebuild|stats|clear]` — one-shot complete index (default cap: 20k files)
- `--full-index-include-activation` — opt in to temporal git activation during full-index rebuilds
- `--incremental-sync [--incremental-sync-mode sync|changes|status]` — content-hash diff re-index (SHA-256)
- `--knowledge-graph-index [--knowledge-graph-index-mode build|update|status]` — materialize whole-project code+docs graph sidecar; `--knowledge-graph-backend json|ladybug|hybrid`; update mode scans the full project safely
- `--codegraph-status [--codegraph-status-no-lag]` — index health at-a-glance (CodeGraph parity)
- `--codegraph-metrics` — aggregated cache/call-graph/complexity/health dashboard
- `--parser-readiness` — pre-flight checks

### CodeGraph parity (cross-file intelligence from pre-indexed AST cache)
- `--codegraph-context TASK` — one-call architecture context: entry points, graph, and source blocks
- `--callers SYMBOL` / `--callees SYMBOL` — bidirectional call tracking
- `--call-path FROM TO` — BFS path between two functions
- `--symbol-resolve` — go-to-definition / find-all-references
- `--ast-path FILE:LINE` — "what is at file:line?"
- `--symbol-search QUERY` — FTS5 symbol search
- `--codegraph-explore QUERY` — bulk-fetch N related symbols + relmap (CodeGraph parity)
- `--codegraph-query CHAIN` — jQuery-style chained graph query (`semantic('auth handler').has(callees=True, name='auth').uml(direction='TD').answer(compact=True)`)
- `--codegraph-query-compact` — trim duplicate source payloads and empty relationship fields in chained query answers
- `--affected FILE [FILE...]` — list test files transitively affected by changes (CodeGraph parity; closes the last CLI surface gap)
- `--dead-code` — transitive dead functions / unused imports
- `--doc-sync` — scan markdown docs for stale file-path references (add `--doc-sync-patterns GLOB...` to scope)
- `--class-hierarchy` / `--dependency-matrix` / `--import-graph` — structural
- `--class-inspect CLASS_NAME` — list all methods defined directly on a class with override detection (`is_override`, `overrides_from`)
- `--codegraph-xref` — multi-dimension cross-reference
- `--codegraph-complexity-heatmap` — cyclomatic complexity heatmap
- `--codegraph-sitemap` — hierarchical project code map
- `--codegraph-visualize` — Mermaid flowchart export, or Graphology/Sigma.js JSON with `--codegraph-visualize-format sigma`
- `--knowledge-graph-export` — Graphology/Sigma.js or raw JSON export of code files, Markdown docs, symbols, and relationships with `--knowledge-graph-lod package|file|symbol|docs`
- `--uml class|package|component|sequence` — UML-style Mermaid diagram export
- `--code-similarity` — AST-structural clone detection
- `--pr-review diff|staged|branch|pr` — AST diff + semantic classify +
  blast-radius PR review (`pr` mode takes `--pr-review-url URL`)

### Info
- `--show-supported-languages`
- `--list-skills`
- `--list-queries`

## Output Format Selection

`--format toon|json` (global machine-readable envelope alias):

| Format | Default for | Token cost | Notes |
|---|---|---|---|
| `toon` | MCP | -73% vs JSON | LLM-optimized, lossless |
| `json` | CLI | baseline | jq-pipe friendly |
| `text` | `--output-format text` | n/a | human-readable output for legacy text paths |
| `table` | `--table` flag | n/a | Box-drawing chars, terminal only |
| `csv` | `--table csv` | n/a | spreadsheet ingestion |

`--format` is intentionally narrower than `--output-format` and `--table`:
use `--format json|toon` for agent envelopes, `--output-format text` for the
remaining human-readable text paths, and `--table csv|full|compact|json|toon`
for table rendering. There is no global `--format yaml` mode.

## File Output

Large payloads use `mcp/utils/file_output_factory.py`:
- `--output-file PATH` — write directly
- `TREE_SITTER_OUTPUT_PATH` env var — auto-spill threshold

## Verification Commands

After any code edit, agents should run the per-change verification command surfaced by
`--change-impact`:

```bash
uv run python -m tree_sitter_analyzer --change-impact --format json
# → look at agent_summary.verification_command
```

The command is tailored to the change: `pytest <specific tests>`, `mypy <touched module>`,
or `git diff --check` for non-code edits.
For interactive agent work on a user's machine, add
`--change-impact-resource-profile local_low_impact`; the local
`verification_command` is capped with `nice -n 15` and `pytest -n 2`, while
`ci_verification_command` keeps the original broader command for CI or a queue
boundary.

## See Also

- [`docs/cli-reference.md`](../cli-reference.md) — Full CLI reference (295 unique flags total — this codemap is intentionally categorical, not exhaustive)
- [`docs/CODEMAPS/mcp-tools.md`](./mcp-tools.md) — MCP-side counterpart
- [`tests/unit/cli/test_mcp_commands.py`](../../tests/unit/cli/test_mcp_commands.py) — Parity contract tests
- [`scripts/codemap-sync-check.sh`](../../scripts/codemap-sync-check.sh) — pre-commit gate that blocks `cli/argument_parser_builder.py` changes without a `cli.md` update
