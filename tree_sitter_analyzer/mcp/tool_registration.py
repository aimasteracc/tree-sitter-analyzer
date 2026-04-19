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
from .tools.change_impact_tool import ChangeImpactTool
from .tools.check_tools_tool import CheckToolsTool
from .tools.ci_report_tool import CIReportTool
from .tools.code_clone_detection_tool import CodeCloneDetectionTool
from .tools.code_diff_tool import CodeDiffTool
from .tools.code_smell_detector_tool import (
    CodeSmellDetectorTool,
)
from .tools.complexity_heatmap_tool import ComplexityHeatmapTool
from .tools.context_optimizer_tool import ContextOptimizerTool
from .tools.dependency_query_tool import DependencyQueryTool
from .tools.error_recovery_tool import ErrorRecoveryTool
from .tools.find_and_grep_tool import FindAndGrepTool
from .tools.get_code_outline_tool import GetCodeOutlineTool
from .tools.get_project_summary_tool import GetProjectSummaryTool
from .tools.grammar_discovery_tool import GrammarDiscoveryTool
from .tools.health_score_tool import HealthScoreTool
from .tools.java_patterns_tool import JavaPatternAnalysisTool
from .tools.list_files_tool import ListFilesTool
from .tools.modification_guard_tool import ModificationGuardTool
from .tools.overview_tool import OverviewTool
from .tools.pr_summary_tool import PRSummaryTool
from .tools.query_tool import QueryTool
from .tools.read_partial_tool import ReadPartialTool
from .tools.refactoring_suggestions_tool import RefactoringSuggestionsTool
from .tools.search_content_tool import SearchContentTool
from .tools.security_scan_tool import SecurityScanTool
from .tools.semantic_impact_tool import SemanticImpactTool
from .tools.semantic_search_tool import SemanticSearchTool
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

    # Overview tools
    _register_overview_tools(registry, project_root)

    # Optimization tools
    _register_optimization_tools(registry, project_root)


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

    # dead_code_analysis (consolidated: dead_code + dead_code_path)
    from .tools.dead_code_analysis_tool import DeadCodeAnalysisTool
    dca_tool = DeadCodeAnalysisTool(project_root)
    registry.register(
        name="dead_code_analysis",
        toolset="analysis",
        category="dead-code",
        schema=dca_tool.get_tool_definition(),
        handler=_make_handler(dca_tool),
        description="Dead code analysis: detect unused definitions and unreachable code paths across Python, JS/TS, Java, Go",
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

    # refactoring_suggestions
    refactoring_tool = RefactoringSuggestionsTool(project_root)
    registry.register(
        name="refactoring_suggestions",
        toolset="analysis",
        category="code-quality",
        schema=refactoring_tool.get_tool_definition(),
        handler=_make_handler(refactoring_tool),
        description="Refactoring suggestions: actionable guidance to fix code smells",
        emoji="🔧",
    )

    # design_patterns
    from .tools.design_patterns_tool import DesignPatternsTool
    patterns_tool = DesignPatternsTool(project_root)
    registry.register(
        name="design_patterns",
        toolset="analysis",
        category="design-pattern-detection",
        schema=patterns_tool.get_tool_definition(),
        handler=_make_handler(patterns_tool),
        description="Design patterns: Singleton, Factory, Observer, Strategy, anti-patterns",
        emoji="🏗️",
    )

    # grammar_discovery
    grammar_tool = GrammarDiscoveryTool()
    registry.register(
        name="grammar_discovery",
        toolset="analysis",
        category="grammar-introspection",
        schema=grammar_tool.get_schema(),
        handler=_make_handler(grammar_tool),
        description="Grammar auto-discovery: runtime introspection of node types, fields, wrappers",
        emoji="🔬",
    )

    # api_discovery
    from .tools.api_discovery_tool import ApiDiscoveryTool
    api_tool = ApiDiscoveryTool(project_root)
    registry.register(
        name="api_discovery",
        toolset="analysis",
        category="api-discovery",
        schema=api_tool.get_tool_definition(),
        handler=_make_handler(api_tool),
        description="API endpoints: Flask, FastAPI, Django, Express, Spring routes",
        emoji="🔌",
    )

    # env_tracker
    from .tools.env_tracker_tool import EnvTrackerTool
    env_tool = EnvTrackerTool(project_root)
    registry.register(
        name="env_tracker",
        toolset="analysis",
        category="environment-variables",
        schema=env_tool.get_tool_definition(),
        handler=_make_handler(env_tool),
        description="Environment variables: track os.getenv, process.env, System.getenv, os.Getenv usage",
        emoji="🌿",
    )

    # magic_values
    from .tools.magic_values_tool import MagicValuesTool
    magic_tool = MagicValuesTool(project_root)
    registry.register(
        name="magic_values",
        toolset="analysis",
        category="code-quality",
        schema=magic_tool.get_tool_definition(),
        handler=_make_handler(magic_tool),
        description="Magic values: detect hardcoded numbers, strings, URLs, paths, colors that should be constants",
        emoji="🔮",
    )

    # import_sanitizer
    from .tools.import_sanitizer_tool import ImportSanitizerTool
    import_tool = ImportSanitizerTool(project_root)
    registry.register(
        name="import_sanitizer",
        toolset="analysis",
        category="import-quality",
        schema=import_tool.get_tool_definition(),
        handler=_make_handler(import_tool),
        description="Import analysis: detect unused imports, circular dependencies, sort order violations",
        emoji="📦",
    )

    # doc_coverage
    from .tools.doc_coverage_tool import DocCoverageTool
    doc_tool = DocCoverageTool(project_root)
    registry.register(
        name="doc_coverage",
        toolset="analysis",
        category="documentation",
        schema=doc_tool.get_tool_definition(),
        handler=_make_handler(doc_tool),
        description="Documentation coverage: find undocumented functions, classes, methods across Python, JS/TS, Java, Go",
        emoji="📝",
    )

    # cognitive_complexity
    from .tools.cognitive_complexity_tool import CognitiveComplexityTool
    cc_tool = CognitiveComplexityTool(project_root)
    registry.register(
        name="cognitive_complexity",
        toolset="analysis",
        category="complexity",
        schema=cc_tool.get_tool_definition(),
        handler=_make_handler(cc_tool),
        description="Cognitive complexity: measure function readability using SonarSource spec across Python, JS/TS, Java, Go",
        emoji="🧠",
    )

    # nesting_complexity (consolidated: nesting_depth + loop_complexity)
    from .tools.nesting_complexity_tool import NestingComplexityTool
    nc_tool = NestingComplexityTool(project_root)
    registry.register(
        name="nesting_complexity",
        toolset="analysis",
        category="complexity",
        schema=nc_tool.get_tool_definition(),
        handler=_make_handler(nc_tool),
        description="Nesting complexity: detect deeply nested code and loop Big-O estimation across Python, JS/TS, Java, Go",
        emoji="📐",
    )

    # boolean_complexity
    from .tools.boolean_complexity_tool import BooleanComplexityTool
    bc_tool = BooleanComplexityTool(project_root)
    registry.register(
        name="boolean_complexity",
        toolset="analysis",
        category="complexity",
        schema=bc_tool.get_tool_definition(),
        handler=_make_handler(bc_tool),
        description="Boolean complexity: detect complex boolean expressions with too many conditions across Python, JS/TS, Java, Go",
        emoji="🔀",
    )

    # switch_smells
    from .tools.switch_smells_tool import SwitchSmellsTool
    ss_tool = SwitchSmellsTool(project_root)
    registry.register(
        name="switch_smells",
        toolset="analysis",
        category="design",
        schema=ss_tool.get_tool_definition(),
        handler=_make_handler(ss_tool),
        description="Switch smells: detect complex switch/match statements that should use polymorphism across Python, JS/TS, Java, Go",
        emoji="🔀",
    )

    # error_quality (consolidated: error_handling + exception_quality + error_message_quality)
    from .tools.error_quality_tool import ErrorQualityTool
    eq_tool = ErrorQualityTool(project_root)
    registry.register(
        name="error_quality",
        toolset="analysis",
        category="error-quality",
        schema=eq_tool.get_tool_definition(),
        handler=_make_handler(eq_tool),
        description="Error quality: detect anti-patterns (bare except, swallowed errors, broad exceptions), handler quality, and message quality across Python, JS/TS, Java, Go",
        emoji="🛡️",
    )

    # error_propagation
    from .tools.error_propagation_tool import ErrorPropagationTool
    ep_tool = ErrorPropagationTool(project_root)
    registry.register(
        name="error_propagation",
        toolset="analysis",
        category="error-quality",
        schema=ep_tool.get_tool_definition(),
        handler=_make_handler(ep_tool),
        description="Error propagation: trace error/exception flow through code, detect unhandled raises, swallowed exceptions, and missing catch blocks",
        emoji="🔄",
    )

    # test_flakiness
    from .tools.test_flakiness_tool import TestFlakinessTool
    tf_tool = TestFlakinessTool(project_root)
    registry.register(
        name="test_flakiness",
        toolset="analysis",
        category="test-quality",
        schema=tf_tool.get_tool_definition(),
        handler=_make_handler(tf_tool),
        description="Test flakiness: detect timing deps, random data, time-dependent assertions, and shared mutable state in tests",
        emoji="🎰",
    )

    # circular_dependency
    from .tools.circular_dependency_tool import CircularDependencyTool
    cd_tool = CircularDependencyTool(project_root)
    registry.register(
        name="circular_dependency",
        toolset="analysis",
        category="dependency",
        schema=cd_tool.get_tool_definition(),
        handler=_make_handler(cd_tool),
        description="Circular dependency: detect circular import/require cycles in Python, JS/TS, Java codebases",
        emoji="🔁",
    )

    # parameter_coupling
    from .tools.parameter_coupling_tool import ParameterCouplingTool
    pc_tool = ParameterCouplingTool(project_root)
    registry.register(
        name="parameter_coupling",
        toolset="analysis",
        category="coupling",
        schema=pc_tool.get_tool_definition(),
        handler=_make_handler(pc_tool),
        description="Parameter coupling: detect functions with too many parameters and Data Clumps across Python, JS/TS, Java, Go",
        emoji="🔗",
    )

    # type_annotation_coverage
    from .tools.type_annotation_coverage_tool import TypeAnnotationCoverageTool
    type_ann_tool = TypeAnnotationCoverageTool(project_root)
    registry.register(
        name="type_annotation_coverage",
        toolset="analysis",
        category="type-annotation",
        schema=type_ann_tool.get_tool_definition(),
        handler=_make_handler(type_ann_tool),
        description="Type annotation coverage: detect missing parameter/return type annotations in Python",
        emoji="🏷️",
    )

    # comment_quality
    from .tools.comment_quality_tool import CommentQualityTool
    cq_tool = CommentQualityTool(project_root)
    registry.register(
        name="comment_quality",
        toolset="analysis",
        category="documentation",
        schema=cq_tool.get_tool_definition(),
        handler=_make_handler(cq_tool),
        description="Comment quality: detect stale docs, param mismatches, missing returns, TODO tracking across Python, JS/TS, Java, Go",
        emoji="💬",
    )

    # call_graph
    from .tools.call_graph_tool import CallGraphTool
    cg_tool = CallGraphTool(project_root)
    registry.register(
        name="call_graph",
        toolset="analysis",
        category="call-graph",
        schema=cg_tool.get_tool_definition(),
        handler=_make_handler(cg_tool),
        description="Call graph: map function call relationships, detect island functions (never called) and god functions (too many calls)",
        emoji="🕸️",
    )

    # async_patterns
    from .tools.async_patterns_tool import AsyncPatternsTool
    ap_tool = AsyncPatternsTool(project_root)
    registry.register(
        name="async_patterns",
        toolset="analysis",
        category="async-patterns",
        schema=ap_tool.get_tool_definition(),
        handler=_make_handler(ap_tool),
        description="Async patterns: detect missing await, fire-and-forget, unhandled promises, blocking in async across Python, JS/TS, Java, Go",
        emoji="⚡",
    )

    # code_smell_detector
    cs_tool = CodeSmellDetectorTool(project_root)
    registry.register(
        name="code_smell_detector",
        toolset="analysis",
        category="code-quality",
        schema=cs_tool.get_tool_definition(),
        handler=_make_handler(cs_tool),
        description="Code smell detection: identify god classes, long methods, magic numbers, and other common code smells",
        emoji="👃",
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

    # semantic_search
    search_tool = SemanticSearchTool(project_root)
    registry.register(
        name="semantic_search",
        toolset="query",
        category="semantic-search",
        schema=search_tool.get_tool_definition(),
        handler=_make_handler(search_tool, method_name="execute"),
        description="Semantic code search: natural language queries with LLM understanding",
        emoji="🔍",
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

    # pr_summary
    pr_summary_tool = PRSummaryTool(project_root)
    registry.register(
        name="pr_summary",
        toolset="diagnostic",
        category="git-analysis",
        schema=pr_summary_tool.get_tool_definition(),
        handler=_make_handler(pr_summary_tool),
        description="Generate PR summaries from git diff: categorization, breaking changes, semantic analysis",
        emoji="📋",
    )

    # change_impact
    change_impact_tool = ChangeImpactTool(project_root)
    registry.register(
        name="change_impact",
        toolset="diagnostic",
        category="impact-analysis",
        schema=change_impact_tool.get_tool_definition(),
        handler=_make_handler(change_impact_tool),
        description="Analyze blast radius of file changes: impacted files, tools, and tests",
        emoji="💥",
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


def _register_overview_tools(registry: Any, project_root: str | None) -> None:
    """Register overview tools."""
    # overview
    overview_tool = OverviewTool(project_root)
    registry.register(
        name="overview",
        toolset="overview",
        category="project-overview",
        schema=overview_tool.get_tool_definition(),
        handler=_make_handler(overview_tool),
        description="Unified project overview with all analysis tools",
        emoji="📊",
    )


def _register_optimization_tools(registry: Any, project_root: str | None) -> None:
    """Register optimization tools."""
    # context_optimizer
    optimizer_tool = ContextOptimizerTool(project_root)
    registry.register(
        name="context_optimizer",
        toolset="optimization",
        category="context-optimization",
        schema=optimizer_tool.get_tool_definition(),
        handler=_make_handler(optimizer_tool),
        description="Optimize code context for LLM windows: intelligent filtering",
        emoji="⚡",
    )

    # i18n_strings
    from .tools.i18n_strings_tool import I18nStringsTool
    i18n_tool = I18nStringsTool(project_root)
    registry.register(
        name="i18n_strings",
        toolset="analysis",
        category="quality",
        schema=i18n_tool.get_tool_definition(),
        handler=_make_handler(i18n_tool),
        description="i18n readiness: detect user-visible strings needing internationalization",
        emoji="🌐",
    )

    # function_size
    from .tools.function_size_tool import FunctionSizeTool
    fs_tool = FunctionSizeTool(project_root)
    registry.register(
        name="function_size",
        toolset="analysis",
        category="complexity",
        schema=fs_tool.get_tool_definition(),
        handler=_make_handler(fs_tool),
        description="Function size: detect oversized functions by LOC and parameter count",
        emoji="📏",
    )

    # test_smells
    from .tools.test_smells_tool import TestSmellsTool
    ts_tool = TestSmellsTool(project_root)
    registry.register(
        name="test_smells",
        toolset="analysis",
        category="quality",
        schema=ts_tool.get_tool_definition(),
        handler=_make_handler(ts_tool),
        description="Test smell detection: empty tests, broad exception catches, sleep calls",
        emoji="🧪",
    )

    # logging_patterns
    from .tools.logging_patterns_tool import LoggingPatternsTool
    lp_tool = LoggingPatternsTool(project_root)
    registry.register(
        name="logging_patterns",
        toolset="analysis",
        category="quality",
        schema=lp_tool.get_tool_definition(),
        handler=_make_handler(lp_tool),
        description="Logging anti-pattern detection: silent catch, print logging, sensitive data in logs",
        emoji="📋",
    )

    # naming_conventions
    from .tools.naming_convention_tool import NamingConventionTool
    nc_tool = NamingConventionTool(project_root)
    registry.register(
        name="naming_conventions",
        toolset="analysis",
        category="naming-quality",
        schema=nc_tool.get_tool_definition(),
        handler=_make_handler(nc_tool),
        description="Naming conventions: detect identifiers that violate language conventions across Python, JS/TS, Java, Go",
        emoji="🏷️",
    )

    # assertion_quality
    from .tools.assertion_quality_tool import AssertionQualityTool
    aq_tool = AssertionQualityTool(project_root)
    registry.register(
        name="assertion_quality",
        toolset="analysis",
        category="test-quality",
        schema=aq_tool.get_tool_definition(),
        handler=_make_handler(aq_tool),
        description="Assertion quality: detect weak, vague, clustered assertions and missing branch coverage in tests",
        emoji="🎯",
    )

    # solid_principles
    from .tools.solid_principles_tool import SOLIDPrinciplesTool
    sp_tool = SOLIDPrinciplesTool(project_root)
    registry.register(
        name="solid_principles",
        toolset="analysis",
        category="solid-principles",
        schema=sp_tool.get_tool_definition(),
        handler=_make_handler(sp_tool),
        description="SOLID principles: detect SRP, OCP, LSP, ISP, DIP violations with per-principle scores",
        emoji="🏗️",
    )

    # coupling_metrics
    from .tools.coupling_metrics_tool import CouplingMetricsTool
    cm_tool = CouplingMetricsTool(project_root)
    registry.register(
        name="coupling_metrics",
        toolset="analysis",
        category="coupling-metrics",
        schema=cm_tool.get_tool_definition(),
        handler=_make_handler(cm_tool),
        description="Coupling metrics: fan-out, fan-in, instability per file to identify coupling hotspots and critical modules",
        emoji="🔗",
    )

    # return_path
    from .tools.return_path_tool import ReturnPathTool
    rp_tool = ReturnPathTool(project_root)
    registry.register(
        name="return_path",
        toolset="analysis",
        category="return-path",
        schema=rp_tool.get_tool_definition(),
        handler=_make_handler(rp_tool),
        description="Return path: detect inconsistent return paths, implicit None returns, and complex return logic across Python, JS/TS, Java, Go",
        emoji="↩️",
    )


    # empty_block
    from .tools.empty_block_tool import EmptyBlockTool
    eb_tool = EmptyBlockTool(project_root)
    registry.register(
        name="empty_block",
        toolset="analysis",
        category="design",
        schema=eb_tool.get_tool_definition(),
        handler=_make_handler(eb_tool),
        description="Empty block: detect empty function/catch/loop blocks that may hide bugs across Python, JS/TS, Java, Go",
        emoji="📭",
    )

    # god_class
    from .tools.god_class_tool import GodClassTool
    gc_tool = GodClassTool(project_root)
    registry.register(
        name="god_class",
        toolset="analysis",
        category="design",
        schema=gc_tool.get_tool_definition(),
        handler=_make_handler(gc_tool),
        description="God class: detect classes with too many methods and fields across Python, JS/TS, Java, Go",
        emoji="👑",
    )

    # lazy_class
    from .tools.lazy_class_tool import LazyClassTool
    lc_tool = LazyClassTool(project_root)
    registry.register(
        name="lazy_class",
        toolset="analysis",
        category="design",
        schema=lc_tool.get_tool_definition(),
        handler=_make_handler(lc_tool),
        description="Lazy class: detect classes with too few methods that may not justify their existence across Python, JS/TS, Java, Go",
        emoji="🦥",
    )

    # duplicate_condition
    from .tools.duplicate_condition_tool import DuplicateConditionTool
    dc_tool = DuplicateConditionTool(project_root)
    registry.register(
        name="duplicate_condition",
        toolset="analysis",
        category="quality",
        schema=dc_tool.get_tool_definition(),
        handler=_make_handler(dc_tool),
        description="Duplicate condition: detect identical if conditions that violate DRY across Python, JS/TS, Java, Go",
        emoji="🔁",
    )

    # method_chain
    from .tools.method_chain_tool import MethodChainTool
    mc_tool = MethodChainTool(project_root)
    registry.register(
        name="method_chain",
        toolset="analysis",
        category="design",
        schema=mc_tool.get_tool_definition(),
        handler=_make_handler(mc_tool),
        description="Method chain: detect Law of Demeter violations via long attribute chains across Python, JS/TS, Java, Go",
        emoji="🔗",
    )

    # string_concat_loop
    from .tools.string_concat_loop_tool import StringConcatLoopTool
    scl_tool = StringConcatLoopTool(project_root)
    registry.register(
        name="string_concat_loop",
        toolset="analysis",
        category="performance",
        schema=scl_tool.get_tool_definition(),
        handler=_make_handler(scl_tool),
        description="String concat in loops: detect O(n^2) string concatenation patterns across Python, JS/TS, Java, Go",
        emoji="🐌",
    )

    # primitive_obsession
    from .tools.primitive_obsession_tool import PrimitiveObsessionTool
    po_tool = PrimitiveObsessionTool(project_root)
    registry.register(
        name="primitive_obsession",
        toolset="analysis",
        category="design",
        schema=po_tool.get_tool_definition(),
        handler=_make_handler(po_tool),
        description="Primitive obsession: detect overuse of primitive types where value objects would be better",
        emoji="🔤",
    )

    # middle_man
    from .tools.middle_man_tool import MiddleManTool
    mm_tool = MiddleManTool(project_root)
    registry.register(
        name="middle_man",
        toolset="analysis",
        category="design",
        schema=mm_tool.get_tool_definition(),
        handler=_make_handler(mm_tool),
        description="Middle man: detect classes that primarily delegate without adding value across Python, JS/TS, Java, Go",
        emoji="🎭",
    )

    # tautological_condition
    from .tools.tautological_condition_tool import TautologicalConditionTool
    tc_tool = TautologicalConditionTool(project_root)
    registry.register(
        name="tautological_condition",
        toolset="analysis",
        category="quality",
        schema=tc_tool.get_tool_definition(),
        handler=_make_handler(tc_tool),
        description="Tautological condition: detect contradictory, subsumed, and self-comparison conditions that always evaluate the same way",
        emoji="⚖️",
    )

    # flag_argument
    from .tools.flag_argument_tool import FlagArgumentTool
    fa_tool = FlagArgumentTool(project_root)
    registry.register(
        name="flag_argument",
        toolset="analysis",
        category="design",
        schema=fa_tool.get_tool_definition(),
        handler=_make_handler(fa_tool),
        description="Flag argument: detect boolean parameters that indicate SRP violations across Python, JS/TS, Java, Go",
        emoji="🚩",
    )

    # nested_ternary
    from .tools.nested_ternary_tool import NestedTernaryTool
    nt_tool = NestedTernaryTool(project_root)
    registry.register(
        name="nested_ternary",
        toolset="analysis",
        category="readability",
        schema=nt_tool.get_tool_definition(),
        handler=_make_handler(nt_tool),
        description="Nested ternary: detect deeply nested ternary/conditional expressions across Python, JS/TS, Java",
        emoji="🔀",
    )

    # assignment_in_conditional
    from .tools.assignment_in_conditional_tool import AssignmentInConditionalTool
    aic_tool = AssignmentInConditionalTool(project_root)
    registry.register(
        name="assignment_in_conditional",
        toolset="analysis",
        category="bug-detection",
        schema=aic_tool.get_tool_definition(),
        handler=_make_handler(aic_tool),
        description="Assignment in conditional: detect = vs == typos in if/while conditions across JS/TS, Java, C/C++",
        emoji="🐛",
    )

    # regex_safety
    from .tools.regex_safety_tool import RegexSafetyTool
    rs_tool = RegexSafetyTool(project_root)
    registry.register(
        name="regex_safety",
        toolset="analysis",
        category="security",
        schema=rs_tool.get_tool_definition(),
        handler=_make_handler(rs_tool),
        description="Regex safety: detect ReDoS-vulnerable regex patterns (nested quantifiers, overlapping alternations) across Python, JS/TS, Java, Go",
        emoji="🔐",
    )

    # mutable_default_args
    from .tools.mutable_default_args_tool import MutableDefaultArgsTool
    mda_tool = MutableDefaultArgsTool(project_root)
    registry.register(
        name="mutable_default_args",
        toolset="analysis",
        category="bug-detection",
        schema=mda_tool.get_tool_definition(),
        handler=_make_handler(mda_tool),
        description="Mutable default args: detect Python functions with mutable default values (list, dict, set) causing shared state bugs",
        emoji="🐛",
    )

    # variable_shadowing
    from .tools.variable_shadowing_tool import VariableShadowingTool
    vs_tool = VariableShadowingTool(project_root)
    registry.register(
        name="variable_shadowing",
        toolset="analysis",
        category="bug-detection",
        schema=vs_tool.get_tool_definition(),
        handler=_make_handler(vs_tool),
        description="Variable shadowing: detect inner-scope variables that shadow outer-scope variables across Python, JS/TS, Java, Go",
        emoji="🎭",
    )

    # dead_store
    from .tools.dead_store_tool import DeadStoreTool
    ds_tool = DeadStoreTool(project_root)
    registry.register(
        name="dead_store",
        toolset="analysis",
        category="bug-detection",
        schema=ds_tool.get_tool_definition(),
        handler=_make_handler(ds_tool),
        description="Dead store: detect variables assigned but never read, self-assignments, and immediate reassignments across Python, JS/TS, Java, Go",
        emoji="🗑️",
    )

    # redundant_else
    from .tools.redundant_else_tool import RedundantElseTool
    re_tool = RedundantElseTool(project_root)
    registry.register(
        name="redundant_else",
        toolset="analysis",
        category="style",
        schema=re_tool.get_tool_definition(),
        handler=_make_handler(re_tool),
        description="Redundant else: detect unnecessary else blocks where the if branch already terminates across Python, JS/TS, Java, Go",
        emoji="↩️",
    )

    # unused_parameter
    from .tools.unused_parameter_tool import UnusedParameterTool
    up_tool = UnusedParameterTool(project_root)
    registry.register(
        name="unused_parameter",
        toolset="analysis",
        category="bug-detection",
        schema=up_tool.get_tool_definition(),
        handler=_make_handler(up_tool),
        description="Unused parameter: detect function/method parameters that are never referenced in the function body across Python, JS/TS, Java, Go",
        emoji="👻",
    )

    # callback_hell
    from .tools.callback_hell_tool import CallbackHellTool
    ch_tool = CallbackHellTool(project_root)
    registry.register(
        name="callback_hell",
        toolset="analysis",
        category="async-quality",
        schema=ch_tool.get_tool_definition(),
        handler=_make_handler(ch_tool),
        description="Callback hell: detect deeply nested callbacks and long .then() chains across Python, JS/TS, Java, Go",
        emoji="🌀",
    )

    # hardcoded_ip
    from .tools.hardcoded_ip_tool import HardcodedIPTool
    hi_tool = HardcodedIPTool(project_root)
    registry.register(
        name="hardcoded_ip",
        toolset="analysis",
        category="security",
        schema=hi_tool.get_tool_definition(),
        handler=_make_handler(hi_tool),
        description="Hardcoded IP/port: detect IP addresses and port numbers that should be externalized across Python, JS/TS, Java, Go",
        emoji="🌐",
    )

    # missing_break
    from .tools.missing_break_tool import MissingBreakTool
    mb_tool = MissingBreakTool(project_root)
    registry.register(
        name="missing_break",
        toolset="analysis",
        category="bug-detection",
        schema=mb_tool.get_tool_definition(),
        handler=_make_handler(mb_tool),
        description="Missing break: detect unintentional switch/case fall-through in JS/TS and Java",
        emoji="🔍",
    )

    # discarded_return
    from .tools.discarded_return_tool import DiscardedReturnTool
    dr_tool = DiscardedReturnTool(project_root)
    registry.register(
        name="discarded_return",
        toolset="analysis",
        category="bug-detection",
        schema=dr_tool.get_tool_definition(),
        handler=_make_handler(dr_tool),
        description="Discarded return: detect function calls whose return values are silently thrown away",
        emoji="🗑️",
    )

    # literal_boolean_comparison
    from .tools.literal_boolean_comparison_tool import LiteralBooleanComparisonTool
    lbc_tool = LiteralBooleanComparisonTool(project_root)
    registry.register(
        name="literal_boolean_comparison",
        toolset="analysis",
        category="code-quality",
        schema=lbc_tool.get_tool_definition(),
        handler=_make_handler(lbc_tool),
        description="Literal boolean comparison: detect x == True, x == None, x == null and suggest proper idioms",
        emoji="⚖️",
    )

    # double_negation
    from .tools.double_negation_tool import DoubleNegationTool
    dn_tool = DoubleNegationTool(project_root)
    registry.register(
        name="double_negation",
        toolset="analysis",
        category="readability",
        schema=dn_tool.get_tool_definition(),
        handler=_make_handler(dn_tool),
        description="Double negation: detect not not x, !!x patterns and suggest clearer alternatives",
        emoji="⁉️",
    )

    # global_state
    from .tools.global_state_tool import GlobalStateTool
    gs_tool = GlobalStateTool(project_root)
    registry.register(
        name="global_state",
        toolset="analysis",
        category="state-quality",
        schema=gs_tool.get_tool_definition(),
        handler=_make_handler(gs_tool),
        description="Global state: detect module-level mutable variables, global/nonlocal keywords, static non-final fields, and package-level variables",
        emoji="🌐",
    )

    # reflection_usage
    from .tools.reflection_usage_tool import ReflectionUsageTool
    ru_tool = ReflectionUsageTool(project_root)
    registry.register(
        name="reflection_usage",
        toolset="analysis",
        category="security",
        schema=ru_tool.get_tool_definition(),
        handler=_make_handler(ru_tool),
        description="Reflection usage: detect eval/exec/getattr, Class.forName, reflect.* patterns that make code hard to audit",
        emoji="🪞",
    )

    # debug_statement
    from .tools.debug_statement_tool import DebugStatementTool
    debug_stmt_tool = DebugStatementTool(project_root)
    registry.register(
        name="debug_statement",
        toolset="analysis",
        category="code-quality",
        schema=debug_stmt_tool.get_tool_definition(),
        handler=_make_handler(debug_stmt_tool),
        description="Debug statements: detect leftover print/console.log/System.out.println/fmt.Println calls that should be removed before production",
        emoji="🐛",
    )

    # commented_code
    from .tools.commented_code_tool import CommentedCodeTool
    cc_tool = CommentedCodeTool(project_root)
    registry.register(
        name="commented_code",
        toolset="analysis",
        category="code-quality",
        schema=cc_tool.get_tool_definition(),
        handler=_make_handler(cc_tool),
        description="Commented-out code: detect code blocks in comments (assignments, calls, imports, declarations) that should be removed",
        emoji="🗑️",
    )

    # loose_equality
    from .tools.loose_equality_tool import LooseEqualityTool
    le_tool = LooseEqualityTool(project_root)
    registry.register(
        name="loose_equality",
        toolset="analysis",
        category="code-quality",
        schema=le_tool.get_tool_definition(),
        handler=_make_handler(le_tool),
        description="Loose equality: detect == and != in JavaScript/TypeScript that should use === and !== to avoid type coercion bugs",
        emoji="⚖️",
    )

    # simplified_conditional
    from .tools.simplified_conditional_tool import SimplifiedConditionalTool
    sc_tool = SimplifiedConditionalTool(project_root)
    registry.register(
        name="simplified_conditional",
        toolset="analysis",
        category="readability",
        schema=sc_tool.get_tool_definition(),
        handler=_make_handler(sc_tool),
        description="Simplified conditional: detect ternary expressions that can be simplified (cond ? true : false → cond)",
        emoji="✂️",
    )

    # yoda_condition
    from .tools.yoda_condition_tool import YodaConditionTool
    yoda_tool = YodaConditionTool(project_root)
    registry.register(
        name="yoda_condition",
        toolset="analysis",
        category="readability",
        schema=yoda_tool.get_tool_definition(),
        handler=_make_handler(yoda_tool),
        description="Yoda condition: detect comparisons where literal is on the left (\"expected\" == actual → actual == \"expected\")",
        emoji="🔄",
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
