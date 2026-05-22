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
    from .tools.call_graph_tool import CodeGraphCallTool
    from .tools.callees_tool import CodeGraphCalleesTool
    from .tools.callers_tool import CodeGraphCallersTool
    from .tools.change_impact_tool import ChangeImpactTool
    from .tools.code_patterns_tool import CodePatternsTool
    from .tools.dependency_analysis_tool import DependencyAnalysisTool
    from .tools.file_health_tool import FileHealthTool
    from .tools.find_and_grep_tool import FindAndGrepTool
    from .tools.list_files_tool import ListFilesTool
    from .tools.parser_readiness_tool import ParserReadinessTool
    from .tools.project_health_tool import ProjectHealthTool
    from .tools.project_overview_tool import ProjectOverviewTool
    from .tools.query_tool import QueryTool
    from .tools.read_partial_tool import ReadPartialTool
    from .tools.refactoring_suggestions_tool import RefactoringSuggestionsTool
    from .tools.route_detector_tool import RouteDetectorTool
    from .tools.safe_to_edit_tool import SafeToEditTool
    from .tools.search_content_tool import SearchContentTool
    from .tools.smart_context_tool import SmartContextTool
    from .tools.symbol_lineage_tool import SymbolLineageTool
    from .tools.symbol_resolve_tool import CodeGraphSymbolResolveTool
    from .tools.symbol_search_tool import CodeGraphSymbolSearchTool

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
        ("codegraph_ast_path", CodeGraphASTPathTool(project_root)),
        ("codegraph_symbol_search", CodeGraphSymbolSearchTool(project_root)),
        ("codegraph_resolve", CodeGraphSymbolResolveTool(project_root)),
        ("analyze_change_impact", ChangeImpactTool(project_root)),
        ("refactoring_suggestions", RefactoringSuggestionsTool(project_root)),
        ("safe_to_edit", SafeToEditTool(project_root)),
        ("smart_context", SmartContextTool(project_root)),
        ("symbol_lineage", SymbolLineageTool(project_root)),
        ("code_patterns", CodePatternsTool(project_root)),
        ("detect_routes", RouteDetectorTool(project_root)),
    ]
    return tool_instances, dict(tool_instances)
