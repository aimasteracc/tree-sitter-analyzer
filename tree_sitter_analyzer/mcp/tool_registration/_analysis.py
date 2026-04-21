"""Tool registration — analysis."""
from typing import Any

from ..tools.analyze_code_structure_tool import AnalyzeCodeStructureTool
from ..tools.analyze_scale_tool import AnalyzeScaleTool
from ..tools.code_clone_detection_tool import CodeCloneDetectionTool
from ..tools.code_diff_tool import CodeDiffTool
from ..tools.dependency_query_tool import DependencyQueryTool
from ..tools.error_recovery_tool import ErrorRecoveryTool
from ..tools.finding_correlation_tool import FindingCorrelationTool
from ..tools.grammar_discovery_tool import GrammarDiscoveryTool
from ..tools.health_score_tool import HealthScoreTool
from ..tools.java_patterns_tool import JavaPatternAnalysisTool
from ..tools.refactoring_suggestions_tool import RefactoringSuggestionsTool
from ..tools.semantic_impact_tool import SemanticImpactTool
from ..tools.test_coverage_tool import TestCoverageTool
from ..tools.trace_impact_tool import TraceImpactTool
from ..tools.understand_codebase_tool import UnderstandCodebaseTool
from ._shared import _make_handler


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

    # dead_code_analysis (consolidated: dead_code + dead_code_path)
    from ..tools.dead_code_analysis_tool import DeadCodeAnalysisTool
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
    from ..tools.design_patterns_tool import DesignPatternsTool
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
    from ..tools.api_discovery_tool import ApiDiscoveryTool
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
    from ..tools.env_tracker_tool import EnvTrackerTool
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
    from ..tools.magic_values_tool import MagicValuesTool
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
    from ..tools.import_sanitizer_tool import ImportSanitizerTool
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
    from ..tools.doc_coverage_tool import DocCoverageTool
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
    from ..tools.cognitive_complexity_tool import CognitiveComplexityTool
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
    from ..tools.nesting_complexity_tool import NestingComplexityTool
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
    from ..tools.boolean_complexity_tool import BooleanComplexityTool
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
    from ..tools.switch_smells_tool import SwitchSmellsTool
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
    from ..tools.error_quality_tool import ErrorQualityTool
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
    from ..tools.error_propagation_tool import ErrorPropagationTool
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
    from ..tools.test_flakiness_tool import TestFlakinessTool
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
    from ..tools.circular_dependency_tool import CircularDependencyTool
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
    from ..tools.parameter_coupling_tool import ParameterCouplingTool
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
    from ..tools.type_annotation_coverage_tool import TypeAnnotationCoverageTool
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
    from ..tools.comment_quality_tool import CommentQualityTool
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
    from ..tools.call_graph_tool import CallGraphTool
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
    from ..tools.async_patterns_tool import AsyncPatternsTool
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

    # finding_correlation
    fc_tool = FindingCorrelationTool(project_root)
    registry.register(
        name="finding_correlation",
        toolset="analysis",
        category="finding-correlation",
        schema=fc_tool.get_tool_definition(),
        handler=_make_handler(fc_tool),
        description="Finding correlation: run multiple analyzers and identify compound hotspots flagged by 2+ independent analyzers",
        emoji="🎯",
    )
