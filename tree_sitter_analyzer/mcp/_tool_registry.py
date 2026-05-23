"""Tool registry factory for the MCP server.

Keeps lazy per-tool imports isolated so callers that import
tree_sitter_analyzer.mcp.server without building a server pay ~zero of the
per-tool import cost (PERF-3).
"""

from __future__ import annotations

from typing import Any


def create_tool_registry(
    project_root: str | None,
) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Instantiate and return all registered MCP tools.

    Imports are inlined (not at module top-level) so the ~316 ms cold-start
    cost is only paid when a registry is actually built.  Keep the import
    block alphabetised; the tuple order below governs public registration.
    """
    from .tools.agent_skills_tool import AgentSkillsTool
    from .tools.agent_workflow_tool import AgentWorkflowTool
    from .tools.analyze_code_structure_tool import AnalyzeCodeStructureTool
    from .tools.analyze_scale_tool import AnalyzeScaleTool
    from .tools.ast_cache_tool import ASTCacheTool
    from .tools.ast_diff_tool import ASTDiffTool
    from .tools.ast_path_tool import CodeGraphASTPathTool

    # autonomous-dev MCP-only tools (referenced in test_agent_contracts)
    from .tools.auto_index_tool import CodeGraphAutoIndexTool

    # consolidated-only tools ported during merge of feat/autonomous-dev
    from .tools.batch_search_tool import BatchSearchTool
    from .tools.build_project_index_tool import BuildProjectIndexTool
    from .tools.call_graph_tool import CodeGraphCallTool
    from .tools.call_path_tool import CodeGraphCallPathTool
    from .tools.callees_tool import CodeGraphCalleesTool
    from .tools.callers_tool import CodeGraphCallersTool
    from .tools.change_impact_tool import ChangeImpactTool
    from .tools.check_tools_tool import CheckToolsTool
    from .tools.class_hierarchy_tool import ClassHierarchyTool
    from .tools.code_patterns_tool import CodePatternsTool
    from .tools.code_similarity_tool import CodeGraphSimilarityTool
    from .tools.codegraph_impact_tool import CodeGraphImpactTool
    from .tools.codegraph_metrics_tool import CodeGraphMetricsTool
    from .tools.codegraph_navigate_tool import CodeGraphNavigateTool
    from .tools.codegraph_overview_tool import CodeGraphOverviewTool
    from .tools.codegraph_pr_review_tool import CodeGraphPRReviewTool
    from .tools.codegraph_sitemap_tool import CodeGraphSitemapTool
    from .tools.codegraph_status_tool import CodeGraphStatusTool
    from .tools.codegraph_visualize_tool import CodeGraphVisualizeTool
    from .tools.codegraph_xref_tool import CodeGraphXRefTool
    from .tools.complexity_heatmap_tool import CodeGraphComplexityHeatmapTool
    from .tools.constraint_check_tool import ConstraintCheckTool
    from .tools.dead_code_tool import CodeGraphDeadCodeTool
    from .tools.decision_journal_tool import DecisionJournalTool
    from .tools.dependency_analysis_tool import DependencyAnalysisTool
    from .tools.dependency_matrix_tool import CodeGraphDependencyMatrixTool
    from .tools.file_health_tool import FileHealthTool
    from .tools.find_and_grep_tool import FindAndGrepTool
    from .tools.full_index_tool import CodeGraphFullIndexTool
    from .tools.import_graph_tool import CodeGraphImportGraphTool
    from .tools.incremental_sync_tool import CodeGraphIncrementalSyncTool
    from .tools.list_files_tool import ListFilesTool
    from .tools.modification_guard_tool import ModificationGuardTool
    from .tools.parser_readiness_tool import ParserReadinessTool
    from .tools.project_health_tool import ProjectHealthTool
    from .tools.project_overview_tool import ProjectOverviewTool
    from .tools.query_tool import QueryTool
    from .tools.read_partial_tool import ReadPartialTool
    from .tools.refactoring_suggestions_tool import RefactoringSuggestionsTool
    from .tools.route_detector_tool import RouteDetectorTool
    from .tools.safe_to_edit_tool import SafeToEditTool
    from .tools.search_content_tool import SearchContentTool
    from .tools.semantic_classify_tool import SemanticClassifyTool
    from .tools.smart_context_tool import SmartContextTool
    from .tools.symbol_lineage_tool import SymbolLineageTool
    from .tools.symbol_resolve_tool import CodeGraphSymbolResolveTool
    from .tools.symbol_search_tool import CodeGraphSymbolSearchTool
    from .tools.trace_impact_tool import TraceImpactTool

    tool_instances: list[tuple[str, Any]] = [
        ("check_code_scale", AnalyzeScaleTool(project_root)),
        ("analyze_code_structure", AnalyzeCodeStructureTool(project_root)),
        ("extract_code_section", ReadPartialTool(project_root)),
        ("query_code", QueryTool(project_root)),
        ("list_files", ListFilesTool(project_root)),
        ("search_content", SearchContentTool(project_root)),
        ("find_and_grep", FindAndGrepTool(project_root)),
        ("list_agent_skills", AgentSkillsTool(project_root)),
        ("get_agent_workflow", AgentWorkflowTool(project_root)),
        ("advise_parser_readiness", ParserReadinessTool(project_root)),
        ("get_project_overview", ProjectOverviewTool(project_root)),
        ("check_project_health", ProjectHealthTool(project_root)),
        ("check_file_health", FileHealthTool(project_root)),
        ("analyze_dependencies", DependencyAnalysisTool(project_root)),
        ("ast_cache", ASTCacheTool(project_root)),
        ("ast_diff", ASTDiffTool(project_root)),
        ("codegraph_call_graph", CodeGraphCallTool(project_root)),
        ("codegraph_callers", CodeGraphCallersTool(project_root)),
        ("codegraph_callees", CodeGraphCalleesTool(project_root)),
        ("codegraph_call_path", CodeGraphCallPathTool(project_root)),
        ("codegraph_ast_path", CodeGraphASTPathTool(project_root)),
        ("codegraph_symbol_search", CodeGraphSymbolSearchTool(project_root)),
        ("codegraph_resolve", CodeGraphSymbolResolveTool(project_root)),
        ("codegraph_impact", CodeGraphImpactTool(project_root)),
        ("codegraph_navigate", CodeGraphNavigateTool(project_root)),
        # CodeGraph parity gap-closure (2026-05-24): codegraph_status is a
        # single-call facade over ast_cache + auto_index + check_tools so
        # agents can decide "is the index ready?" in one tool call instead
        # of triangulating three.
        ("codegraph_status", CodeGraphStatusTool(project_root)),
        # Pain pass 2: codegraph_overview was imported in server.py but
        # missing from the central registry, which broke the cli-mcp-parity
        # contract test. Re-register here so both code paths agree.
        ("codegraph_overview", CodeGraphOverviewTool(project_root)),
        ("codegraph_pr_review", CodeGraphPRReviewTool(project_root)),
        ("analyze_change_impact", ChangeImpactTool(project_root)),
        ("refactoring_suggestions", RefactoringSuggestionsTool(project_root)),
        ("safe_to_edit", SafeToEditTool(project_root)),
        ("smart_context", SmartContextTool(project_root)),
        ("symbol_lineage", SymbolLineageTool(project_root)),
        ("code_patterns", CodePatternsTool(project_root)),
        ("semantic_classify", SemanticClassifyTool(project_root)),
        ("detect_routes", RouteDetectorTool(project_root)),
        ("codegraph_dead_code", CodeGraphDeadCodeTool(project_root)),
        # Pain #26 (dogfood pass 4): import_graph_tool was imported and
        # spec'd in mcp_commands.py but missing from the central registry.
        # Same drift pattern as #12 — registry vs CLI specs need a single
        # source-of-truth; see test_registered_mcp_tools_have_cli_parity.
        ("codegraph_import_graph", CodeGraphImportGraphTool(project_root)),
        ("codegraph_similarity", CodeGraphSimilarityTool(project_root)),
        ("codegraph_sitemap", CodeGraphSitemapTool(project_root)),
        ("codegraph_xref", CodeGraphXRefTool(project_root)),
        ("codegraph_complexity_heatmap", CodeGraphComplexityHeatmapTool(project_root)),
        ("codegraph_class_hierarchy", ClassHierarchyTool(project_root)),
        ("codegraph_dependency_matrix", CodeGraphDependencyMatrixTool(project_root)),
        ("check_constraints", ConstraintCheckTool(project_root)),
        ("codegraph_visualize", CodeGraphVisualizeTool(project_root)),
        # consolidated-only tools ported during merge of feat/autonomous-dev
        ("trace_impact", TraceImpactTool(project_root)),
        ("check_tools", CheckToolsTool(project_root)),
        ("build_project_index", BuildProjectIndexTool(project_root)),
        ("modification_guard", ModificationGuardTool(project_root)),
        ("decision_journal", DecisionJournalTool(project_root)),
        ("batch_search", BatchSearchTool(project_root)),
        # PL-C scope: cache-management trio gets first-class registration
        # (and matching CLI flags) — no longer ``mcp_only`` in tool_to_cli.
        ("codegraph_autoindex", CodeGraphAutoIndexTool(project_root)),
        ("codegraph_full_index", CodeGraphFullIndexTool(project_root)),
        ("codegraph_metrics", CodeGraphMetricsTool(project_root)),
        ("codegraph_incremental_sync", CodeGraphIncrementalSyncTool(project_root)),
    ]
    return tool_instances, dict(tool_instances)
