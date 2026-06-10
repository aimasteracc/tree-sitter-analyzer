<!-- Generated: 2026-05-22; Wave C2 facade cutover: 2026-06-02 -->
# MCP Tools Codemap

**8 facade tools** registered in [`mcp/_tool_registry.py`](../../tree_sitter_analyzer/mcp/_tool_registry.py)
(v2.0 β cutover — was 63 discrete tools). Each facade fans an `action` parameter
out to the unchanged inner tools; the 63 legacy names still work for one
deprecation cycle via the legacy-name shim
([`mcp/legacy_shim.py`](../../tree_sitter_analyzer/mcp/legacy_shim.py)).
All tools default to **TOON output** (locked — see `CLAUDE.md`).

## Facade Surface (public, eager — the only 8 tools clients see)

| MCP name | action= | Purpose |
|---|---|---|
| `search` | symbol / query / content / grep / batch / chain / select / subscribe / unsubscribe | Code search: BM25 symbol lookup, tree-sitter .scm DSL, ripgrep, fd+rg, batch, graph-chain DSL, Hyphae DSL, reactive push subscriptions (RFC-0001) |
| `nav` | navigate / call_path / xref / resolve / lineage / impact / trace / context / callers / callees | Call-graph navigation + one-call symbol context |
| `structure` | outline / analyze / ast_path / sitemap / class_tree / class_detail / explore / read | Structural AST analysis + partial file read |
| `health` | project / file / scale / patterns / heatmap / imports / matrix / dead / routes / overview / deps / test_gap | Code health, complexity, dependency analysis, untested symbol discovery |
| `edit` | safe / guard / impact / refactor / constraints / pr / classify / ast_diff | Edit-safety, blast-radius, refactor, PR review |
| `project` | overview / files / smart / parser / tools / metrics / skills / workflow / journal / doc_sync | Project-intelligence hub |
| `index` | status / cache / build / full / auto / sync | CodeGraph index lifecycle |
| `viz` | uml / graph / similarity | UML / graph diagrams + similarity |

> `set_project_path` remains a standalone infrastructure entry (not a facade
> action) because it mutates server-level state. Final client surface = **8
> facades + set_project_path**.

## Legacy Capability → Facade Crosswalk (deprecated names, still shimmed)

The table below documents the 62 legacy capabilities and their CLI flags. Each
legacy MCP name is now reached via its facade (`old_name` →
`facade action=<...>`); see [`mcp/facade_map.py`](../../tree_sitter_analyzer/mcp/facade_map.py).

