<!-- Generated: 2026-05-22 -->
# MCP Tools Codemap

27 MCP tools registered in [`mcp/server.py:124`](../../tree_sitter_analyzer/mcp/server.py#L124).
All tools default to **TOON output** (locked — see `CLAUDE.md`).

## Tool Registry

| MCP name | CLI flag / handler | Purpose |
|---|---|---|
| `check_code_scale` | `--check-scale` | Per-file metrics (LOC, complexity, classes/methods/imports counts) |
| `analyze_code_structure` | `--table` / `--summary` | Full structural AST table |
| `extract_code_section` | `--partial-read --start-line N --end-line M` | Token-efficient line range |
| `get_code_outline` | (MCP-only; CLI: `--table compact`) | Structural navigation map (hierarchy, no method bodies) |
| `query_code` | `--query-key methods --filter "public=true"` | tree-sitter query DSL |
| `list_files` | `list-files` subcommand (fd) | Discovery |
| `search_content` | `search-content` subcommand (ripgrep) | Regex search |
| `find_and_grep` | `find-and-grep` subcommand (fd+rg pipeline) | Combined find+grep |
| `list_agent_skills` | `--list-skills` | Curated skill index for AI agents |
| `get_agent_workflow` | `--smart-context` | SMART workflow (Set→Map→Analyze→Retrieve→Trace) |
| `advise_parser_readiness` | `--parser-readiness` | Pre-flight check before parsing |
| `get_project_overview` | `--project-overview` | One-screen project snapshot |
| `get_project_summary` | (MCP-only) | Persistent architecture overview from disk-backed index |
| `check_project_health` | `--project-health` | Health-score per file + grade distribution |
| `check_file_health` | `--file-health` | One-file health score + actionable smells |
| `analyze_dependencies` | `--dependencies` | Import graph + cycle detection |
| `ast_cache` | `--ast-cache` | Index project / lookup / invalidate AST cache |
| `codegraph_call_graph` | `--call-graph` | Caller/callee graph (sqlite-backed) |
| `analyze_change_impact` | `--change-impact` | Blast radius + verification command for edits |
| `trace_impact` | `--trace-impact --trace-impact-symbol SYM` | Find every caller/usage site of a symbol |
| `refactoring_suggestions` | `--refactor` | Concrete refactor recipes for `code_patterns` findings |
| `safe_to_edit` | `--safe-to-edit` | Verdict + downstream caller risk |
| `modification_guard` | `--modification-guard --modification-guard-symbol SYM` | Pre-modification safety check (run BEFORE editing public symbol) |
| `smart_context` | `--smart-context --query "X"` | Targeted context for a symbol/file |
| `symbol_lineage` | `--symbol-lineage SYM` | Where a symbol was defined / renamed / moved |
| `code_patterns` | `--code-patterns` | Code smells (long_method, deep_nesting, god_class, sql_injection, …) |
| `detect_routes` | `--detect-routes` | Flask/Django/FastAPI/Express/Spring Boot routes |

## Adding a New MCP Tool

1. Create `tree_sitter_analyzer/mcp/tools/<name>_tool.py` extending `BaseMCPTool`.
2. Register it in `mcp/server.py` `tool_instances` list (the only place).
3. Add a CLI equivalent in `cli_main.py` or `cli/commands/` — **REQUIRED** by parity contract.
4. Add tests:
   - Tool envelope contract: `tests/unit/mcp/tools/test_tool_response_contract.py`
   - CLI equivalence: `tests/unit/cli/test_mcp_commands.py`
   - Agent contracts: `tests/unit/test_agent_contracts.py`
5. Default to `output_format="toon"` — never flip to JSON (see `CLAUDE.md`).

## Tool Response Envelope (canonical)

All tools return:

```jsonc
{
  "success": true|false,
  "...":  /* tool-specific payload */,
  "agent_summary": {
    "summary_line": "<file> <metrics> ...",  // one-line agent-readable summary
    "verdict": "SAFE|REVIEW|CAUTION|UNSAFE|ERROR",
    "next_step": "what to do next"
  },
  "verdict": "..."     // duplicated at top-level for fast triage
}
```

`verdict` semantics:
- `SAFE` — ship it
- `REVIEW` — needs human/agent attention but not blocking
- `CAUTION` — warnings present
- `UNSAFE` — critical findings, do not ship
- `ERROR` — tool input error

## Key Utility Modules

| File | Purpose |
|---|---|
| `mcp/utils/project_index.py` | Persistent project structure snapshot |
| `mcp/utils/search_cache.py` | LRU cache for fd/ripgrep results |
| `mcp/utils/file_output_factory.py` | Atomic file output for large payloads |
| `mcp/utils/error_handler.py` | Typed error envelopes |
| `mcp/utils/gitignore_detector.py` | `.gitignore` aware file filtering |
| `mcp/utils/edge_extractors/` | Per-language call graph edge extraction |
| `mcp/server_utils/smart_prompts.py` | LLM-facing system prompts for `smart_context` |
| `mcp/server_utils/tool_registration.py` | Tool → JSON Schema generation |

## See Also

- [`docs/api/mcp_tools_specification.md`](../api/mcp_tools_specification.md) — Full per-tool API
- [`docs/smart-workflow.md`](../smart-workflow.md) — SMART methodology
- [`docs/CODEMAPS/cli.md`](./cli.md) — CLI counterpart map
