# MCP Facade Action Reference

> **AUTO-GENERATED — do not edit by hand.** Regenerate with `uv run python scripts/generate_facade_actions_doc.py`.
> Drift-gated by `tests/unit/docs/test_facade_actions_doc_drift.py` (regenerates in-memory and diffs).

The MCP server exposes **8 facade tools** routing **73 actions** via the `action` parameter. This reference is generated from the live facade registry (`tree_sitter_analyzer/mcp/_tool_registry.py`) and each inner tool's `inputSchema` — the same schema the runtime strict-parameter guard enforces, so a wrong param guess in this table would fail at runtime too (and vice versa).

Reading the tables:

- **Params** — accepted top-level parameters; `*` marks required ones. Facades mechanically alias the canonical `symbol` onto inner `function_name`/`class_name` params (noted inline). Every facade also accepts `action` (required) itself.
- **Response keys** — the statically declared `ToolResponse` envelope (`get_output_schema()`); `*` marks guaranteed keys. `error` appears on failures. "+ action payload" means the action layers its own result keys on top (`additionalProperties: true`); payload shapes are not statically declared, so they are not listed here — see the facade description for per-action semantics.
- **CLI twin** — the CLI flag (or console script) covering the same capability, from the CLI-parity contract. 4 actions have no authoritative CLI mapping and show — (honest gap, not an omission).
- *Bespoke routes* (closures with hand-rolled arg handling, e.g. `nav action=test_map`) have their params pinned in the generator with source provenance; the generator fails if the live route set drifts from those pins.

## `search` — 9 actions

| Action | Params (required `*`) | Response keys (top-level) | CLI twin |
| --- | --- | --- | --- |
| `batch` | `queries`* | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--batch-search` |
| `chain` | `query`*, `compact`, `include_code`, `max_files`, `max_symbols`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-query` |
| `content` | `query`*, `case`, `context`, `context_after`, `context_before`, `count_only_matches`, `enable_parallel`, `encoding`, `exclude_globs`, `exclude_types`, `extensions`, `file_types`, `files`, `files_with_matches`, `fixed_strings`, `follow_symlinks`, `group_by_file`, `hidden`, `include_globs`, `include_stats`, `invert_match`, `max_count`, `max_depth`, `max_filesize`, `multiline`, `no_ignore`, `only_matching`, `optimize_paths`, `output_file`, `output_format`, `pcre2`, `roots`, `sort`, `summary_only`, `suppress_output`, `timeout_ms`, `total_only`, `word` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `search-content` (console script) |
| `grep` | `query`*, `roots`*, `case`, `changed_before`, `changed_within`, `context_after`, `context_before`, `count_only_matches`, `depth`, `encoding`, `exclude`, `exclude_globs`, `extensions`, `file_limit`, `fixed_strings`, `follow_symlinks`, `full_path_match`, `glob`, `group_by_file`, `hidden`, `include_globs`, `max_count`, `max_filesize`, `multiline`, `no_ignore`, `optimize_paths`, `output_file`, `output_format`, `pattern`, `size`, `sort`, `summary_only`, `suppress_output`, `timeout_ms`, `total_only`, `types`, `word` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `find-and-grep` (console script) |
| `query` | `file_path`, `filter`, `find_references`, `language`, `max_count`, `output_file`, `output_format`, `query_key`, `query_string`, `result_format`, `suppress_output`, `symbol`, `symbol_type` — requires `file_path` or `symbol`; file-scoped queries take exactly one of `query_key`/`query_string` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--query-key` |
| `select` | `selector`*, `max_results`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | — |
| `subscribe` | `selector`*, `min_interval`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | — |
| `symbol` | `query`*, `kind`, `language`, `limit`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--symbol-search` |
| `unsubscribe` | `output_format`, `selector`, `sub_id` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | — |

## `nav` — 14 actions

