<!-- Generated: 2026-05-22 -->
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
├── mcp_commands.py             ← MCP-equivalent CLI flags (parity contract)
└── codegraph_index_commands.py ← cache trio: autoindex / full-index / incremental-sync / metrics
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
- `--project-overview` — snapshot
- `--project-health` — health-score distribution
- `--smart-context [--query "X"]` — SMART workflow context
- `--change-impact` — blast radius
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
- `--codegraph-status [--codegraph-status-no-lag]` — index health at-a-glance (CodeGraph parity)
- `--codegraph-metrics` — aggregated cache/call-graph/complexity/health dashboard
- `--parser-readiness` — pre-flight checks

### CodeGraph parity (cross-file intelligence from pre-indexed AST cache)
- `--callers SYMBOL` / `--callees SYMBOL` — bidirectional call tracking
- `--call-path FROM TO` — BFS path between two functions
- `--symbol-resolve` — go-to-definition / find-all-references
- `--ast-path FILE:LINE` — "what is at file:line?"
- `--codegraph-symbol-search QUERY` — FTS5 symbol search
- `--codegraph-explore QUERY` — bulk-fetch N related symbols + relmap (CodeGraph parity)
- `--affected FILE [FILE...]` — list test files transitively affected by changes (CodeGraph parity; closes the last CLI surface gap)
- `--dead-code` — transitive dead functions / unused imports
- `--class-hierarchy` / `--dependency-matrix` / `--import-graph` — structural
- `--codegraph-xref` — multi-dimension cross-reference
- `--codegraph-complexity-heatmap` — cyclomatic complexity heatmap
- `--codegraph-sitemap` — hierarchical project code map
- `--codegraph-visualize` — Mermaid flowchart export
- `--code-similarity` — AST-structural clone detection
- `--pr-review` — AST diff + semantic classify + blast-radius PR review

### Info
- `--show-supported-languages`
- `--list-skills`
- `--list-queries`

## Output Format Selection

`--format toon|json|table|csv|yaml`:

| Format | Default for | Token cost | Notes |
|---|---|---|---|
| `toon` | MCP | -73% vs JSON | LLM-optimized, lossless |
| `json` | CLI | baseline | jq-pipe friendly |
| `table` | `--table` flag | n/a | Box-drawing chars, terminal only |
| `csv` | `--table csv` | n/a | spreadsheet ingestion |
| `yaml` | optional | larger than JSON | human-readable structured |

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

## See Also

- [`docs/cli-reference.md`](../cli-reference.md) — Full CLI reference (226 unique flags total — this codemap is intentionally categorical, not exhaustive)
- [`docs/CODEMAPS/mcp-tools.md`](./mcp-tools.md) — MCP-side counterpart
- [`tests/unit/cli/test_mcp_commands.py`](../../tests/unit/cli/test_mcp_commands.py) — Parity contract tests
- [`scripts/codemap-sync-check.sh`](../../scripts/codemap-sync-check.sh) — pre-commit gate that blocks `argument_parser_builder.py` changes without a `cli.md` update
