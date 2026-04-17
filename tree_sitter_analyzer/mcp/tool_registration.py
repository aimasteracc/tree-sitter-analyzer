#!/usr/bin/env python3
"""
MCP Tool Registration Module

This module handles the registration of all MCP tools with the ToolRegistry.
Each tool is registered with metadata including toolset, category, emoji, and description.
"""

from collections.abc import Callable
from typing import Any

from .registry import TOOLSET_DEFINITIONS, get_registry
from .tools.analyze_code_structure_tool import AnalyzeCodeStructureTool
from .tools.analyze_scale_tool import AnalyzeScaleTool
from .tools.batch_search_tool import BatchSearchTool
from .tools.build_project_index_tool import BuildProjectIndexTool
from .tools.check_tools_tool import CheckToolsTool
from .tools.ci_report_tool import CIReportTool
from .tools.code_clone_detection_tool import CodeCloneDetectionTool
from .tools.code_diff_tool import CodeDiffTool
from .tools.code_smell_detector_tool import CodeSmellDetectorTool
from .tools.complexity_heatmap_tool import ComplexityHeatmapTool
from .tools.dependency_query_tool import DependencyQueryTool
from .tools.error_recovery_tool import ErrorRecoveryTool
from .tools.find_and_grep_tool import FindAndGrepTool
from .tools.get_code_outline_tool import GetCodeOutlineTool
from .tools.get_project_summary_tool import GetProjectSummaryTool
from .tools.health_score_tool import HealthScoreTool
from .tools.java_patterns_tool import JavaPatternAnalysisTool
from .tools.list_files_tool import ListFilesTool
from .tools.modification_guard_tool import ModificationGuardTool
from .tools.query_tool import QueryTool
from .tools.read_partial_tool import ReadPartialTool
from .tools.search_content_tool import SearchContentTool
from .tools.security_scan_tool import SecurityScanTool
from .tools.semantic_impact_tool import (
    QuickRiskAssessmentTool,
    SemanticImpactTool,
)
from .tools.test_coverage_tool import TestCoverageTool
from .tools.trace_impact_tool import TraceImpactTool
from .tools.understand_codebase_tool import UnderstandCodebaseTool

# Optional tools
try:
    from .tools.universal_analyze_tool import UniversalAnalyzeTool

    UNIVERSAL_TOOL_AVAILABLE = True
except ImportError:
    UNIVERSAL_TOOL_AVAILABLE = False
    UniversalAnalyzeTool = None  # type: ignore


def _make_handler(
    tool: Any, method_name: str = "execute"
) -> Callable[..., Any]:
    """
    Create a handler function that calls the tool's method.

    Args:
        tool: The tool instance
        method_name: Name of the method to call

    Returns:
        Async handler function
    """

    async def handler(**kwargs: Any) -> Any:
        tool_instance = tool
        method = getattr(tool_instance, method_name)
        if hasattr(method, "__self__"):
            # It's a bound method, call it directly
            return await method(kwargs)
        else:
            # It's an unbound method, pass self
            return await method(tool_instance, kwargs)

    return handler


def register_all_tools(project_root: str | None = None) -> None:
    """
    Register all MCP tools with the ToolRegistry.

    Args:
        project_root: Optional project root directory for tool initialization
    """
    registry = get_registry()

    # Analysis tools
    _register_analysis_tools(registry, project_root)

    # Query tools
    _register_query_tools(registry, project_root)

    # Navigation tools
    _register_navigation_tools(registry, project_root)

    # Safety tools
    _register_safety_tools(registry, project_root)

    # Diagnostic tools
    _register_diagnostic_tools(registry, project_root)

    # Index tools
    _register_index_tools(registry, project_root)