| Action | Params (required `*`) | Response keys (top-level) | CLI twin |
| --- | --- | --- | --- |
| `call_path` | `source_function`*, `target_function`*, `direction`, `max_depth`, `max_paths`, `output_format`, `source_file`, `target_file` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--call-path` |
| `callee_tree` | `symbol`*, `file_path`, `max_depth`, `max_nodes`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--callee-tree` |
| `callees` | `function_name`* (or `symbol` as alias), `scope` (point\|graph, default point), `file_path`, `limit` (scope=point), `depth` (scope=graph), `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--call-graph` |
| `caller_tree` | `symbol`*, `file_path`, `max_depth`, `max_nodes`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--caller-tree` |
| `callers` | `function_name`* (or `symbol` as alias), `scope` (point\|graph, default point), `file_path`, `limit` (scope=point), `depth` (scope=graph), `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--call-graph` |
| `co_change` | `symbol` or `file_path` (one required), `max_commits` (default 500), `min_shared` (default 3), `max_results` (default 20), `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--co-change` |
| `context` | `task`* (or `symbol`/`query` as alias), `max_nodes`, `max_code_blocks`, `include_graph`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-context` |
| `impact` | `mode`*, `depth`, `file_path`, `function_name` (`symbol` aliases `function_name`), `function_names`, `include_tests`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-impact` |
| `lineage` | `symbol`*, `file_paths`, `max_depth`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--symbol-lineage` |
| `navigate` | `symbol`*, `depth`, `file_path`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-navigate` |
| `resolve` | `symbol`*, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--symbol-resolve` |
| `test_map` | `symbol`* (or `function_name` as alias), `file_path`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--test-map` |
| `trace` | `symbol`*, `case_sensitive`, `exclude_patterns`, `file_path`, `max_results`, `project_root`, `word_match` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--trace-impact` |
| `xref` | `file_path`, `include_callees`, `include_callers`, `include_file_deps`, `include_imports`, `mode`, `output_format`, `symbol` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-xref` |

## `structure` — 9 actions

| Action | Params (required `*`) | Response keys (top-level) | CLI twin |
| --- | --- | --- | --- |
| `analyze` | `file_path`*, `format_type`, `language`, `output_file`, `output_format`, `suppress_output` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--structure` |
| `ast_path` | `file_path`*, `language`, `line`, `max_depth`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--ast-path` |
| `class_detail` | `class_name`* (or `query`/`symbol` as alias), `language`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--class-inspect` |
| `class_tree` | `class_name` (`symbol` aliases `class_name`), `max_depth`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--class-hierarchy` |
| `explore` | `includeCode`, `maxFiles`, `maxSymbols`, `output_format`, `query`, `symbol`, `symbols` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-explore` |
| `outline` | `file_path`*, `include_fields`, `include_imports`, `language`, `listed_cap`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--outline` |
| `read` | single: `file_path`* + `start_line`* [+ `end_line`, `start_column`, `end_column`, `format`, `output_file`, `suppress_output`, `output_format`, `allow_truncate`, `fail_fast`]; batch: `requests`* | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--partial-read` |
| `signatures` | `file_path`*, `language`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | — |
| `sitemap` | `directory`, `language`, `max_files`, `max_symbols`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-sitemap` |

## `health` — 12 actions

| Action | Params (required `*`) | Response keys (top-level) | CLI twin |
| --- | --- | --- | --- |
| `dead` | `include_test_files`, `max_dead`, `max_imports`, `max_variables`, `mode`, `output_format`, `path` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--dead-code` |
| `deps` | `file_path`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--dependencies` |
| `file` | `file_path`*, `compact_only`, `language`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--file-health` |
| `heatmap` | `directory`, `file_path`, `function_name` (`symbol` aliases `function_name`), `language`, `max_files`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-complexity-heatmap` |
| `imports` | `file_path`, `max_depth`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--import-graph` |
| `matrix` | `mode`*, `file_path`, `output_format`, `threshold`, `top_k` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--dependency-matrix` |
| `overview` | `max_coupled_files`, `max_dead`, `max_entry_points`, `max_hubs`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-overview` |
| `patterns` | `file_path`*, `categories`, `output_format`, `severity_threshold` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--code-patterns` |
| `project` | `compact_only`, `max_files`, `min_grade`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--project-health` |
| `routes` | `file_path`, `framework`, `mode`, `output_format`, `url_pattern` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--detect-routes` |
| `scale` | `file_path`, `file_paths`, `include_complexity`, `include_details`, `include_guidance`, `language`, `metrics_only`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--metrics-only` |
| `test_gap` | `coverage_json`, `file_path`, `include_covered`, `language`, `max_files`, `max_gaps`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--test-gap` |

## `edit` — 8 actions

| Action | Params (required `*`) | Response keys (top-level) | CLI twin |
| --- | --- | --- | --- |
| `ast_diff` | `file_path`, `include_node_bodies`, `language`, `mode`, `new_file`, `new_ref`, `new_source`, `old_file`, `old_ref`, `old_source`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--ast-diff` |
| `classify` | `file_path`, `hunk_cap`, `include_ast_nodes`, `language`, `mode`, `new_ref`, `new_source`, `old_ref`, `old_source`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--semantic-classify` |
| `constraints` | `output_format`, `path_filter`, `severity_min` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--check-constraints` |
| `guard` | `modification_type`*, `symbol`*, `file_path` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--modification-guard` |
| `impact` | `agent_summary_only`, `compact_only`, `include_tests`, `mode`, `output_format`, `pr_url`, `resource_profile`, `scope_mode`, `scope_paths` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--change-impact` |
| `pr` | `include_call_graph`, `mode`, `output_format`, `pr_url` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--pr-review` |
| `refactor` | `file_path`*, `include_extractions`, `include_skeleton`, `language`, `max_suggestions`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--refactor` |
| `safe` | `file_path`*, `compact_only`, `edit_type`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--safe-to-edit` |

## `project` — 10 actions

| Action | Params (required `*`) | Response keys (top-level) | CLI twin |
| --- | --- | --- | --- |
| `doc_sync` | `doc_patterns`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--doc-sync` |
| `files` | `absolute`, `changed_before`, `changed_within`, `count_only`, `depth`, `exclude`, `extensions`, `follow_symlinks`, `full_path_match`, `glob`, `hidden`, `limit`, `min_depth`, `no_ignore`, `one_file_system`, `output_file`, `output_format`, `path`, `pattern`, `prune`, `roots`, `show_errors`, `size`, `strip_cwd_prefix`, `suppress_output`, `threads`, `types` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `list-files` (console script) |
| `journal` | `alternatives`, `id`, `limit`, `mode`, `new_id`, `output_format`, `path_scope`, `query`, `rationale`, `related_symbols`, `scope_paths`, `tags`, `title`, `verdict`, `verdict_filter` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--decision-journal` |
| `metrics` | `output_format`, `sections` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-metrics` |
| `overview` | `include_health`, `max_depth`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--overview` |
| `parser` | `include_supported`, `language`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--parser-readiness` |
| `skills` | `output_format`, `skills_root` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--agent-skills` |
| `smart` | `file_path`*, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--smart-context` |
| `tools` | (none) | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--check-tools` |
| `workflow` | `output_format`, `target_path` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--agent-workflow` |

