#!/usr/bin/env python3
"""MCP-equivalent CLI command handlers.

This package is the authoritative namespace for all MCP-bridged CLI commands.
Importers should use:

    from tree_sitter_analyzer.cli.commands import mcp_commands
    from tree_sitter_analyzer.cli.commands.mcp_commands import handle_mcp_commands

Public API (unchanged from the former single-file module):
    handle_mcp_commands  — main entry point used by special_commands.py
    MCP_COMMAND_SPECS    — the full command registry
    _TOOL_CLASS_NAMES    — allowlist used by _get_tool_class / contract tests
    _build_error_envelope — envelope builder used by cli_envelope_contract tests
    _get_tool_class       — resolves a tool class by name; uses globals() so
                            monkeypatch.setattr(mcp_commands, "FooTool", ...) works
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tree_sitter_analyzer.cli.commands.mcp_command_helpers import (
    McpCommandSpec,
    build_mcp_tool_args,
    find_selected_mcp_command,
    validate_mcp_command_args,
)
from tree_sitter_analyzer.mcp.tools._call_tree_tool import (  # noqa: F401
    CodeGraphCalleeTreeTool,
    CodeGraphCallerTreeTool,
)

# ---------------------------------------------------------------------------
# Tool class imports — consumed via globals() inside _get_tool_class so that
# tests can monkeypatch the names at module level.  The # noqa codes prevent
# ruff / autoflake from stripping imports that appear unused.
# ---------------------------------------------------------------------------
from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool  # noqa: F401
from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool  # noqa: F401
from tree_sitter_analyzer.mcp.tools.ast_path_tool import (
    CodeGraphASTPathTool,  # noqa: F401
)
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
from tree_sitter_analyzer.mcp.tools.class_inspect_tool import (
    ClassInspectTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.code_patterns_tool import (
    CodePatternsTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.code_similarity_tool import (
    CodeGraphSimilarityTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.codegraph_context_tool import (
    CodeGraphContextTool,  # noqa: F401
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
from tree_sitter_analyzer.mcp.tools.codegraph_query_tool import (
    CodeGraphQueryTool,  # noqa: F401
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
from tree_sitter_analyzer.mcp.tools.doc_sync_tool import (
    DocSyncTool,  # noqa: F401
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
from tree_sitter_analyzer.mcp.tools.test_gap_tool import (
    CodeGraphTestGapTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.trace_impact_tool import (
    TraceImpactTool,  # noqa: F401
)
from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool  # noqa: F401

# ---------------------------------------------------------------------------
# Sub-module imports — builders, specs, helpers
# ---------------------------------------------------------------------------
from ._helpers import _build_error_envelope, _classify_error_type, _run_tool
from ._specs import MCP_COMMAND_SPECS

# ---------------------------------------------------------------------------
# ARCH-A2: tool class name allowlist — used by _get_tool_class and the
# contract test (test_agent_contracts.py) to verify every MCP_COMMAND_SPECS
# entry resolves.  A frozenset of strings, NOT a dict of classes, so that
# monkeypatching mcp_commands.FooTool at test time routes through globals().
# ---------------------------------------------------------------------------
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
        "CodeGraphCalleeTreeTool",
        "CodeGraphCallerTreeTool",
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
        "CodeGraphContextTool",
        "CodeGraphExploreTool",
        "CodeGraphQueryTool",
        "CodeGraphImportGraphTool",
        # Pain pass 4: dead_code spec was added but the class wasn't in
        # this allowlist, so the contract test caught a registry/spec drift.
        "CodeGraphDeadCodeTool",
        "CodeGraphSimilarityTool",
        "CodeGraphSitemapTool",
        "CodeGraphXRefTool",
        "CodeGraphComplexityHeatmapTool",
        "ClassHierarchyTool",
        "ClassInspectTool",
        "CodeGraphDependencyMatrixTool",
        "CodeGraphVisualizeTool",
        "CodeGraphUMLTool",
        "ConstraintCheckTool",
        # consolidated-only tools ported during merge of feat/autonomous-dev
        "TraceImpactTool",
        "CheckToolsTool",
        "BuildProjectIndexTool",
        "ModificationGuardTool",
        "DecisionJournalTool",
        "BatchSearchTool",
        "DocSyncTool",
        "CodeGraphTestGapTool",
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
    fail_on_verdict = getattr(args, "change_impact_fail_on_risk", None)
    return _run_tool(
        args,
        _get_tool_class(spec.tool_attr),
        build_mcp_tool_args(args, spec, output_format),
        spec.label,
        output_json_fn,
        output_error_fn,
        output_format_fn,
        fail_on_verdict_worse_than=fail_on_verdict,
    )


__all__ = [
    "McpCommandSpec",
    "MCP_COMMAND_SPECS",
    "_TOOL_CLASS_NAMES",
    "_build_error_envelope",
    "_classify_error_type",
    "_get_tool_class",
    "_run_tool",
    "handle_mcp_commands",
]