def _register_analysis_tools(registry: Any, project_root: str | None) -> None:
    """Register analysis tools."""
    # dependency_query
    dep_tool = DependencyQueryTool(project_root)
    registry.register(
        name="dependency_query",
        toolset="analysis",
        category="dependency-graph",
        schema=dep_tool.get_tool_definition(),
        handler=_make_handler(dep_tool),
        description="Query dependency graph: dependents, blast radius, health scores",
        emoji="🕸️",
    )

    # trace_impact
    trace_tool = TraceImpactTool(project_root)
    registry.register(
        name="trace_impact",
        toolset="analysis",
        category="impact-analysis",
        schema=trace_tool.get_tool_definition(),
        handler=_make_handler(trace_tool),
        description="Trace symbol impact across files: usage locations, blast radius",
        emoji="💥",
    )

    # analyze_scale (check_code_scale)
    scale_tool = AnalyzeScaleTool(project_root)
    registry.register(
        name="analyze_scale",
        toolset="analysis",
        category="code-metrics",
        schema=scale_tool.get_tool_definition(),
        handler=_make_handler(scale_tool),
        description="Analyze code scale: complexity, size, structure metrics",
        emoji="📊",
    )

    # analyze_code_structure
    structure_tool = AnalyzeCodeStructureTool(project_root)
    registry.register(
        name="analyze_code_structure",
        toolset="analysis",
        category="code-structure",
        schema=structure_tool.get_tool_definition(),
        handler=_make_handler(structure_tool),
        description="Analyze code structure: classes, functions, relationships",
        emoji="🏗️",
    )

    # code_diff
    diff_tool = CodeDiffTool(project_root)
    registry.register(
        name="code_diff",
        toolset="analysis",
        category="semantic-diff",
        schema=diff_tool.get_tool_definition(),
        handler=_make_handler(diff_tool),
        description="Semantic-level code diff: element changes, breaking detection",
        emoji="🔄",
    )

    # code_smell_detector
    smell_tool = CodeSmellDetectorTool(project_root)
    registry.register(
        name="code_smell_detector",
        toolset="analysis",
        category="code-quality",
        schema=smell_tool.get_tool_definition(),
        handler=_make_handler(smell_tool),
        description="Detect code smells: God Class, Long Method, Deep Nesting, Magic Numbers",
        emoji="👃",
    )

    # code_clone_detection
    clone_tool = CodeCloneDetectionTool(project_root)
    registry.register(
        name="code_clone_detection",
        toolset="analysis",
        category="duplication-detection",
        schema=clone_tool.get_tool_definition(),
        handler=_make_handler(clone_tool),
        description="Detect code clones: Type 1/2/3 clones, similarity analysis",
        emoji="👯",
    )

    # health_score
    health_tool = HealthScoreTool(project_root)
    registry.register(
        name="health_score",
        toolset="analysis",
        category="quality-assessment",
        schema=health_tool.get_tool_definition(),
        handler=_make_handler(health_tool),
        description="Analyze file health: A-F grading, complexity, maintainability",
        emoji="🏥",
    )

    # java_patterns
    java_tool = JavaPatternAnalysisTool(project_root)
    registry.register(
        name="java_patterns",
        toolset="analysis",
        category="language-specific",
        schema=java_tool.get_tool_definition(),
        handler=_make_handler(java_tool),
        description="Java patterns: Lambda, Stream API, Spring annotations",
        emoji="☕",
    )

    # error_recovery
    recovery_tool = ErrorRecoveryTool(project_root)
    registry.register(
        name="error_recovery",
        toolset="analysis",
        category="error-handling",
        schema=recovery_tool.get_tool_definition(),
        handler=_make_handler(recovery_tool),
        description="Error recovery: encoding detection, binary detection, regex fallback",
        emoji="🔧",
    )

    # semantic_impact
    semantic_tool = SemanticImpactTool(project_root)
    registry.register(
        name="semantic_impact",
        toolset="analysis",
        category="impact-analysis",
        schema=semantic_tool.get_tool_definition(),
        handler=_make_handler(semantic_tool),
        description="Semantic impact analysis: risk score, factors, suggestions",
        emoji="⚠️",
    )

    # quick_risk_assessment
    risk_tool = QuickRiskAssessmentTool(project_root)
    registry.register(
        name="quick_risk_assessment",
        toolset="analysis",
        category="impact-analysis",
        schema=risk_tool.get_tool_definition(),
        handler=_make_handler(risk_tool),
        description="Quick risk assessment: visibility, caller count, type hierarchy",
        emoji="⚡",
    )

    # understand_codebase (智能入口)
    understand_tool = UnderstandCodebaseTool(project_root)
    registry.register(
        name="understand_codebase",
        toolset="analysis",
        category="codebase-understanding",
        schema=understand_tool.get_tool_definition(),
        handler=_make_handler(understand_tool),
        description="理解代码库: 依赖、影响、健康评分（三深度级别）",
        emoji="🧠",
    )

    # complexity_heatmap
    heatmap_tool = ComplexityHeatmapTool(project_root)
    registry.register(
        name="complexity_heatmap",
        toolset="analysis",
        category="complexity-visualization",
        schema=heatmap_tool.get_tool_definition(),
        handler=_make_handler(heatmap_tool),
        description="Complexity heatmap: line-level complexity visualization",
        emoji="🔥",
    )

    # dead_code
    from .tools.dead_code_tool import DeadCodeTool
    dead_code_tool = DeadCodeTool(project_root)
    registry.register(
        name="dead_code",
        toolset="analysis",
        category="dead-code-detection",
        schema=dead_code_tool.get_tool_definition(),
        handler=_make_handler(dead_code_tool),
        description="Detect dead (unused) code: functions, classes, imports",
        emoji="🗑️",
    )

    # test_coverage
    coverage_tool = TestCoverageTool(project_root)
    registry.register(
        name="test_coverage",
        toolset="analysis",
        category="testing-coverage",
        schema=coverage_tool.get_tool_definition(),
        handler=_make_handler(coverage_tool),
        description="Test coverage analysis: identify untested code elements",
        emoji="📊",
    )