## `index` — 7 actions

| Action | Params (required `*`) | Response keys (top-level) | CLI twin |
| --- | --- | --- | --- |
| `auto` | `max_files`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--autoindex` |
| `build` | `add_notes`, `roots` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--build-project-index` |
| `cache` | `backend`, `file_path`, `force`, `include_activation`, `language`, `limit`, `max_files`, `mode`, `poll_interval`, `query`, `symbol` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--ast-cache` |
| `full` | `include_activation`, `max_files`, `mode`, `output_format`, `resolve_synapse` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--full-index` |
| `knowledge` | `backend`, `focus`, `include_docs`, `include_symbols`, `level`, `max_edges`, `max_files`, `max_nodes`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--knowledge-graph-index` |
| `status` | `include_lag`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-status` |
| `sync` | `max_files`, `mode`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--incremental-sync` |

## `viz` — 4 actions

| Action | Params (required `*`) | Response keys (top-level) | CLI twin |
| --- | --- | --- | --- |
| `graph` | `depth`, `direction`, `file_path`, `function`, `max_edges`, `mode`, `output_format`, `visualization_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--codegraph-visualize` |
| `knowledge` | `export_format`, `focus`, `lod`, `max_edges`, `max_nodes`, `output_format` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--knowledge-graph-export` |
| `similarity` | `include_bodies`, `max_groups`, `min_group_size`, `min_lines`, `mode`, `output_format`, `path_filter`, `use_cache` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--code-similarity` |
| `uml` | `class_name` (`symbol` aliases `class_name`), `diagram`, `file_path`, `function_name` (`symbol` aliases `function_name`), `include_external_bases`, `include_tests`, `max_depth`, `max_edges`, `max_nodes`, `max_paths`, `output_format`, `package_depth`, `source`, `target` | `success`*, `verdict`*, `agent_summary`, `error` + action payload | `--uml` |
