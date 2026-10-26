# Migration Guide

## v3.0 → v3.1.0

v3.1.0 adds `search action=uql` and changes no request shape, but several response values move onto the canonical envelope vocabulary. None of them makes an answer more confident. The full list, with the issue for each change, is in the [CHANGELOG](../CHANGELOG.md) under **3.1.0 → Behaviour changes and migration**.

| Surface | v3.0 | v3.1.0 | What to do |
|---|---|---|---|
| `index action=status` / `codegraph_status` `completeness` | `partial` (snapshot value) | `incomplete` plus a reason code; snapshot value in `snapshot_completeness` | compare against `incomplete`, or read `snapshot_completeness` |
| `health action=file` / `code_patterns` on empty or non-code files | `verdict: N/A` | `verdict: INFO` + `verdict_reason: EMPTY_FILE` / `NON_CODE_FILE` | branch on `verdict_reason` |
| Syntax-error short circuit (`safe_to_edit`, `smart_context`, `check_file_health`, `code_patterns`), failed `ast_diff` | `success: true`, `verdict: ERROR` | `success: false` + `error` + `error_code` (`SYNTAX_ERROR`, `LANGUAGE_UNSUPPORTED`, `AST_DIFF_FAILED`) | treat `success: false` as the failure signal |
| Unparseable constraint file / failed incremental sync | `CAUTION` / `WARN` | `ERROR` (`CONSTRAINT_CONFIG_INVALID` for constraints) | handle `ERROR` in gates |
| `codegraph_test_gap` `agent_summary` | string | dict; the text is in `summary_line` | read `summary_line` |
| Unscoped `nav action=callers` on a name with one definition | lists unproven same-name calls as callers | same answer as with its `file_path`; unproven sites move to `NAME_ONLY_INBOUND` / `NON_CALL_REFERENCES` evidence | read `name_only_sites` / `unresolved_inbound_sites` |
| `search action=tql_execute` | no completeness; unknown pseudo-class fails at evaluation; unknown attribute returns `[]` | `completeness` + `completeness_reasons`; both rejected at parse time with `error_code` and `fixed_selector` | fix the selector; use `fixed_selector` |
| `search action=chain` | documented | deprecated in the docs, still works, no warning | prefer `search action=uql` for multi-hop questions |
| `nav` answers without an index on Windows | `app\doc.py`, absolute paths in `trace` | repo-relative, forward-slash | drop downstream backslash repair |
| `dead_code` / overview orphans | functions used as values reported dead | not reported; findings carry `confidence` | filter on `confidence` |
| Automatic index workers | `cpu_count - 1` for 64+ files | one per 64 files, 2 … `cpu_count - 1` | set `TSA_INDEX_WORKERS` |
| Contributors: pytest `addopts` | `--reruns=1` | no global reruns | mark a genuinely flaky test `flaky(reruns=1)` with an issue |

The extractor version moves from 53 to 54. The next refresh re-extracts every file automatically, so the first refresh after upgrading costs about one cold index.

## v2.x → v3.0.0

v3.0.0 changes several default outputs and one CLI behaviour, and moves the index format forward. The full list, with the issue for each change, is in the [CHANGELOG](../CHANGELOG.md) under **3.0.0 → Breaking / behaviour changes and migration**.

| Surface | v2.x | v3.0.0 | To keep the old behaviour |
|---|---|---|---|
| `edit action=impact` / `--change-impact-full` | full lists (70–224 KB for a multi-file diff) | top entries with honest totals, within 24 KB | `include_details=true` / `--change-impact-include-details` |
| `index action=cache` / `--ast-cache` `files` detail | every file, cached ones included | changed / errored files only, at most 50 | `include_details=true` / `--ast-cache-include-details` |
| CLI `--watch` | starts a watcher and returns | holds until Ctrl-C, then stops the watcher | run it in the background, or use `--incremental-sync` for a one-shot refresh |
| `nav action=callers` with a bare name + `file_path` | could answer `complete` where `Class.method` did not | same gates as `Class.method` | none; read `name_only_sites` / `unresolved_inbound_sites` |
| Definition in an excluded file | `SYMBOL_NOT_DEFINED` | `SYMBOL_IN_EXCLUDED_FILE` | none |
| Index admission errors | text in `error` | typed `error_code` / `cause_code` / `retryable` / `next_action`; `INDEX_CANDIDATE_UNBOUND` is new | branch on `error_code` |
| `viz action=graph` node ids | `<file>::<name>` | `<file>::<Owner>.<name>@<line>` | re-derive stored ids |

The index (manifest v3, schema 18, extractor version 53) is upgraded automatically by the next refresh. v2.x readers treat a v3 manifest as not certified and fail closed, so downgrading costs a re-index, not a wrong certified answer.

## v1.x → v2.0.0

This guide describes the breaking search-surface and encoding changes released in v2.0.0. The 8 MCP facades plus `set_project_path` remain the stable top-level surface.

## Changes callers must handle