def _register_query_tools(registry: Any, project_root: str | None) -> None:
    """Register query tools."""
    # query_code
    query_tool = QueryTool(project_root)
    registry.register(
        name="query_code",
        toolset="query",
        category="symbol-query",
        schema=query_tool.get_tool_definition(),
        handler=_make_handler(query_tool),
        description="Extract code elements by syntax: functions, classes, imports",
        emoji="🔎",
    )

    # extract_code_section (read_partial)
    partial_tool = ReadPartialTool(project_root)
    registry.register(
        name="extract_code_section",
        toolset="query",
        category="code-extraction",
        schema=partial_tool.get_tool_definition(),
        handler=_make_handler(partial_tool),
        description="Extract code sections by line ranges or semantic boundaries",
        emoji="✂️",
    )

    # get_code_outline
    outline_tool = GetCodeOutlineTool(project_root)
    registry.register(
        name="get_code_outline",
        toolset="query",
        category="code-outline",
        schema=outline_tool.get_tool_definition(),
        handler=_make_handler(outline_tool),
        description="Get code outline: hierarchical structure with metadata",
        emoji="📋",
    )


def _register_navigation_tools(registry: Any, project_root: str | None) -> None:
    """Register navigation tools."""
    # list_files
    list_tool = ListFilesTool(project_root)
    registry.register(
        name="list_files",
        toolset="navigation",
        category="file-listing",
        schema=list_tool.get_tool_definition(),
        handler=_make_handler(list_tool),
        description="List files with filtering by type, pattern, size",
        emoji="📁",
    )

    # find_and_grep
    find_tool = FindAndGrepTool(project_root)
    registry.register(
        name="find_and_grep",
        toolset="navigation",
        category="file-search",
        schema=find_tool.get_tool_definition(),
        handler=_make_handler(find_tool),
        description="Find files by name and grep content with patterns",
        emoji="🔍",
    )

    # search_content
    search_tool = SearchContentTool(project_root)
    registry.register(
        name="search_content",
        toolset="navigation",
        category="content-search",
        schema=search_tool.get_tool_definition(),
        handler=_make_handler(search_tool),
        description="Search file content with regex and context",
        emoji="🔎",
    )

    # batch_search
    batch_tool = BatchSearchTool(project_root)
    registry.register(
        name="batch_search",
        toolset="navigation",
        category="batch-search",
        schema=batch_tool.get_tool_definition(),
        handler=_make_handler(batch_tool),
        description="Search multiple patterns across files in batch",
        emoji="📦",
    )


def _register_safety_tools(registry: Any, project_root: str | None) -> None:
    """Register safety tools."""
    # modification_guard
    guard_tool = ModificationGuardTool(project_root)
    registry.register(
        name="modification_guard",
        toolset="safety",
        category="pre-modification-check",
        schema=guard_tool.get_tool_definition(),
        handler=_make_handler(guard_tool),
        description="Pre-modification safety check: impact analysis, warnings",
        emoji="🛡️",
    )

    # security_scan
    security_tool = SecurityScanTool(project_root)
    registry.register(
        name="security_scan",
        toolset="safety",
        category="security-scanning",
        schema=security_tool.get_tool_definition(),
        handler=_make_handler(security_tool),
        description="Security vulnerability scanner: secrets, injection, XSS, deserialization",
        emoji="🔒",
    )


def _register_diagnostic_tools(registry: Any, project_root: str | None) -> None:
    """Register diagnostic tools."""
    # check_tools
    check_tool = CheckToolsTool(project_root)
    registry.register(
        name="check_tools",
        toolset="diagnostic",
        category="diagnostics",
        schema=check_tool.get_tool_definition(),
        handler=_make_handler(check_tool),
        description="Check tool availability and configuration",
        emoji="🩺",
    )

    # ci_report
    ci_tool = CIReportTool(project_root)
    registry.register(
        name="ci_report",
        toolset="diagnostic",
        category="ci-integration",
        schema=ci_tool.get_tool_definition(),
        handler=_make_handler(ci_tool),
        description="Generate CI/CD friendly reports with pass/fail status",
        emoji="🚦",
    )


def _register_index_tools(registry: Any, project_root: str | None) -> None:
    """Register index tools."""
    # build_project_index
    build_tool = BuildProjectIndexTool(project_root)
    registry.register(
        name="build_project_index",
        toolset="index",
        category="project-index",
        schema=build_tool.get_tool_definition(),
        handler=_make_handler(build_tool),
        description="Build persistent project index for fast queries",
        emoji="🏗️",
    )

    # get_project_summary
    summary_tool = GetProjectSummaryTool(project_root)
    registry.register(
        name="get_project_summary",
        toolset="index",
        category="project-summary",
        schema=summary_tool.get_tool_definition(),
        handler=_make_handler(summary_tool),
        description="Get project summary: stats, structure, key files",
        emoji="📚",
    )


def get_tool_info() -> dict[str, Any]:
    """
    Get information about all registered tools.

    Returns:
        Dictionary with toolsets, tools, and metadata
    """
    registry = get_registry()
    return {
        "toolsets": TOOLSET_DEFINITIONS,
        "registered_tools": registry.get_toolsets(),
    }
