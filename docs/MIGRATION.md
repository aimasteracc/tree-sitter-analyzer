# Migration Guide: published v1.29.5 → Unreleased develop

This guide describes the current develop implementation, compared with the published
v1.29.5 baseline. It does not assign a release version or announce a publication.
Both already expose **8 MCP facades plus `set_project_path`**; the facade cutover is
not a new change in this migration.

## Changes callers must handle

| Surface | Published v1.29.5 | Unreleased develop |
|---|---|---|
| MCP response encoding | TOON by default | JSON only; remove TOON decoding and consume the structured response envelope |
| CLI machine-readable encoding | JSON available | `--format json`; TOON is removed |
| Table rendering | Additional legacy table formats | `--table full` or `--table signatures`; compact/csv table modes are removed |
| Text-search wrappers | `search.content`, `search.grep`; legacy `search_content`, `find_and_grep`; `search-content`, `find-and-grep` commands | Removed; use the host's text/file search tools, or invoke a suitable text-search program directly |
| Remaining external-tool wrappers | Batch text search, file listing, tool checks | Still available: `search.batch`, `project.files`, `project.tools`, `list-files`, `--check-tools` |
| Internal file discovery and live symbol tracing | External search processes | Native discovery and a bounded Python source-scanning worker |

Indexed symbol search and AST queries serve code-intelligence tasks. They are not
replacements for arbitrary text search in unindexed files. Likewise, indexed
`structure action=sitemap` is not a live filesystem listing. Native source
occurrences are heuristic text evidence, not proof of AST call relationships.

Develop currently has **87 facade actions, 356 unique long CLI flags, and seven
console-script entry points**. The three published v1.29.5 routes `edit.rename`,
`health.unreachable`, and `health.middleware` remain available. Explicit rename
apply can write files; `edit.plan_rename` remains preview-only.

The remaining wrapper retirement is a separate proposal, not part of the current
implementation. Optional rg/fd integration is also under qualification; their
presence on PATH does not select a new core backend. See
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

The current shim forwards the **65 names** in
[`LEGACY_TOOL_MAP`](../tree_sitter_analyzer/mcp/facade_map.py). The removed
`search_content` and `find_and_grep` names are not forwarded. Callers should migrate
to facades rather than assume every historical name remains supported.

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

## Pin the published baseline

To keep the published behavior while migrating, pin its exact version:

```bash
pip install "tree-sitter-analyzer==1.29.5"
```

For a project, use the normal dependency specification:

```toml
[project]
dependencies = ["tree-sitter-analyzer==1.29.5"]
```

## Legacy name → current facade crosswalk

This table covers every name in the current `LEGACY_TOOL_MAP`. New facade-only
actions are listed in the [MCP codemap](CODEMAPS/mcp-tools.md).

### search facade

| Legacy tool name | Current call |
|---|---|
| `codegraph_symbol_search` | `search` `action=symbol` |
| `query_code` | `search` `action=query` |
| `batch_search` | `search` `action=batch` |
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
| `list_files` | `project` `action=files` |
| `smart_context` | `project` `action=smart` |
| `advise_parser_readiness` | `project` `action=parser` |
| `check_tools` | `project` `action=tools` |
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
