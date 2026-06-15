# Migration Guide: v1.x → v2.0 (66 Tools → 8 Facades)

## Why 66 → 8?

Tree-sitter Analyzer v1.x registered **66 discrete MCP tools** into every connected client.
That worked on the CLI and in curl-style clients, but it created two real problems:

**Token cost.** Every MCP client (Roo Code, Cline, Copilot, Cursor) injects all tool
definitions into every prompt. With 66 tools the eager payload hit **24,318 tokens of
pure tool-definition overhead per session** — exactly the waste that TOON output was
designed to avoid. The irony: the server that saved 50-70% on *response* tokens was
burning 24k tokens on *discovery*.

**Client breakage.** Cursor caps composed MCP tool names at 60 characters
(`<server>__<tool>`). Several v1.x names were approaching that limit. Roo Code reports
degraded tool-selection accuracy above ~50 tools because the LLM's tool picker is
overwhelmed by near-duplicate names (`codegraph_callers` vs
`codegraph_call_graph mode=callers`).

v2.0 collapses all 66 tools into **8 domain facades** (`search`, `nav`, `structure`,
`health`, `edit`, `project`, `index`, `viz`). Each facade exposes an `action` parameter
that routes to the same inner logic. **No capability is removed** — every tool is
reachable via `(facade, action)`. The token cost drops to **~4,873 tokens (~80% less)**
day-one.

Comparison (tool count in eager MCP surface):

| Server | Tools |
|---|---|
| CodeGraph | ~12 |
| Rhizome / mycelium | 1 (unified) |
| **Tree-sitter Analyzer v2.0** | **8 (rich-output: verdict + TOON)** |
| Tree-sitter Analyzer v1.x | 66 |

---

## Shim: one release cycle, then removed

v2.0 ships a **backwards-compatibility shim** in the MCP server layer. Any call that
arrives using a v1.x tool name is transparently forwarded to the correct facade action.
The shim emits a deprecation warning on **stderr** and includes a `deprecation` field in
the response envelope so agent-side code can detect it:

```json
{
  "verdict": "INFO",
  "deprecation": "codegraph_callers is deprecated (v1.x). Use: nav action=callers",
  "data": { ... }
}
```

The shim is present in **v2.0 and v2.1** and will be removed in **v2.2**.

---

## Pin to v1.x (escape hatch)

If you need uninterrupted v1.x behaviour while your tooling migrates, pin:

```bash
pip install "tree-sitter-analyzer<2"
```

Or in `pyproject.toml`:

```toml
[tool.uv.sources]
tree-sitter-analyzer = { version = "<2" }
```

---

## Old → New crosswalk (all 66 legacy tools)

The table below is the canonical mapping maintained in
`tree_sitter_analyzer/mcp/facade_map.py`. The shim is derived from this same table.

### search facade

| v1.x tool name | v2.0 call |
|---|---|
| `codegraph_symbol_search` | `search` `action=symbol` |
| `query_code` | `search` `action=query` (tree-sitter .scm DSL — distinct from symbol search) |
| `search_content` | `search` `action=content` |
| `find_and_grep` | `search` `action=grep` |
| `batch_search` | `search` `action=batch` |
| `codegraph_query` | `search` `action=chain` |

### nav facade

| v1.x tool name | v2.0 call |
|---|---|
| `codegraph_navigate` | `nav` `action=navigate` |
| `codegraph_call_path` | `nav` `action=call_path` |
| `codegraph_xref` | `nav` `action=xref` |
| `codegraph_resolve` | `nav` `action=resolve` |
| `symbol_lineage` | `nav` `action=lineage` |
| `codegraph_impact` | `nav` `action=impact` |
| `trace_impact` | `nav` `action=trace` |
| `codegraph_context` | `nav` `action=context` |
| `codegraph_callers` | `nav` `action=callers` (default `scope=point`) |
| `codegraph_callees` | `nav` `action=callees` (default `scope=point`) |
| `codegraph_call_graph` | `nav` `action=callers` `scope=graph` |
| `codegraph_callee_tree` | `nav` `action=callee_tree` |
| `codegraph_caller_tree` | `nav` `action=caller_tree` |

### structure facade

| v1.x tool name | v2.0 call |
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

| v1.x tool name | v2.0 call |
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

| v1.x tool name | v2.0 call |
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

| v1.x tool name | v2.0 call |
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

### index facade

| v1.x tool name | v2.0 call |
|---|---|
| `codegraph_status` | `index` `action=status` |
| `ast_cache` | `index` `action=cache` |
| `build_project_index` | `index` `action=build` |
| `codegraph_full_index` | `index` `action=full` |
| `codegraph_autoindex` | `index` `action=auto` |
| `codegraph_incremental_sync` | `index` `action=sync` |

### viz facade

| v1.x tool name | v2.0 call |
|---|---|
| `codegraph_uml` | `viz` `action=uml` |
| `codegraph_visualize` | `viz` `action=graph` |
| `codegraph_similarity` | `viz` `action=similarity` |

---

## Infrastructure tool (not shimmed)

`set_project_path` is **not a facade** and not in the crosswalk above. It mutates
server-level state (analysis engine, security validator, inner-instance rebind) that
no inner tool can reach, so it stays as a standalone entry in v2.0. No migration needed.

---

## MCP call examples

**v1.x style (still works via shim through v2.1):**

```json
{ "tool": "codegraph_callers", "arguments": { "function_name": "execute" } }
```

**v2.0 style (preferred):**

```json
{ "tool": "nav", "arguments": { "action": "callers", "function_name": "execute" } }
```

**v2.0 graph scope (was `codegraph_call_graph`):**

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

The bundled `tsa-*` skills are updated in v2.0 as part of Wave D / G1.

---

## Deprecation timeline

| Version | Status |
|---|---|
| v1.x | All 66 tools live, no deprecation |
| **v2.0** | 8 facades live; shim forwards 66 legacy names with `deprecation` field |
| v2.1 | Shim still present; legacy names emit louder stderr warning |
| **v2.2** | Shim removed; legacy names return `NOT_FOUND` |

---

## See also

- `tree_sitter_analyzer/mcp/facade_map.py` — machine-readable crosswalk (single source of truth)
- `docs/CODEMAPS/mcp-tools.md` — agent-facing codemap (facades + legacy names)
- `AGENTS.md` — onboarding guide for AI agents