| MCP name | CLI flag / handler | Purpose |
|---|---|---|
| `check_code_scale` | `--check-scale` | Per-file metrics (LOC, complexity, classes/methods/imports counts) |
| `analyze_code_structure` | `--table` / `--summary` | Full structural AST table |
| `get_code_outline` | `--outline` | Hierarchical outline (package → class → method) without method bodies |
| `extract_code_section` | `--partial-read --start-line N --end-line M` | Token-efficient line range |
| `query_code` | `--query-key methods --filter "public=true"` | tree-sitter query DSL |
| `list_files` | `list-files` subcommand (fd) | Discovery |
| `search_content` | `search-content` subcommand (ripgrep) | Regex search |
| `find_and_grep` | `find-and-grep` subcommand (fd+rg pipeline) | Combined find+grep |
| `batch_search` | `--batch-search` / `--batch-search-queries-json` | Multiple ripgrep searches in parallel (faster than sequential search_content) |
| `check_tools` | `--check-tools` | Verify fd + ripgrep are installed (and report versions) |
| `list_agent_skills` | `--list-skills` | Curated skill index for AI agents |
| `get_agent_workflow` | `--smart-context` | SMART workflow (Set→Map→Analyze→Retrieve→Trace) |
| `advise_parser_readiness` | `--parser-readiness` | Pre-flight check before parsing |
| `get_project_overview` | `--project-overview` | One-screen project snapshot |
| `build_project_index` | `--build-project-index` / `--build-project-index-roots` | Rebuild the persistent project index from scratch and save to disk |
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
| `ast_diff` | `--ast-diff` | Structural AST diff (signature vs body vs new/removed symbol) |
| `check_constraints` | `--check-constraints` | Evaluate architectural-constraints.yml against the tree |
| `decision_journal` | `--decision-journal` | Persistent log of architectural decisions |
| `doc_sync` | `--doc-sync` | Scan markdown docs for stale file-path references — backtick spans and link targets that no longer exist |
| `semantic_classify` | `--semantic-classify` | Classify code changes (risk + category) |
| **CodeGraph parity — symbol navigation** | | |
| `codegraph_context` | `--codegraph-context` | PRIMARY one-call architecture context from a natural-language task (entry points + graph + source blocks) |
| `codegraph_navigate` | `--codegraph-navigate` | PRIMARY symbol navigation hub (def + refs + hierarchy) |
| `codegraph_explore` | `--codegraph-explore` | BULK fetch N related symbols' source + relationship map |
| `codegraph_query` | `--codegraph-query` | jQuery-style chained graph query with lexical `search()`, offline `semantic()`, filter/exclude/has selection, cached relationship expansion, Mermaid `uml()` facets, compact answer packs, and evidence facets |
| `codegraph_symbol_search` | `--codegraph-symbol-search` | FTS5-powered symbol search over indexed project |
| `codegraph_resolve` | `--symbol-resolve` | Go-to-definition / find-all-references |
| `codegraph_ast_path` | `--ast-path` | "What is at file:line?" AST path/scope |
| **CodeGraph parity — call graph** | | |
| `codegraph_callers` | `--callers` | Who calls this function |
| `codegraph_callees` | `--callees` | What this function calls |
| `codegraph_call_path` | `--call-path` | BFS path between two functions via call edges |
| `codegraph_impact` | `--codegraph-impact` | Function-level blast radius; risk score from production edges only; always includes `tests` bucket (`test_callers_count`, `test_callees_count`); pass `include_tests=true` for file lists |
| `codegraph_dead_code` | `--dead-code` | Transitive dead functions / unused imports / unref vars |
| **CodeGraph parity — project-wide** | | |
| `codegraph_overview` | `--codegraph-overview` | Project-wide call graph intelligence |
| `codegraph_sitemap` | `--codegraph-sitemap` | Hierarchical project code map |
| `codegraph_complexity_heatmap` | `--codegraph-complexity-heatmap` | Cyclomatic complexity heatmap (per fn + project) |
| `codegraph_class_hierarchy` | `--class-hierarchy` | Class inheritance hierarchy |
| `codegraph_class_inspect` | `--class-inspect` | Inspect class methods with override detection |
| `codegraph_dependency_matrix` | `--dependency-matrix` | Module coupling matrix |
| `codegraph_import_graph` | `--import-graph` | File-level import dependency graph |
| `codegraph_xref` | `--codegraph-xref` | Multi-dimension cross-reference from AST cache |
| `codegraph_similarity` | `--code-similarity` | AST-structural clone detection |
| `codegraph_visualize` | `--codegraph-visualize` | Export call graph as Mermaid flowchart |
| `codegraph_uml` | `--uml` | Export UML-style Mermaid diagrams (class/package/component/sequence) |
| **CodeGraph parity — cache/index** | | |
| `codegraph_status` | `--codegraph-status` | INDEX HEALTH at-a-glance (indexed?, files, symbols, lag) |
| `codegraph_autoindex` | `--autoindex` | Transparent AST cache auto-indexing |
| `codegraph_full_index` | `--full-index` | One-shot complete project intelligence index |
| `codegraph_incremental_sync` | `--incremental-sync` | Content-hash diff re-index (SHA-256 per file) |
| `codegraph_metrics` | `--codegraph-metrics` | Aggregated project intelligence dashboard |
| **CodeGraph parity — review** | | |
| `codegraph_pr_review` | `--pr-review` | AST diff + semantic classify + blast-radius PR review |

## Adding a New MCP Tool

1. Create `tree_sitter_analyzer/mcp/tools/<name>_tool.py` extending `BaseMCPTool`.
2. Register it in `mcp/_tool_registry.py` (the canonical registry).
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
