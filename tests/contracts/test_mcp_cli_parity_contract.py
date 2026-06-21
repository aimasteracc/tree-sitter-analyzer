"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import os
import re
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+ stdlib
except ImportError:  # Python 3.10 — fall back to the tomli back-port
    import tomli as tomllib
from hypothesis import settings as hypothesis_settings

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.mcp.server import _create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKIPPED_SCAN_DIRS = {
    ".git",
    ".benchmark-repos",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
}


def test_registered_mcp_tools_have_cli_parity() -> None:
    """Every registered MCP tool must have a documented CLI access path."""
    parser = create_argument_parser()
    main_cli_options = {
        option for action in parser._actions for option in action.option_strings
    }

    with (PROJECT_ROOT / "pyproject.toml").open("rb") as f:
        scripts = tomllib.load(f)["project"]["scripts"]

    tool_to_cli = {
        "check_code_scale": ("main", "--metrics-only"),
        "analyze_code_structure": ("main", "--structure"),
        "get_code_outline": ("main", "--outline"),
        "extract_code_section": ("main", "--partial-read"),
        "query_code": ("main", "--query-key"),
        "list_files": ("script", "list-files"),
        "search_content": ("script", "search-content"),
        "find_and_grep": ("script", "find-and-grep"),
        "list_agent_skills": ("main", "--agent-skills"),
        "get_agent_workflow": ("main", "--agent-workflow"),
        "advise_parser_readiness": ("main", "--parser-readiness"),
        "get_project_overview": ("main", "--overview"),
        "check_project_health": ("main", "--project-health"),
        "check_file_health": ("main", "--file-health"),
        "analyze_dependencies": ("main", "--dependencies"),
        "analyze_change_impact": ("main", "--change-impact"),
        "refactoring_suggestions": ("main", "--refactor"),
        "safe_to_edit": ("main", "--safe-to-edit"),
        "smart_context": ("main", "--smart-context"),
        "symbol_lineage": ("main", "--symbol-lineage"),
        "code_patterns": ("main", "--code-patterns"),
        "codegraph_call_graph": ("main", "--call-graph"),
        "codegraph_callers": ("main", "--call-graph"),
        "codegraph_callees": ("main", "--call-graph"),
        # Tree primitives (mycelium RFC-0020/0021 parity).
        "codegraph_callee_tree": ("main", "--callee-tree"),
        "codegraph_caller_tree": ("main", "--caller-tree"),
        "codegraph_symbol_search": ("main", "--symbol-search"),
        "codegraph_resolve": ("main", "--symbol-resolve"),
        "ast_cache": ("main", "--ast-cache"),
        "ast_diff": ("main", "--ast-diff"),
        "codegraph_ast_path": ("main", "--ast-path"),
        "codegraph_overview": ("main", "--codegraph-overview"),
        "codegraph_navigate": ("main", "--codegraph-navigate"),
        # CodeGraph parity gap-closure (2026-05-24).
        "codegraph_status": ("main", "--codegraph-status"),
        "codegraph_context": ("main", "--codegraph-context"),
        "codegraph_explore": ("main", "--codegraph-explore"),
        "codegraph_query": ("main", "--codegraph-query"),
        "codegraph_impact": ("main", "--codegraph-impact"),
        "codegraph_pr_review": ("main", "--pr-review"),
        "semantic_classify": ("main", "--semantic-classify"),
        "detect_routes": ("main", "--detect-routes"),
        "codegraph_import_graph": ("main", "--import-graph"),
        "codegraph_dead_code": ("main", "--dead-code"),
        "codegraph_similarity": ("main", "--code-similarity"),
        # CodeGraph parity tools registered with codegraph_-prefixed names:
        # their CLI flags use the unprefixed form (--class-hierarchy,
        # --dependency-matrix) to keep the user-facing surface short.
        "codegraph_class_hierarchy": ("main", "--class-hierarchy"),
        "codegraph_class_inspect": ("main", "--class-inspect"),
        "codegraph_dependency_matrix": ("main", "--dependency-matrix"),
        # Feature 3 (Constraint DSL): MCP tool ``check_constraints`` ships
        # with the CLI flag ``--check-constraints`` for CLI/MCP parity.
        "check_constraints": ("main", "--check-constraints"),
        # Tools that already had CLI flags but were missing from this
        # mapping table while the server.py registry was stale. Now that
        # server.py delegates to the central registry, these come into
        # scope automatically.
        "codegraph_call_path": ("main", "--call-path"),
        "codegraph_xref": ("main", "--codegraph-xref"),
        "codegraph_sitemap": ("main", "--codegraph-sitemap"),
        "codegraph_complexity_heatmap": ("main", "--codegraph-complexity-heatmap"),
        "codegraph_visualize": ("main", "--codegraph-visualize"),
        "codegraph_uml": ("main", "--uml"),
        # PL-C sprint: the cache-management trio now has real CLI flags
        # (was ``mcp_only`` exemptions before).
        "codegraph_autoindex": ("main", "--autoindex"),
        "codegraph_full_index": ("main", "--full-index"),
        "codegraph_metrics": ("main", "--codegraph-metrics"),
        "codegraph_incremental_sync": ("main", "--incremental-sync"),
        # consolidated-only tools ported during merge of feat/autonomous-dev
        "trace_impact": ("main", "--trace-impact"),
        "modification_guard": ("main", "--modification-guard"),
        "batch_search": ("main", "--batch-search"),
        "build_project_index": ("main", "--build-project-index"),
        "check_tools": ("main", "--check-tools"),
        "decision_journal": ("main", "--decision-journal"),
        "doc_sync": ("main", "--doc-sync"),
        "codegraph_test_gap": ("main", "--test-gap"),
    }

    # ------------------------------------------------------------------
    # Wave C2 re-key: the MCP surface is now the 8 facades, NOT the 63
    # legacy tool names. ``tool_to_cli`` above is keyed by the legacy
    # CAPABILITY name (the thing that still owns a 1:1 CLI flag); the
    # parity contract is re-expressed as ``(facade, action) ↔ CLI flag``
    # via ``facade_map.LEGACY_TOOL_MAP``. The 62-row capability coverage
    # is PRESERVED (re-keyed, not deleted) per PRD §4/§5.
    # ------------------------------------------------------------------
    from tree_sitter_analyzer.mcp.facade_map import (
        FACADE_NAMES,
        LEGACY_TOOL_MAP,
        NEW_ACTION_PARITY,
        SET_PROJECT_PATH_TOOL_NAME,
    )

    registered_facades = {
        name for name, _tool in _create_tool_registry(str(PROJECT_ROOT))[0]
    }
    # 1. The registry exposes exactly the 8 facades (no legacy leakage).
    assert registered_facades == set(FACADE_NAMES)

    # 2. Every capability with a CLI flag re-keys to a live (facade, action)
    #    pair (or is the standalone set_project_path infra entry). Guards
    #    "no CLI capability lost its facade route during cutover".
    #    New-only actions (NEW_ACTION_PARITY) are also valid routes — they were
    #    never v1.x legacy names, so they live outside LEGACY_TOOL_MAP.
    unmapped_capabilities = [
        tool_name
        for tool_name in tool_to_cli
        if (
            tool_name not in LEGACY_TOOL_MAP
            and tool_name not in NEW_ACTION_PARITY
            and tool_name != SET_PROJECT_PATH_TOOL_NAME
        )
    ]
    assert unmapped_capabilities == [], (
        "These capabilities have a CLI flag but no (facade, action) route — "
        "they were dropped during the facade cutover: " + repr(unmapped_capabilities)
    )

    # 3. Every facade-routed capability keeps a CLI parity entry — re-keyed
    #    coverage stays 1:1 with the CLI surface (62-row preservation).
    missing_cli_for_route = sorted(set(LEGACY_TOOL_MAP) - set(tool_to_cli))
    assert missing_cli_for_route == [], (
        "These facade-backed capabilities have NO CLI parity entry — every "
        "(facade, action) must keep a documented CLI access path: "
        + repr(missing_cli_for_route)
    )

    # 3b. NEW_ACTION_PARITY entries also have live CLI flags (same bar as legacy).
    missing_cli_for_new_actions = [
        key
        for key, (_facade, _action, cli_flag) in NEW_ACTION_PARITY.items()
        if cli_flag not in main_cli_options
    ]
    assert missing_cli_for_new_actions == [], (
        "These new-action parity entries have NO CLI flag — every "
        "(facade, action) must keep a documented CLI access path: "
        + repr(missing_cli_for_new_actions)
    )

    # 4. The CLI flags themselves still resolve (main flag or console script).
    missing_main_flags = [
        cli_name
        for _tool_name, (kind, cli_name) in tool_to_cli.items()
        if kind == "main" and cli_name not in main_cli_options
    ]
    missing_scripts = [
        cli_name
        for _tool_name, (kind, cli_name) in tool_to_cli.items()
        if kind == "script" and cli_name not in scripts
    ]

    assert missing_main_flags == []
    assert missing_scripts == []