| Surface | v1.x | v2.0.0 |
|---|---|---|
| MCP response encoding | TOON by default | JSON only; remove TOON decoding and consume the structured response envelope |
| CLI machine-readable encoding | JSON available | `--format json`; TOON is removed |
| Table rendering | Additional legacy table formats | `--table full` or `--table signatures`; compact/csv table modes are removed |
| Text-search wrappers | `search.content`, `search.grep`; legacy `search_content`, `find_and_grep`; `search-content`, `find-and-grep` commands | Removed; use bounded native `search action=text` / `--text-search` for literal live-source search |
| External-tool wrappers | `search.batch`, `project.files`, `project.tools`, `list-files`, `--check-tools` | Removed; use native literal search, indexed search/structure views, or bounded trace according to the task |
| Internal file discovery and live symbol tracing | External search processes | Native discovery and a bounded Python source-scanning worker |
| Python MCP compatibility classes | `MCPTool`, `UniversalAnalyzeTool`, and `server.universal_analyze_tool` | Removed; extend `BaseMCPTool` and use `structure action=analyze` / `AnalyzeCodeStructureTool` |

Indexed symbol search and AST queries serve code-intelligence tasks. They are not
replacements for arbitrary text search in unindexed files. Likewise, indexed
`structure action=sitemap` is not a live filesystem listing. Native source
occurrences are heuristic text evidence, not proof of AST call relationships.

The v2.0.0 surface has **85 facade actions, 361 unique long CLI flags, and six console-script entry points**. The three published v1.29.5 routes `edit.rename`,
`health.unreachable`, and `health.middleware` remain available. Explicit rename
apply can write files; `edit.plan_rename` remains preview-only.

The wrapper retirement ships in v2.0.0. Optional rg/fd acceleration remains a separate qualification effort; executables on PATH never change the core backend automatically. See
[RFC-0033](../rfcs/0033-native-search-independence.md) and
[RFC-0034](../rfcs/0034-optional-search-backend-qualification.md).

## JSON and index migration

Update clients to parse JSON and preserve the response envelope, including error,
truncation and evidence fields. CLI diagnostics stay on stderr. Human-readable
legacy CLI paths may still use `--output-format text`; this is not an alternate
MCP encoding. No global `--format text`, `--format toon`, or `--table csv` exists.

Rebuild indexes after upgrading when extractor/schema compatibility requires it.
For an explicit AST index build and subsequent indexed structure view:

```bash
uv run python -m tree_sitter_analyzer --ast-cache --ast-cache-mode index --format json
uv run python -m tree_sitter_analyzer --codegraph-sitemap --codegraph-sitemap-mode flat --format json
```

## Legacy-name compatibility

The current shim forwards the **62 names** in
[`LEGACY_TOOL_MAP`](../tree_sitter_analyzer/mcp/facade_map.py). The removed
`search_content`, `find_and_grep`, `batch_search`, `list_files`, and `check_tools`
names are not forwarded. Callers should migrate to facades rather than assume every
historical name remains supported.

A forwarded dictionary response receives a `deprecation` object; the shim also
emits a warning on stderr. Example of that field, with the tool-specific response
fields omitted:

```json
{
  "deprecation": {
    "deprecated": true,
    "old_name": "codegraph_callers",
    "facade": "nav",
    "action": "callers",
    "message": "'codegraph_callers' is deprecated; call 'nav' with action='callers'. The legacy name works for one release cycle."
  }
}
```

This describes present behavior, not a new promise about a future shim-removal
version. Follow the migration notes for the selected release before upgrading.

## Install v2.0.0

```bash
pip install --upgrade "tree-sitter-analyzer==2.0.0"
```

## Pin the published v1 baseline

To keep the latest v1 behavior while migrating, pin its exact version:

```bash
pip install "tree-sitter-analyzer==1.32.0"
```

For a project, use the normal dependency specification:

```toml
[project]
dependencies = ["tree-sitter-analyzer==1.32.0"]
```

## Legacy name → current facade crosswalk

This table covers every name in the current `LEGACY_TOOL_MAP`. New facade-only
actions are listed in the [MCP codemap](CODEMAPS/mcp-tools.md).

### search facade

| Legacy tool name | Current call |
|---|---|
| `codegraph_symbol_search` | `search` `action=symbol` |
| `query_code` | `search` `action=query` |
| `codegraph_query` | `search` `action=chain` |

### nav facade

| Legacy tool name | Current call |
|---|---|
| `codegraph_navigate` | `nav` `action=navigate` |
| `codegraph_call_path` | `nav` `action=call_path` |
| `codegraph_xref` | `nav` `action=xref` |
| `codegraph_resolve` | `nav` `action=resolve` |
| `symbol_lineage` | `nav` `action=lineage` |
| `codegraph_impact` | `nav` `action=impact` |
| `trace_impact` | `nav` `action=trace` |
| `codegraph_context` | `nav` `action=context` |
| `codegraph_callers` | `nav` `action=callers` |
| `codegraph_callees` | `nav` `action=callees` |
| `codegraph_callee_tree` | `nav` `action=callee_tree` |
| `codegraph_caller_tree` | `nav` `action=caller_tree` |
| `codegraph_call_graph` | `nav` `action=callers` `scope=graph` |

