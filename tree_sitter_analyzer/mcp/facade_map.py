#!/usr/bin/env python3
"""Single source of truth for the 8-facade MCP surface (Wave C2 cutover).

This module is the canonical crosswalk used by THREE consumers so they can
never drift apart:

1. ``server.call_tool`` / ``server_utils.tool_registration`` — the β legacy-name
   shim that forwards a deprecated 1.x tool name to ``facade.execute({action: ...})``.
2. ``tests/unit/test_agent_contracts.py`` — the re-keyed parity / codemap / skill
   contracts and the new discovery + delegation tests.
3. Future docs/skill generators (Wave D) that need old→new mappings.

Design (PRD §0 F3/F5, §2, §4, §6):

* ``FACADE_NAMES`` — the exactly-8 eager MCP tool names. Every name composed as
  ``tree-sitter-analyzer__<facade>`` must stay ≤38 chars (Cursor 60-char limit
  minus the 22-char ``tree-sitter-analyzer__`` prefix; see §8 success metric).
* ``LEGACY_TOOL_MAP`` — ``{old_tool_name: (facade, action)}`` covering all 62
  registry tools. ``set_project_path`` is NOT here: it stays a standalone
  infrastructure entry (see ``SET_PROJECT_PATH_TOOL_NAME``) because it mutates
  server-level state (analysis_engine / security_validator / rebind loop) that
  no inner tool can reach.
* ``FACADE_ACTION_TO_INNER`` — ``{(facade, action): inner_registry_name}`` — the
  delegation contract. ``codegraph_call_graph`` is reachable via the
  scope=graph branch of ``nav.callers``/``nav.callees`` (R4), so it maps to
  whichever inner the *default* (point) scope resolves to for the contract, and
  the graph branch is asserted separately.

F3 (LOCKED): ``query_code`` (tree-sitter .scm DSL) and ``codegraph_symbol_search``
(BM25 FTS) are DISTINCT actions (``search.query`` vs ``search.symbol``). They are
NOT merged — folding them would silently delete the tree-sitter query capability.
"""

from __future__ import annotations

# The standalone infrastructure entry that is NOT a facade and NOT shimmed.
SET_PROJECT_PATH_TOOL_NAME = "set_project_path"

# The exactly-8 eager facade tool names (public MCP surface).
FACADE_NAMES: tuple[str, ...] = (
    "search",
    "nav",
    "structure",
    "health",
    "edit",
    "project",
    "index",
    "viz",
)

# ---------------------------------------------------------------------------
# legacy old-tool-name -> (facade, action) crosswalk (β shim source of truth)
#
# Covers all 62 registry tool names. ``set_project_path`` is intentionally
# excluded (standalone infra entry). The order groups by facade for review.
# ---------------------------------------------------------------------------
LEGACY_TOOL_MAP: dict[str, tuple[str, str]] = {
    # -- search ------------------------------------------------------------
    "codegraph_symbol_search": ("search", "symbol"),
    "query_code": ("search", "query"),  # F3: tree-sitter .scm DSL (NOT symbol)
    "search_content": ("search", "content"),
    "find_and_grep": ("search", "grep"),
    "batch_search": ("search", "batch"),
    "codegraph_query": ("search", "chain"),
    # -- nav ---------------------------------------------------------------
    "codegraph_navigate": ("nav", "navigate"),
    "codegraph_call_path": ("nav", "call_path"),
    "codegraph_xref": ("nav", "xref"),
    "codegraph_resolve": ("nav", "resolve"),
    "symbol_lineage": ("nav", "lineage"),
    "codegraph_impact": ("nav", "impact"),
    "trace_impact": ("nav", "trace"),
    "codegraph_context": ("nav", "context"),
    "codegraph_callers": ("nav", "callers"),  # scope=point default
    "codegraph_callees": ("nav", "callees"),  # scope=point default
    # Tree primitives (mycelium RFC-0020/0021 parity): one call → nested tree.
    "codegraph_callee_tree": ("nav", "callee_tree"),
    "codegraph_caller_tree": ("nav", "caller_tree"),
    # R4: the call-graph tool is reachable via scope=graph on callers/callees.
    # The shim forwards the legacy name to callers scope=graph (mode=callers is
    # the historical default behaviour of codegraph_call_graph for an agent
    # asking "the call graph").
    "codegraph_call_graph": ("nav", "callers"),
    # -- structure ---------------------------------------------------------
    "get_code_outline": ("structure", "outline"),
    "analyze_code_structure": ("structure", "analyze"),
    "codegraph_ast_path": ("structure", "ast_path"),
    "codegraph_sitemap": ("structure", "sitemap"),
    "codegraph_class_hierarchy": ("structure", "class_tree"),
    "codegraph_class_inspect": ("structure", "class_detail"),
    "codegraph_explore": ("structure", "explore"),
    "extract_code_section": ("structure", "read"),
    # -- health ------------------------------------------------------------
    "check_project_health": ("health", "project"),
    "check_file_health": ("health", "file"),
    "check_code_scale": ("health", "scale"),
    "code_patterns": ("health", "patterns"),
    "codegraph_complexity_heatmap": ("health", "heatmap"),
    "codegraph_import_graph": ("health", "imports"),
    "codegraph_dependency_matrix": ("health", "matrix"),
    "codegraph_dead_code": ("health", "dead"),
    "detect_routes": ("health", "routes"),
    "codegraph_overview": ("health", "overview"),
    "analyze_dependencies": ("health", "deps"),
    # -- edit --------------------------------------------------------------
    "safe_to_edit": ("edit", "safe"),
    "modification_guard": ("edit", "guard"),
    "analyze_change_impact": ("edit", "impact"),
    "refactoring_suggestions": ("edit", "refactor"),
    "check_constraints": ("edit", "constraints"),
    "codegraph_pr_review": ("edit", "pr"),
    "semantic_classify": ("edit", "classify"),
    "ast_diff": ("edit", "ast_diff"),
    # -- project -----------------------------------------------------------
    "get_project_overview": ("project", "overview"),
    "list_files": ("project", "files"),
    "smart_context": ("project", "smart"),
    "advise_parser_readiness": ("project", "parser"),
    "check_tools": ("project", "tools"),
    "codegraph_metrics": ("project", "metrics"),
    "list_agent_skills": ("project", "skills"),
    "get_agent_workflow": ("project", "workflow"),
    "decision_journal": ("project", "journal"),
    "doc_sync": ("project", "doc_sync"),
    # -- index -------------------------------------------------------------
    "codegraph_status": ("index", "status"),
    "ast_cache": ("index", "cache"),
    "build_project_index": ("index", "build"),
    "codegraph_full_index": ("index", "full"),
    "codegraph_autoindex": ("index", "auto"),
    "codegraph_incremental_sync": ("index", "sync"),
    # -- viz ---------------------------------------------------------------
    "codegraph_uml": ("viz", "uml"),
    "codegraph_visualize": ("viz", "graph"),
    "codegraph_similarity": ("viz", "similarity"),
}


def legacy_to_facade(name: str) -> tuple[str, str] | None:
    """Return ``(facade, action)`` for a legacy tool name, else ``None``."""
    return LEGACY_TOOL_MAP.get(name)


def is_facade_name(name: str) -> bool:
    """True if ``name`` is one of the 8 live facade names."""
    return name in FACADE_NAMES