# ---------------------------------------------------------------------------
# Wave C2 facade-cutover contracts (PRD §5): discovery + delegation
# ---------------------------------------------------------------------------

# MCP server name used to compose the client-visible ``<server>__<tool>`` name.
# Cursor caps the composed name at 60 chars; the success metric (PRD §8) is
# ≤38 chars so even the longest facade leaves headroom.
_MCP_SERVER_NAME = "tree-sitter-analyzer"
_MAX_COMPOSED_TOOL_NAME = 38


def test_facade_discovery_exposes_exactly_eight_facades() -> None:
    """Discovery contract: the eager MCP surface is exactly the 8 facades.

    Guards the whole point of the cutover — if a regression re-registers the
    63 discrete tools (or drops a facade), the eager tool-definition token cost
    explodes again and Cursor/Roo break. Also enforces the ≤38-char composed
    name budget so ``tree-sitter-analyzer__<facade>`` never trips the Cursor
    60-char limit.
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry
    from tree_sitter_analyzer.mcp.facade_map import FACADE_NAMES

    tools, lookup = create_tool_registry(str(PROJECT_ROOT))
    names = [name for name, _tool in tools]

    assert len(names) == 8, f"Expected exactly 8 facades, got {len(names)}: {names}"
    assert set(names) == set(FACADE_NAMES)
    assert len(lookup) == 8

    for name in names:
        composed = f"{_MCP_SERVER_NAME}__{name}"
        assert len(composed) <= _MAX_COMPOSED_TOOL_NAME, (
            f"Composed MCP tool name {composed!r} is {len(composed)} chars — "
            f"exceeds the {_MAX_COMPOSED_TOOL_NAME}-char budget (Cursor 60-char "
            "limit headroom)."
        )

    # Each facade's definition advertises its action enum so an LLM can route.
    for _name, facade in tools:
        defn = facade.get_tool_definition()
        action_schema = defn["inputSchema"]["properties"]["action"]
        assert action_schema.get("enum"), f"{_name} facade exposes no action enum"


def test_all_facade_descriptions_contain_codegraph_keyword() -> None:
    """Fix ② discoverability contract: every facade description must contain
    the keyword 'codegraph' so headless agents searching 'codegraph' via
    ToolSearch land on a TSA facade instead of falling back to 2-3 wasted turns.

    This keyword is intentional and LOCKED (CLAUDE.md §1) — do NOT remove it
    from facade descriptions or revert this test.
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    _tools, lookup = create_tool_registry(str(PROJECT_ROOT))
    missing: list[str] = []
    for facade_name, facade in lookup.items():
        defn = facade.get_tool_definition()
        description = defn.get("description", "")
        if "codegraph" not in description.lower():
            missing.append(facade_name)

    assert missing == [], (
        "These facades are missing 'codegraph' in their description — agents "
        "searching for codegraph tools will not find them (fix ② regression): "
        + repr(missing)
    )