### structure facade

| Legacy tool name | Current call |
|---|---|
| `get_code_outline` | `structure` `action=outline` |
| `analyze_code_structure` | `structure` `action=analyze` |
| `codegraph_ast_path` | `structure` `action=ast_path` |
| `codegraph_sitemap` | `structure` `action=sitemap` |
| `codegraph_class_hierarchy` | `structure` `action=class_tree` |
| `codegraph_class_inspect` | `structure` `action=class_detail` |
| `codegraph_explore` | `structure` `action=explore` |
| `extract_code_section` | `structure` `action=read` |

### health facade

| Legacy tool name | Current call |
|---|---|
| `check_project_health` | `health` `action=project` |
| `check_file_health` | `health` `action=file` |
| `check_code_scale` | `health` `action=scale` |
| `code_patterns` | `health` `action=patterns` |
| `codegraph_complexity_heatmap` | `health` `action=heatmap` |
| `codegraph_import_graph` | `health` `action=imports` |
| `codegraph_dependency_matrix` | `health` `action=matrix` |
| `codegraph_dead_code` | `health` `action=dead` |
| `detect_routes` | `health` `action=routes` |
| `codegraph_overview` | `health` `action=overview` |
| `analyze_dependencies` | `health` `action=deps` |
| `codegraph_test_gap` | `health` `action=test_gap` |

### edit facade

| Legacy tool name | Current call |
|---|---|
| `safe_to_edit` | `edit` `action=safe` |
| `modification_guard` | `edit` `action=guard` |
| `analyze_change_impact` | `edit` `action=impact` |
| `refactoring_suggestions` | `edit` `action=refactor` |
| `check_constraints` | `edit` `action=constraints` |
| `codegraph_pr_review` | `edit` `action=pr` |
| `semantic_classify` | `edit` `action=classify` |
| `ast_diff` | `edit` `action=ast_diff` |

### project facade

| Legacy tool name | Current call |
|---|---|
| `get_project_overview` | `project` `action=overview` |
| `smart_context` | `project` `action=smart` |
| `advise_parser_readiness` | `project` `action=parser` |
| `codegraph_metrics` | `project` `action=metrics` |
| `list_agent_skills` | `project` `action=skills` |
| `get_agent_workflow` | `project` `action=workflow` |
| `decision_journal` | `project` `action=journal` |
| `doc_sync` | `project` `action=doc_sync` |
| `get_project_summary` | `project` `action=card` |

### index facade

| Legacy tool name | Current call |
|---|---|
| `codegraph_status` | `index` `action=status` |
| `ast_cache` | `index` `action=cache` |
| `build_project_index` | `index` `action=build` |
| `codegraph_full_index` | `index` `action=full` |
| `codegraph_autoindex` | `index` `action=auto` |
| `codegraph_incremental_sync` | `index` `action=sync` |

### viz facade

| Legacy tool name | Current call |
|---|---|
| `codegraph_uml` | `viz` `action=uml` |
| `codegraph_visualize` | `viz` `action=graph` |
| `codegraph_similarity` | `viz` `action=similarity` |

## Infrastructure tool (not shimmed)

`set_project_path` is **not a facade** and not in the crosswalk above. It mutates
server-level state (analysis engine, security validator, inner-instance rebind) that
no inner tool can reach, so it stays as a standalone entry in both baselines. No migration needed.

---

## MCP call examples

**Legacy name (currently forwarded by the shim):**

```json
{ "tool": "codegraph_callers", "arguments": { "function_name": "execute" } }
```

**Facade call (preferred):**

```json
{ "tool": "nav", "arguments": { "action": "callers", "function_name": "execute" } }
```

**Graph scope (legacy `codegraph_call_graph`):**

```json
{ "tool": "nav", "arguments": { "action": "callers", "function_name": "execute", "scope": "graph" } }
```

---

## Agent skill allowlists

If you maintain custom agent skills that list
`mcp__tree-sitter-analyzer__<legacy_tool>` in their `allowed-tools` frontmatter, update
each entry to reference the facade:

```yaml
# before
allowed-tools:
  - mcp__tree-sitter-analyzer__codegraph_callers
  - mcp__tree-sitter-analyzer__codegraph_symbol_search

# after
allowed-tools:
  - mcp__tree-sitter-analyzer__nav
  - mcp__tree-sitter-analyzer__search
```

Use the bundled `tsa-*` skills that match the installed TSA version.

---

## See also

- `tree_sitter_analyzer/mcp/facade_map.py` — machine-readable crosswalk (single source of truth)
- `docs/CODEMAPS/mcp-tools.md` — agent-facing codemap (facades + legacy names)
- `AGENTS.md` — onboarding guide for AI agents
