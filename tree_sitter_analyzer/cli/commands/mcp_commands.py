#!/usr/bin/env python3
"""MCP-equivalent CLI command handlers."""

import asyncio
import os
from collections.abc import Callable, Mapping
from typing import Any

from tree_sitter_analyzer.cli.commands.mcp_command_helpers import (
    McpCommandSpec,
    build_mcp_tool_args,
    find_selected_mcp_command,
    validate_mcp_command_args,
)

# These imports look unused — they're consumed via ``globals()`` inside
# :func:`_get_tool_class` so that tests can monkeypatch the names at
# module level — see ``tests/unit/cli/test_mcp_commands.py``.
# noqa codes keep refactor-cleaner / autoflake / ruff from stripping them.
from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool  # noqa: F401
from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool  # noqa: F401
from tree_sitter_analyzer.mcp.tools.ast_path_tool import (
    CodeGraphASTPathTool,  # noqa: F401
)

# consolidated-only tools ported during merge of feat/autonomous-dev
from tree_sitter_analyzer.mcp.tools.batch_search_tool import (
    BatchSearchTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.build_project_index_tool import (
    BuildProjectIndexTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.call_graph_tool import (
    CodeGraphCallTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.call_path_tool import (
    CodeGraphCallPathTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.callees_tool import (
    CodeGraphCalleesTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.callers_tool import (
    CodeGraphCallersTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.change_impact_tool import (
    ChangeImpactTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.check_tools_tool import (
    CheckToolsTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.class_hierarchy_tool import (
    ClassHierarchyTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
    CodePatternsTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.code_similarity_tool import (
    CodeGraphSimilarityTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_explore_tool import (
    CodeGraphExploreTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_impact_tool import (
    CodeGraphImpactTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_navigate_tool import (
    CodeGraphNavigateTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_overview_tool import (
    CodeGraphOverviewTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_pr_review_tool import (
    CodeGraphPRReviewTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import (
    CodeGraphSitemapTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
    CodeGraphStatusTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_visualize_tool import (
    CodeGraphVisualizeTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_xref_tool import (
    CodeGraphXRefTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.complexity_heatmap_tool import (
    CodeGraphComplexityHeatmapTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.dead_code_tool import (
    CodeGraphDeadCodeTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.decision_journal_tool import (
    DecisionJournalTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
    DependencyAnalysisTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.dependency_matrix_tool import (
    CodeGraphDependencyMatrixTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool  # noqa: F401
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
    GetCodeOutlineTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.import_graph_tool import (
    CodeGraphImportGraphTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.modification_guard_tool import (
    ModificationGuardTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.parser_readiness_tool import (
    ParserReadinessTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.project_health_tool import (
    ProjectHealthTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.project_overview_tool import (
    ProjectOverviewTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.refactoring_suggestions_tool import (
    RefactoringSuggestionsTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.route_detector_tool import (
    RouteDetectorTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    SafeToEditTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
    SemanticClassifyTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.smart_context_tool import (
    SmartContextTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import (
    SymbolLineageTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.symbol_resolve_tool import (
    CodeGraphSymbolResolveTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.symbol_search_tool import (
    CodeGraphSymbolSearchTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
    TraceImpactTool,  # noqa: F401
)

_DEPENDENCY_FILE_SCOPED_MODES = {"blast_radius", "file_deps"}
_DEPENDENCY_MODE_ALIASES = {"full": "summary"}


def _normalize_dependency_mode(mode: str | None) -> str:
    return _DEPENDENCY_MODE_ALIASES.get(mode or "summary", mode or "summary")


def _dependency_mode_requires_file(args: Any) -> bool:
    return (
        _normalize_dependency_mode(getattr(args, "dependencies", None))
        in _DEPENDENCY_FILE_SCOPED_MODES
    )


def _build_dependency_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    mode = _normalize_dependency_mode(getattr(args, "dependencies", None))
    tool_args = {
        "mode": mode,
        "output_format": output_format,
    }
    if mode in _DEPENDENCY_FILE_SCOPED_MODES:
        tool_args["file_path"] = args.file_path
    return tool_args


def _build_detect_routes_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --detect-routes, omitting empty optional keys."""
    tool_args: dict[str, Any] = {
        "mode": getattr(args, "detect_routes_mode", "summary") or "summary",
        "framework": getattr(args, "detect_routes_framework", "all") or "all",
        "output_format": output_format,
    }
    url_pattern = getattr(args, "detect_routes_url", None)
    if url_pattern:
        tool_args["url_pattern"] = url_pattern
    file_path = getattr(args, "detect_routes_file", None)
    if file_path:
        tool_args["file_path"] = file_path
    return tool_args


def _build_parser_readiness_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for parser-readiness CLI alias and flag modes."""
    return {
        "language": getattr(args, "parser_readiness_language", None)
        or getattr(args, "file_path", None),
        "include_supported": bool(
            getattr(args, "parser_readiness_include_supported", False)
        ),
        "output_format": output_format,
    }


# ---- builders ported from feat/consolidated during merge ----


def _build_trace_impact_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --trace-impact, omitting empty optional keys.

    The TraceImpactTool schema does not accept ``output_format``, so the
    dispatcher must not forward it here — callers receive JSON envelopes
    by default and can post-process to TOON via the ``toon_content`` field
    if the tool produces one.
    """
    tool_args: dict[str, Any] = {
        "symbol": getattr(args, "trace_impact_symbol", "") or "",
    }
    file_path = getattr(args, "trace_impact_file", None) or getattr(
        args, "file_path", None
    )
    if file_path:
        tool_args["file_path"] = file_path
    roots = getattr(args, "trace_impact_roots", None)
    if roots:
        tool_args["project_root"] = roots
    return tool_args


def _build_batch_search_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --batch-search (T2 round-37d parity fix).

    BatchSearchTool's schema is ``{queries: array<{pattern, roots?, ...}>}``.
    The CLI accepts a JSON file with the queries array (a single CLI flag
    cannot encode a list of dicts cleanly). Validation, schema strictness,
    and the 2-10 queries cap are enforced by the tool itself.

    ``output_format`` is not on the schema (additionalProperties: false),
    so we don't forward it — the CLI's format handler emits the response
    in the requested format after the tool returns.
    """
    del output_format  # BatchSearchTool currently ignores output_format
    queries_path = getattr(args, "batch_search_queries_json", None)
    if not queries_path:
        raise ValueError(
            "--batch-search requires --batch-search-queries-json PATH "
            "pointing to a JSON array of query objects"
        )
    import json
    from pathlib import Path

    try:
        text = Path(queries_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"Cannot read batch_search queries file '{queries_path}': {exc}"
        ) from exc
    try:
        queries = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"--batch-search-queries-json '{queries_path}' is not valid JSON: {exc}"
        ) from exc
    if not isinstance(queries, list):
        raise ValueError(
            f"--batch-search-queries-json '{queries_path}' must contain a JSON array"
        )
    return {"queries": queries}


def _build_modification_guard_tool_args(
    args: Any, output_format: str
) -> dict[str, Any]:
    """Build tool args for --modification-guard (T1 round-37c parity fix).

    Schema requires ``symbol`` + ``modification_type``; ``file_path`` is
    optional. ModificationGuardTool's schema does not accept
    ``output_format`` (same as trace_impact / check_tools /
    build_project_index — see R4), so we don't forward it. The CLI's
    own format handler still emits the response in the requested format
    after the tool returns.
    """
    del output_format  # ModificationGuardTool currently ignores output_format
    symbol = getattr(args, "modification_guard_symbol", None) or ""
    mod_type = getattr(args, "modification_guard_type", None) or ""
    tool_args: dict[str, Any] = {
        "symbol": symbol,
        "modification_type": mod_type,
    }
    file_path = getattr(args, "modification_guard_file", None) or getattr(
        args, "file_path", None
    )
    if file_path:
        tool_args["file_path"] = file_path
    return tool_args


def _build_decision_journal_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --decision-journal (r37fG CLI-MCP parity).

    Mirrors DecisionJournalTool's four-mode schema. Only forwards the
    fields the chosen mode actually needs so the contract test matrix
    can drive the tool with the minimum viable argument shape.
    """
    mode = getattr(args, "decision_journal_mode", "search") or "search"
    tool_args: dict[str, Any] = {"mode": mode, "output_format": output_format}
    if mode == "record":
        if (title := getattr(args, "decision_journal_title", None)) is not None:
            tool_args["title"] = title
        if (rationale := getattr(args, "decision_journal_rationale", None)) is not None:
            tool_args["rationale"] = rationale
        if (verdict := getattr(args, "decision_journal_verdict", None)) is not None:
            tool_args["verdict"] = verdict
        if (tags := getattr(args, "decision_journal_tags", None)) is not None:
            tool_args["tags"] = tags
    elif mode == "get":
        if (rec_id := getattr(args, "decision_journal_id", None)) is not None:
            tool_args["id"] = rec_id
    elif mode == "search":
        if (query := getattr(args, "decision_journal_query", None)) is not None:
            tool_args["query"] = query
        if (vf := getattr(args, "decision_journal_verdict_filter", None)) is not None:
            tool_args["verdict_filter"] = vf
        tool_args["limit"] = int(getattr(args, "decision_journal_limit", 20) or 20)
    elif mode == "supersede":
        if (rec_id := getattr(args, "decision_journal_id", None)) is not None:
            tool_args["id"] = rec_id
        if (new_id := getattr(args, "decision_journal_new_id", None)) is not None:
            tool_args["new_id"] = new_id
    return tool_args


def _build_check_tools_tool_args(args: Any, output_format: str) -> dict[str, Any]:
    """Build tool args for --check-tools.

    The CheckToolsTool schema accepts no input properties (only checks
    whether fd/rg are available), so we forward an empty dict.
    """
    del args, output_format  # CheckToolsTool takes no inputs
    return {}


def _build_build_project_index_tool_args(
    args: Any, output_format: str
) -> dict[str, Any]:
    """Build tool args for --build-project-index.

    Mirrors :class:`BuildProjectIndexTool`'s schema — ``roots`` (list of
    directories) and ``add_notes`` (string). ``output_format`` is not on
    the schema so we omit it.
    """
    del output_format  # BuildProjectIndexTool currently ignores output_format
    tool_args: dict[str, Any] = {}
    roots = getattr(args, "build_project_index_roots", None)
    if roots:
        tool_args["roots"] = roots
    notes = getattr(args, "build_project_index_notes", None)
    if notes:
        tool_args["add_notes"] = notes
    return tool_args


MCP_COMMAND_SPECS: tuple[McpCommandSpec, ...] = (
    McpCommandSpec(
        flag_name="file_health",
        tool_attr="FileHealthTool",
        label="File health check",
        required_file_error="--file-health requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="project_health",
        tool_attr="ProjectHealthTool",
        label="Project health check",
        build_tool_args=lambda args, output_format: {
            "min_grade": getattr(args, "min_grade", "D"),
            "max_files": getattr(args, "max_files", 30),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="overview",
        tool_attr="ProjectOverviewTool",
        label="Project overview",
        build_tool_args=lambda args, output_format: {
            "include_health": True,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="safe_to_edit",
        tool_attr="SafeToEditTool",
        label="Safe to edit",
        required_file_error="--safe-to-edit requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "edit_type": getattr(args, "edit_type", "refactor") or "refactor",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="change_impact",
        tool_attr="ChangeImpactTool",
        label="Change impact analysis",
        # agent_summary_only flipped to default-True in v1.12 (was 145 KB
        # of JSON, agents had to add --agent-summary-only every time).
        # ``--change-impact-full`` is the explicit opt-out; the older
        # ``--agent-summary-only`` is still accepted but is now redundant.
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "change_impact_mode", "diff") or "diff",
            "pr_url": getattr(args, "pr_url", "") or "",
            "include_tests": bool(getattr(args, "change_impact_include_tests", True)),
            "output_format": output_format,
            "scope_paths": getattr(args, "change_impact_scope", None) or [],
            "agent_summary_only": not bool(getattr(args, "change_impact_full", False)),
        },
    ),
    McpCommandSpec(
        flag_name="parser_readiness",
        tool_attr="ParserReadinessTool",
        label="Parser readiness advisor",
        build_tool_args=_build_parser_readiness_tool_args,
    ),
    McpCommandSpec(
        flag_name="dependencies",
        tool_attr="DependencyAnalysisTool",
        label="Dependency analysis",
        required_file_error=(
            "--dependencies requires a file path for file_deps and blast_radius modes"
        ),
        requires_file=_dependency_mode_requires_file,
        build_tool_args=_build_dependency_tool_args,
    ),
    McpCommandSpec(
        flag_name="refactor",
        tool_attr="RefactoringSuggestionsTool",
        label="Refactoring suggestions",
        required_file_error="--refactor requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="outline",
        tool_attr="GetCodeOutlineTool",
        label="Code outline",
        required_file_error="--outline requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "include_fields": getattr(args, "outline_include_fields", False),
            "include_imports": getattr(args, "outline_include_imports", False),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="smart_context",
        tool_attr="SmartContextTool",
        label="Smart context",
        required_file_error="--smart-context requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="symbol_lineage",
        tool_attr="SymbolLineageTool",
        label="Symbol lineage and impact preview",
        build_tool_args=lambda args, output_format: {
            "symbol": getattr(args, "symbol_lineage", "") or "",
            "max_depth": getattr(args, "max_depth", 3),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="code_patterns",
        tool_attr="CodePatternsTool",
        label="Code pattern and anti-pattern detection",
        required_file_error="--code-patterns requires a file path",
        build_tool_args=lambda args, output_format: {
            "file_path": args.file_path,
            "categories": getattr(args, "code_patterns_categories", None) or ["all"],
            "severity_threshold": getattr(args, "severity_threshold", "info") or "info",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="call_graph",
        tool_attr="CodeGraphCallTool",
        label="Function-level call graph (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "call_graph_mode", "summary") or "summary",
            "function_name": getattr(args, "call_graph_function", None),
            "file_path": getattr(args, "call_graph_file", None),
            "depth": getattr(args, "call_graph_depth", 5),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="callers",
        tool_attr="CodeGraphCallersTool",
        label="Find callers of a function (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "function_name": getattr(args, "callers", ""),
            "file_path": getattr(args, "callers_file", None),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="callees",
        tool_attr="CodeGraphCalleesTool",
        label="Find callees of a function (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "function_name": getattr(args, "callees", ""),
            "file_path": getattr(args, "callees_file", None),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="ast_cache",
        tool_attr="ASTCacheTool",
        label="Pre-indexed AST cache (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "ast_cache_mode", "stats") or "stats",
            "file_path": getattr(args, "file_path", None),
            "query": getattr(args, "ast_cache_query", None),
            "language": getattr(args, "ast_cache_language", None),
            "max_files": getattr(args, "ast_cache_max_files", 20_000),
            "force": bool(getattr(args, "ast_cache_force", False)),
            "include_activation": bool(
                getattr(args, "ast_cache_include_activation", False)
            ),
            "poll_interval": getattr(args, "watch_poll_interval", 5.0),
            "backend": getattr(args, "watch_backend", "poll"),
        },
    ),
    McpCommandSpec(
        flag_name="detect_routes",
        tool_attr="RouteDetectorTool",
        label="Framework route detection (CodeGraph parity)",
        build_tool_args=_build_detect_routes_tool_args,
    ),
    McpCommandSpec(
        flag_name="ast_diff",
        tool_attr="ASTDiffTool",
        label="Structural AST diff (difftastic-level)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "ast_diff_mode", "diff_files") or "diff_files",
            "old_file": getattr(args, "ast_diff_old_file", None),
            "new_file": getattr(args, "ast_diff_new_file", None),
            "old_source": getattr(args, "ast_diff_old_source", None),
            "new_source": getattr(args, "ast_diff_new_source", None),
            "file_path": getattr(args, "ast_diff_file", None),
            "old_ref": getattr(args, "ast_diff_old_ref", "HEAD~1"),
            "new_ref": getattr(args, "ast_diff_new_ref", "HEAD"),
            "language": getattr(args, "ast_diff_language", None),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="symbol_search",
        tool_attr="CodeGraphSymbolSearchTool",
        label="FTS5-powered instant symbol search (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            # Pain #21 (dogfood pass 3): same dest-name bug as #17. --symbol-search QUERY
            # stores into args.symbol_search; reading symbol_search_query was always None
            # so the tool always raised "query is required".
            "query": getattr(args, "symbol_search", "") or "",
            "language": getattr(args, "symbol_search_language", None),
            "kind": getattr(args, "symbol_search_kind", "any") or "any",
            "limit": getattr(args, "symbol_search_limit", 50),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="call_path",
        tool_attr="CodeGraphCallPathTool",
        label="Find execution paths between two functions (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "source_function": getattr(args, "call_path_source", "") or "",
            "target_function": getattr(args, "call_path_target", "") or "",
            "source_file": getattr(args, "call_path_source_file", None),
            "target_file": getattr(args, "call_path_target_file", None),
            "max_depth": getattr(args, "call_path_max_depth", 10),
            "max_paths": getattr(args, "call_path_max_paths", 5),
            "direction": getattr(args, "call_path", "bidirectional") or "bidirectional",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_overview",
        tool_attr="CodeGraphOverviewTool",
        label="Project-wide call graph intelligence (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "max_entry_points": getattr(
                args, "codegraph_overview_max_entry_points", 30
            ),
            "max_hubs": getattr(args, "codegraph_overview_max_hubs", 20),
            "max_dead": getattr(args, "codegraph_overview_max_dead", 20),
            "max_coupled_files": getattr(args, "codegraph_overview_max_coupled", 15),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="symbol_resolve",
        tool_attr="CodeGraphSymbolResolveTool",
        label="Go-to-definition and find-all-references (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "symbol": getattr(args, "symbol_resolve", ""),
            "mode": getattr(args, "symbol_resolve_mode", "resolve") or "resolve",
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_impact",
        tool_attr="CodeGraphImpactTool",
        label="Function blast radius analysis (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_impact_mode", "function_impact")
            or "function_impact",
            # Pain #17 (dogfood pass 3): --codegraph-impact FUNCTION argparse
            # dest is ``codegraph_impact``, not ``codegraph_impact_function``.
            # Reading the wrong attr meant function_name was always None and
            # the tool always raised at CLI invocation.
            "function_name": getattr(args, "codegraph_impact", None),
            "function_names": getattr(args, "codegraph_impact_functions", None),
            "file_path": getattr(args, "codegraph_impact_file", None),
            "depth": getattr(args, "codegraph_impact_depth", 5),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_navigate",
        tool_attr="CodeGraphNavigateTool",
        label="Unified symbol navigation: go-to-def + references + call hierarchy",
        build_tool_args=lambda args, output_format: {
            "symbol": getattr(args, "codegraph_navigate", ""),
            "mode": getattr(args, "codegraph_navigate_mode", "full") or "full",
            "file_path": getattr(args, "codegraph_navigate_file", None),
            "depth": getattr(args, "codegraph_navigate_depth", 2),
            "output_format": output_format,
        },
    ),
    # CodeGraph parity gap-closure (2026-05-24): codegraph_status is a thin
    # facade returning index health in one call (was: 3-4 separate calls to
    # ast_cache + auto_index + check_tools). Bare boolean flag.
    McpCommandSpec(
        flag_name="codegraph_status",
        tool_attr="CodeGraphStatusTool",
        label="Index health at-a-glance (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "include_lag": not bool(getattr(args, "codegraph_status_no_lag", False)),
            "output_format": output_format,
        },
    ),
    # CodeGraph parity gap-closure (2026-05-24): codegraph_explore replaces
    # ~8 chained codegraph_node / analyze_code_structure calls with one
    # capped batch fetch. Value-bearing flag: --codegraph-explore "QUERY".
    McpCommandSpec(
        flag_name="codegraph_explore",
        tool_attr="CodeGraphExploreTool",
        label="Bulk-fetch N related symbols' source + relationship map",
        build_tool_args=lambda args, output_format: {
            "query": getattr(args, "codegraph_explore", "") or "",
            "maxFiles": getattr(args, "codegraph_explore_max_files", 12),
            "maxSymbols": getattr(args, "codegraph_explore_max_symbols", 20),
            "includeCode": not bool(
                getattr(args, "codegraph_explore_outline_only", False)
            ),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="ast_path",
        tool_attr="CodeGraphASTPathTool",
        label="AST path/scope navigation (CodeGraph parity)",
        required_file_error="--ast-path requires a file path",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "ast_path_mode", "scope") or "scope",
            "file_path": args.file_path,
            "line": getattr(args, "ast_path_line", None),
            "max_depth": getattr(args, "ast_path_max_depth", 3),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="semantic_classify",
        tool_attr="SemanticClassifyTool",
        label="Semantic change classification",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "semantic_classify_mode", "classify_file")
            or "classify_file",
            "file_path": getattr(args, "file_path", None),
            "old_ref": getattr(args, "semantic_classify_old_ref", "HEAD~1"),
            "new_ref": getattr(args, "semantic_classify_new_ref", "HEAD"),
            "language": getattr(args, "semantic_classify_language", None),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="pr_review",
        tool_attr="CodeGraphPRReviewTool",
        label="AI-powered PR review: AST diff + semantic + call graph",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "pr_review", "diff") or "diff",
            "pr_url": getattr(args, "pr_review_url", "") or "",
            "include_call_graph": True,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="import_graph",
        tool_attr="CodeGraphImportGraphTool",
        label="File-level import dependency graph (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "import_graph_mode", "summary") or "summary",
            "file_path": getattr(args, "import_graph_file", None)
            or getattr(args, "file_path", None),
            "max_depth": getattr(args, "import_graph_max_depth", 10),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="dead_code",
        tool_attr="CodeGraphDeadCodeTool",
        label="Dead code analysis: transitive dead functions, unused imports, unreferenced variables",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "dead_code_mode", "all") or "all",
            "include_test_files": bool(getattr(args, "dead_code_include_tests", False)),
            "max_dead": getattr(args, "dead_code_max", 50) or 50,
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="code_similarity",
        tool_attr="CodeGraphSimilarityTool",
        label="AST-structural clone detection: finds duplicate and near-duplicate functions (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "code_similarity_mode", "all") or "all",
            "min_lines": getattr(args, "code_similarity_min_lines", 5) or 5,
            "min_group_size": getattr(args, "code_similarity_min_group", 2) or 2,
            "max_groups": getattr(args, "code_similarity_max_groups", 20) or 20,
            "use_cache": not bool(getattr(args, "code_similarity_no_cache", False)),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_sitemap",
        tool_attr="CodeGraphSitemapTool",
        label="Hierarchical project code map: directory→file→class→function (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_sitemap_mode", "full") or "full",
            "language": getattr(args, "codegraph_sitemap_language", None),
            "directory": getattr(args, "codegraph_sitemap_directory", None),
            "max_files": getattr(args, "codegraph_sitemap_max_files", 200),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_xref",
        tool_attr="CodeGraphXRefTool",
        label="Instant cross-reference: definition + callers + callees + import deps (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_xref_mode", "symbol") or "symbol",
            "symbol": getattr(args, "codegraph_xref", ""),
            "file_path": getattr(args, "codegraph_xref_file", None),
            "include_callers": bool(getattr(args, "codegraph_xref_callers", True)),
            "include_callees": bool(getattr(args, "codegraph_xref_callees", True)),
            "include_imports": bool(getattr(args, "codegraph_xref_imports", True)),
            "include_file_deps": bool(getattr(args, "codegraph_xref_file_deps", True)),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_complexity_heatmap",
        tool_attr="CodeGraphComplexityHeatmapTool",
        label="Cyclomatic complexity heatmap with risk bands (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_complexity_heatmap", "project")
            or "project",
            "file_path": getattr(args, "codegraph_complexity_file", None),
            "function_name": getattr(args, "codegraph_complexity_function", None),
            "language": getattr(args, "codegraph_complexity_language", None),
            "directory": getattr(args, "codegraph_complexity_directory", None),
            "max_files": getattr(args, "codegraph_complexity_max_files", 200),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="class_hierarchy",
        tool_attr="ClassHierarchyTool",
        label="Class inheritance hierarchy analysis: subclasses, superclasses, impact (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "class_hierarchy_mode", "summary") or "summary",
            "class_name": getattr(args, "class_hierarchy_class", None),
            "max_depth": getattr(args, "class_hierarchy_depth", 10),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="dependency_matrix",
        tool_attr="CodeGraphDependencyMatrixTool",
        label="Module coupling analysis: pairwise scores, hotspots, unstable modules (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "dependency_matrix_mode", "summary") or "summary",
            "file_path": getattr(args, "dependency_matrix_file", None),
            "top_k": getattr(args, "dependency_matrix_top_k", 10),
            "threshold": getattr(args, "dependency_matrix_threshold", 0.7),
            "output_format": output_format,
        },
    ),
    McpCommandSpec(
        flag_name="codegraph_visualize",
        tool_attr="CodeGraphVisualizeTool",
        label="Mermaid call graph visualization (CodeGraph parity)",
        build_tool_args=lambda args, output_format: {
            "mode": getattr(args, "codegraph_visualize_mode", "full") or "full",
            "file_path": getattr(args, "codegraph_visualize_file", None),
            "function": getattr(args, "codegraph_visualize_function", None),
            "depth": getattr(args, "codegraph_visualize_depth", 3),
            "max_edges": getattr(args, "codegraph_visualize_max_edges", 150),
            "direction": getattr(args, "codegraph_visualize_direction", "TD") or "TD",
            "output_format": output_format,
        },
    ),
    # consolidated-only dispatchers ported during merge of feat/autonomous-dev
    McpCommandSpec(
        flag_name="trace_impact",
        tool_attr="TraceImpactTool",
        label="Trace symbol impact (callers + usages across project)",
        build_tool_args=_build_trace_impact_tool_args,
    ),
    McpCommandSpec(
        flag_name="check_tools",
        tool_attr="CheckToolsTool",
        label="Check whether fd and ripgrep are installed",
        build_tool_args=_build_check_tools_tool_args,
    ),
    McpCommandSpec(
        flag_name="build_project_index",
        tool_attr="BuildProjectIndexTool",
        label="Rebuild persistent project index",
        build_tool_args=_build_build_project_index_tool_args,
    ),
    McpCommandSpec(
        flag_name="modification_guard",
        tool_attr="ModificationGuardTool",
        label="Pre-modification safety guard for a symbol",
        build_tool_args=_build_modification_guard_tool_args,
    ),
    McpCommandSpec(
        flag_name="decision_journal",
        tool_attr="DecisionJournalTool",
        label="Decision journal (record/get/search/supersede)",
        build_tool_args=_build_decision_journal_tool_args,
    ),
    McpCommandSpec(
        flag_name="batch_search",
        tool_attr="BatchSearchTool",
        label="Batch ripgrep search (2-10 queries via JSON file)",
        build_tool_args=_build_batch_search_tool_args,
    ),
)


def _classify_error_type(exc: BaseException) -> str:
    """Classify an exception into the canonical error_type vocabulary.

    The CLI envelope contract distinguishes ``validation`` (caller
    misuse — bad args) from ``runtime`` (anything else). The mapping is
    deliberately coarse so machine-parsing the envelope stays simple.
    """
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return "validation"
    return "runtime"


def _build_error_envelope(
    flag_name: str,
    label: str,
    exc: BaseException,
    echo_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical error envelope for MCP-bridged CLI commands.

    r37ah (re-added during PL-D long-tail cleanup): error responses
    must mirror ``agent_summary.verdict`` upward to the top level so
    the CLI envelope gate (``test_cli_envelope_contract``) accepts
    them. Without this, callers see ``verdict=None`` while
    ``agent_summary.verdict='ERROR'`` — the very drift the gate exists
    to catch.

    Shape (locked by ``test_mcp_command_error_envelope_has_top_verdict``):
        - ``success`` ``False``
        - ``error_type`` per ``_classify_error_type``
        - ``error`` — the human-readable message
        - ``summary_line`` — one-line headline
        - ``verdict`` ``"ERROR"`` (canonical vocabulary)
        - ``agent_summary.verdict`` ``"ERROR"`` (mirrored)
    """
    message = str(exc) or type(exc).__name__
    summary_line = f"{flag_name}: error — {message}"
    envelope: dict[str, Any] = {
        "success": False,
        "error_type": _classify_error_type(exc),
        "error": message,
        "summary_line": summary_line,
        # r37ah contract: top-level verdict mirror so the CLI envelope
        # gate accepts MCP-bridged error responses.
        "verdict": "ERROR",
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": summary_line,
            "next_step": "Fix the input and retry.",
            "label": label,
        },
    }
    if echo_fields:
        for key, value in echo_fields.items():
            envelope.setdefault(key, value)
    return envelope


def _run_tool(
    args: Any,
    tool_cls: Callable[..., Any],
    tool_args: Mapping[str, Any],
    label: str,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
) -> int:
    """Helper: instantiate tool, run execute(), print output."""
    try:
        project_root = getattr(args, "project_root", None) or os.getcwd()
        tool = tool_cls(project_root=project_root)
        result: dict[str, Any] = asyncio.run(tool.execute(dict(tool_args)))
        fmt = output_format_fn()
        if fmt == "toon":
            print(result.get("toon_content", ""))
        else:
            output_json_fn(result)
        return 0 if result.get("success", False) else 1
    except Exception as e:
        output_error_fn(f"{label} failed: {e}")
        return 1


# ARCH-A2: declare which tool-class names this module exposes for the
# CLI. The set is used by the contract test to verify every
# MCP_COMMAND_SPECS entry resolves. Lookup itself goes through the
# module namespace (``globals()``) so monkeypatching at module level —
# the standard pattern used by tests in tests/unit/cli/test_mcp_commands.py
# — keeps working. A snapshot dict would freeze references at import
# time and quietly break those tests.
_TOOL_CLASS_NAMES: frozenset[str] = frozenset(
    {
        "FileHealthTool",
        "GetCodeOutlineTool",
        "ParserReadinessTool",
        "ProjectHealthTool",
        "ProjectOverviewTool",
        "SafeToEditTool",
        "ChangeImpactTool",
        "DependencyAnalysisTool",
        "RefactoringSuggestionsTool",
        "SmartContextTool",
        "SymbolLineageTool",
        "CodePatternsTool",
        "CodeGraphCallTool",
        "CodeGraphCallersTool",
        "CodeGraphCalleesTool",
        "CodeGraphCallPathTool",
        "CodeGraphOverviewTool",
        "ASTCacheTool",
        "ASTDiffTool",
        "RouteDetectorTool",
        "CodeGraphSymbolSearchTool",
        "CodeGraphSymbolResolveTool",
        "CodeGraphImpactTool",
        "CodeGraphASTPathTool",
        "SemanticClassifyTool",
        "CodeGraphPRReviewTool",
        "CodeGraphNavigateTool",
        "CodeGraphStatusTool",
        "CodeGraphExploreTool",
        "CodeGraphImportGraphTool",
        # Pain pass 4: dead_code spec was added but the class wasn't in
        # this allowlist, so the contract test caught a registry/spec drift.
        "CodeGraphDeadCodeTool",
        "CodeGraphSimilarityTool",
        "CodeGraphSitemapTool",
        "CodeGraphXRefTool",
        "CodeGraphComplexityHeatmapTool",
        "ClassHierarchyTool",
        "CodeGraphDependencyMatrixTool",
        "CodeGraphVisualizeTool",
        "ConstraintCheckTool",
        # consolidated-only tools ported during merge of feat/autonomous-dev
        "TraceImpactTool",
        "CheckToolsTool",
        "BuildProjectIndexTool",
        "ModificationGuardTool",
        "DecisionJournalTool",
        "BatchSearchTool",
    }
)


def _get_tool_class(tool_attr: str) -> Callable[..., Any]:
    """Resolve a tool class by its command spec attribute name.

    Looks the class up in the module's own namespace (``globals()``) so
    tests that monkeypatch ``mcp_commands.FileHealthTool`` etc. see the
    substituted class — a frozen dict would defeat that pattern.
    """
    if tool_attr not in _TOOL_CLASS_NAMES:
        raise KeyError(f"Unknown MCP tool: {tool_attr}")
    cls = globals().get(tool_attr)
    if cls is None:
        raise KeyError(
            f"Tool name {tool_attr!r} is declared in _TOOL_CLASS_NAMES but "
            "is not bound in this module."
        )
    return cls  # type: ignore[no-any-return]


def handle_mcp_commands(
    args: Any,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
) -> int | None:
    """Handle MCP-equivalent CLI commands. Returns exit code or None if not handled."""
    spec = find_selected_mcp_command(args, MCP_COMMAND_SPECS)
    if spec is None:
        return None

    if not validate_mcp_command_args(args, spec, output_error_fn):
        return 1

    output_format = output_format_fn()
    return _run_tool(
        args,
        _get_tool_class(spec.tool_attr),
        build_mcp_tool_args(args, spec, output_format),
        spec.label,
        output_json_fn,
        output_error_fn,
        output_format_fn,
    )