def test_facade_delegation_routes_each_action_to_expected_inner() -> None:
    """Delegation contract (PRD §5/§7): every (facade, action) reaches the
    expected inner tool instance.

    This is the verdict-envelope guard: the 9 unique-feature outputs
    (project-health A-F, smart_context, agent_summary, TOON, verdict ladder,
    ...) survive ONLY because facades delegate to the unchanged inner tools.
    If a facade ever re-implements an action inline (instead of delegating),
    or wires the wrong inner, this test fails before the envelope can drift.

    For ``action_map`` routes we assert the inner class name; for the bespoke
    routes (search.content, structure.read, nav.callers/callees — F5/R4) we
    assert the route is registered as a bespoke callable instead.
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    _tools, lookup = create_tool_registry(str(PROJECT_ROOT))

    # (facade, action) -> expected inner class name. Bespoke routes use the
    # sentinel ``"<bespoke>"`` because they delegate via a closure, not an
    # action_map entry. This table is the human-readable mirror of
    # facade_map.LEGACY_TOOL_MAP keyed by route.
    expected_inner: dict[tuple[str, str], str] = {
        ("search", "symbol"): "CodeGraphSymbolSearchTool",
        ("search", "query"): "QueryTool",
        ("search", "grep"): "FindAndGrepTool",
        ("search", "batch"): "BatchSearchTool",
        ("search", "chain"): "CodeGraphQueryTool",
        ("search", "select"): "HyphaeSelectTool",
        ("search", "subscribe"): "HyphaeSubscribeTool",
        ("search", "unsubscribe"): "HyphaeUnsubscribeTool",
        ("search", "content"): "<bespoke>",
        ("nav", "navigate"): "CodeGraphNavigateTool",
        ("nav", "call_path"): "CodeGraphCallPathTool",
        ("nav", "xref"): "CodeGraphXRefTool",
        ("nav", "resolve"): "CodeGraphSymbolResolveTool",
        ("nav", "lineage"): "SymbolLineageTool",
        ("nav", "impact"): "CodeGraphImpactTool",
        ("nav", "trace"): "TraceImpactTool",
        ("nav", "context"): "<bespoke>",
        ("nav", "callers"): "<bespoke>",
        ("nav", "callees"): "<bespoke>",
        ("nav", "callee_tree"): "CodeGraphCalleeTreeTool",
        ("nav", "caller_tree"): "CodeGraphCallerTreeTool",
        # RFC-0014 Phase B: test_map is a bespoke route (closure over impact_inner).
        ("nav", "test_map"): "<bespoke>",
        # RFC-0014 Phase C: co_change is a bespoke route (async wrapper for _compute_co_change).
        ("nav", "co_change"): "<bespoke>",
        ("structure", "outline"): "GetCodeOutlineTool",
        ("structure", "analyze"): "AnalyzeCodeStructureTool",
        ("structure", "signatures"): "<bespoke>",
        ("structure", "ast_path"): "CodeGraphASTPathTool",
        ("structure", "sitemap"): "CodeGraphSitemapTool",
        ("structure", "class_tree"): "ClassHierarchyTool",
        # class_detail is a bespoke route (#804) so query/symbol→class_name aliasing works.
        ("structure", "class_detail"): "<bespoke>",
        ("structure", "explore"): "CodeGraphExploreTool",
        ("structure", "read"): "<bespoke>",
        ("health", "project"): "ProjectHealthTool",
        ("health", "file"): "FileHealthTool",
        ("health", "scale"): "AnalyzeScaleTool",
        ("health", "patterns"): "CodePatternsTool",
        ("health", "heatmap"): "CodeGraphComplexityHeatmapTool",
        ("health", "imports"): "CodeGraphImportGraphTool",
        ("health", "matrix"): "CodeGraphDependencyMatrixTool",
        ("health", "dead"): "CodeGraphDeadCodeTool",
        ("health", "routes"): "RouteDetectorTool",
        ("health", "overview"): "CodeGraphOverviewTool",
        ("health", "deps"): "DependencyAnalysisTool",
        ("health", "test_gap"): "CodeGraphTestGapTool",
        ("edit", "safe"): "SafeToEditTool",
        ("edit", "guard"): "ModificationGuardTool",
        ("edit", "impact"): "ChangeImpactTool",
        ("edit", "refactor"): "RefactoringSuggestionsTool",
        ("edit", "constraints"): "ConstraintCheckTool",
        # _PRReviewViaFacade subclasses CodeGraphPRReviewTool so facade
        # action=pr implies mode=pr (#451 Codex P1); delegation to the
        # unchanged inner execute() is preserved via super().
        ("edit", "pr"): "_PRReviewViaFacade",
        ("edit", "classify"): "SemanticClassifyTool",
        ("edit", "ast_diff"): "ASTDiffTool",
        ("project", "overview"): "ProjectOverviewTool",
        ("project", "files"): "ListFilesTool",
        ("project", "smart"): "SmartContextTool",
        ("project", "parser"): "ParserReadinessTool",
        ("project", "tools"): "CheckToolsTool",
        ("project", "metrics"): "CodeGraphMetricsTool",
        ("project", "skills"): "AgentSkillsTool",
        ("project", "workflow"): "AgentWorkflowTool",
        ("project", "journal"): "DecisionJournalTool",
        ("project", "doc_sync"): "DocSyncTool",
        ("index", "status"): "CodeGraphStatusTool",
        ("index", "cache"): "ASTCacheTool",
        ("index", "build"): "BuildProjectIndexTool",
        ("index", "full"): "CodeGraphFullIndexTool",
        ("index", "auto"): "CodeGraphAutoIndexTool",
        ("index", "sync"): "CodeGraphIncrementalSyncTool",
        ("index", "knowledge"): "CodeGraphKnowledgeIndexTool",
        ("viz", "uml"): "CodeGraphUMLTool",
        ("viz", "graph"): "CodeGraphVisualizeTool",
        ("viz", "similarity"): "CodeGraphSimilarityTool",
        ("viz", "knowledge"): "CodeGraphKnowledgeGraphTool",
    }

    mismatches: list[str] = []
    for (facade_name, action), want in expected_inner.items():
        facade = lookup[facade_name]
        if want == "<bespoke>":
            if action not in facade.bespoke_map:
                mismatches.append(
                    f"{facade_name}.{action}: expected bespoke route, "
                    f"not registered in bespoke_map"
                )
            continue
        inner = facade.action_map.get(action)
        if inner is None:
            mismatches.append(
                f"{facade_name}.{action}: no action_map entry (expected {want})"
            )
            continue
        got = type(inner).__name__
        if got != want:
            mismatches.append(f"{facade_name}.{action}: routes to {got}, want {want}")

    assert mismatches == [], "Facade delegation drift:\n  " + "\n  ".join(mismatches)

    # Completeness: every action declared by a facade must be covered above —
    # otherwise a newly-added action could silently skip the delegation guard.
    declared: set[tuple[str, str]] = set()
    for facade_name, facade in lookup.items():
        for action in facade.action_map:
            declared.add((facade_name, action))
        for action in facade.bespoke_map:
            declared.add((facade_name, action))
    uncovered = sorted(declared - set(expected_inner))
    assert uncovered == [], (
        "These facade actions are not covered by the delegation table — add "
        f"them so the verdict-envelope guard stays complete: {uncovered}"
    )


def test_every_tool_declares_mcp_annotations() -> None:
    """Every registered MCP tool MUST set `annotations` in its tool definition.

    MCP spec defines 4 hints (readOnlyHint / destructiveHint / idempotentHint
    / openWorldHint) so clients (Cursor, Cline, Claude Desktop) know whether
    to show confirmation dialogs or treat the call as safe. Without these,
    every read-only `check_*` invocation could pop a "are you sure?" prompt
    — and worse, every destructive call could go through without warning.

    This test enforces:
      1. Every tool has an `annotations` key.
      2. All 4 hints are present and boolean-typed.
      3. The triple `readOnly=true` + `destructive=true` is impossible
         (mutually exclusive — would mean both safe AND destructive).
    """
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _ = create_tool_registry(str(PROJECT_ROOT))
    required_hints = {
        "readOnlyHint",
        "destructiveHint",
        "idempotentHint",
        "openWorldHint",
    }

    missing_annotations: list[str] = []
    missing_hints: list[str] = []
    contradictions: list[str] = []
    non_bool_hints: list[str] = []

    for name, tool in tools:
        defn = tool.get_tool_definition()
        ann = defn.get("annotations")
        if ann is None:
            missing_annotations.append(name)
            continue
        gaps = required_hints - set(ann)
        if gaps:
            missing_hints.append(f"{name}: missing {sorted(gaps)}")
            continue
        non_bool = [k for k in required_hints if not isinstance(ann[k], bool)]
        if non_bool:
            non_bool_hints.append(f"{name}: non-bool {non_bool}")
            continue
        if ann["readOnlyHint"] and ann["destructiveHint"]:
            contradictions.append(name)

    assert missing_annotations == [], (
        "These tools have no `annotations` block in their definition. "
        "Add readOnlyHint/destructiveHint/idempotentHint/openWorldHint "
        f"per MCP spec: {missing_annotations}"
    )
    assert missing_hints == [], (
        f"Tools with incomplete annotation hints: {missing_hints}"
    )
    assert non_bool_hints == [], (
        f"Hints must be Python bools, not strings: {non_bool_hints}"
    )
    assert contradictions == [], (
        "Tools cannot be both readOnly AND destructive — pick one. "
        f"Offenders: {contradictions}"
    )
