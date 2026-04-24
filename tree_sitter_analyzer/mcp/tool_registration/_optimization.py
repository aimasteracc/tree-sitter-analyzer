"""Tool registration — optimization."""
from typing import Any

from ..tools.context_optimizer_tool import ContextOptimizerTool
from ._shared import _make_handler


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
    from ..tools.i18n_strings_tool import I18nStringsTool
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
    from ..tools.function_size_tool import FunctionSizeTool
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
    from ..tools.test_smells_tool import TestSmellsTool
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
    from ..tools.logging_patterns_tool import LoggingPatternsTool
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
    from ..tools.naming_convention_tool import NamingConventionTool
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
    from ..tools.assertion_quality_tool import AssertionQualityTool
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
    from ..tools.solid_principles_tool import SOLIDPrinciplesTool
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
    from ..tools.coupling_metrics_tool import CouplingMetricsTool
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
    from ..tools.return_path_tool import ReturnPathTool
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


    # god_class
    from ..tools.god_class_tool import GodClassTool
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
    from ..tools.lazy_class_tool import LazyClassTool
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

    # method_chain
    from ..tools.method_chain_tool import MethodChainTool
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
    from ..tools.string_concat_loop_tool import StringConcatLoopTool
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



    # encapsulation_break
    from ..tools.encapsulation_break_tool import EncapsulationBreakTool
    eb_tool = EncapsulationBreakTool(project_root)
    registry.register(
        name="encapsulation_break",
        toolset="analysis",
        category="encapsulation",
        schema=eb_tool.get_tool_definition(),
        handler=_make_handler(eb_tool),
        description="Encapsulation break: detect methods that return direct references to internal mutable state across Python, JS/TS, Java",
        emoji="🔓",
    )

    # primitive_obsession
    from ..tools.primitive_obsession_tool import PrimitiveObsessionTool
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
    from ..tools.middle_man_tool import MiddleManTool
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
    from ..tools.tautological_condition_tool import TautologicalConditionTool
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
    from ..tools.flag_argument_tool import FlagArgumentTool
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


    # regex_safety
    from ..tools.regex_safety_tool import RegexSafetyTool
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

    # dead_store
    from ..tools.dead_store_tool import DeadStoreTool
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

    # guard_clause
    from ..tools.guard_clause_tool import GuardClauseTool
    gcl_tool = GuardClauseTool(project_root)
    registry.register(
        name="guard_clause",
        toolset="analysis",
        category="style",
        schema=gcl_tool.get_tool_definition(),
        handler=_make_handler(gcl_tool),
        description="Guard clause: detect if/else blocks where inverting the condition and returning early would flatten the code across Python, JS/TS, Java, Go",
        emoji="🛡️",
    )

    # config_drift
    from ..tools.config_drift_tool import ConfigDriftTool
    cd_tool = ConfigDriftTool(project_root)
    registry.register(
        name="config_drift",
        toolset="analysis",
        category="best-practice",
        schema=cd_tool.get_tool_definition(),
        handler=_make_handler(cd_tool),
        description="Config drift: detect hardcoded configuration values (host, port, url, api_key, etc.) that should be externalized via env vars across Python, JS/TS, Java, Go",
        emoji="⚙️",
    )

    # exception_signature
    from ..tools.exception_signature_tool import ExceptionSignatureTool
    es_tool = ExceptionSignatureTool(project_root)
    registry.register(
        name="exception_signature",
        toolset="analysis",
        category="best-practice",
        schema=es_tool.get_tool_definition(),
        handler=_make_handler(es_tool),
        description="Exception signature: extract what exceptions each function can throw and check documentation consistency across Python, JS/TS, Java, Go",
        emoji="⚡",
    )

    # unused_parameter
    from ..tools.unused_parameter_tool import UnusedParameterTool
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


    # discarded_return
    from ..tools.discarded_return_tool import DiscardedReturnTool
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

    # global_state
    from ..tools.global_state_tool import GlobalStateTool
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
    from ..tools.reflection_usage_tool import ReflectionUsageTool
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


    # long_parameter_list
    from ..tools.long_parameter_list_tool import LongParameterListTool
    lpl_tool = LongParameterListTool(project_root)
    registry.register(
        name="long_parameter_list",
        toolset="analysis",
        category="complexity",
        schema=lpl_tool.get_tool_definition(),
        handler=_make_handler(lpl_tool),
        description="Long parameter list: detect functions with 5+ parameters that should use a parameter object",
        emoji="📋",
    )

    from ..tools.protocol_completeness_tool import ProtocolCompletenessTool
    pc_tool = ProtocolCompletenessTool(project_root)
    registry.register(
        name="protocol_completeness",
        toolset="analysis",
        category="correctness",
        schema=pc_tool.get_tool_definition(),
        handler=_make_handler(pc_tool),
        description="Protocol completeness: detect incomplete protocol implementations (__eq__ without __hash__, equals without hashCode)",
        emoji="🔧",
    )

    from ..tools.query_mutation_tool import QueryMutationTool
    qm_tool = QueryMutationTool(project_root)
    registry.register(
        name="query_mutation",
        toolset="analysis",
        category="correctness",
        schema=qm_tool.get_tool_definition(),
        handler=_make_handler(qm_tool),
        description="Query method mutation: detect CQS violations (query-named methods that modify state)",
        emoji="🔍",
    )

    # silent_suppression
    from ..tools.silent_suppression_tool import SilentSuppressionTool
    ss_tool = SilentSuppressionTool(project_root)
    registry.register(
        name="silent_suppression",
        toolset="analysis",
        category="bug-detection",
        schema=ss_tool.get_tool_definition(),
        handler=_make_handler(ss_tool),
        description="Silent error suppression: detect catch/except blocks that swallow errors (pass, continue, logging-only, return None)",
        emoji="🤫",
    )


    # nested_class
    from ..tools.nested_class_tool import NestedClassTool
    ncls_tool = NestedClassTool(project_root)
    registry.register(
        name="nested_class",
        toolset="analysis",
        category="design",
        schema=ncls_tool.get_tool_definition(),
        handler=_make_handler(ncls_tool),
        description="Nested class: detect classes inside other classes indicating potential design smell",
        emoji="🏗️",
    )

    # method_cohesion
    from ..tools.method_cohesion_tool import MethodCohesionTool
    mcoh_tool = MethodCohesionTool(project_root)
    registry.register(
        name="method_cohesion",
        toolset="analysis",
        category="design",
        schema=mcoh_tool.get_tool_definition(),
        handler=_make_handler(mcoh_tool),
        description="Method cohesion: detect classes with LCOM4 > 1 where methods operate on disjoint field sets across Python, JS/TS, Java, Go",
        emoji="🧩",
    )

    # temporal_coupling
    from ..tools.temporal_coupling_tool import TemporalCouplingTool
    tmpc_tool = TemporalCouplingTool(project_root)
    registry.register(
        name="temporal_coupling",
        toolset="analysis",
        category="design",
        schema=tmpc_tool.get_tool_definition(),
        handler=_make_handler(tmpc_tool),
        description="Temporal coupling: detect methods that read instance vars written only by other methods (hidden ordering dependency)",
        emoji="🔗",
    )

    # neural_perception
    from ..tools.neural_perception_tool import NeuralPerceptionTool
    np_tool = NeuralPerceptionTool(project_root)
    registry.register(
        name="neural_perception",
        toolset="analysis",
        category="meta-analysis",
        schema=np_tool.get_tool_definition(),
        handler=_make_handler(np_tool),
        description="Neural perception: run ALL analyzers on files, correlate findings into holistic perception map with compound hotspots and health scores",
        emoji="🧠",
    )

    # brain
    from ..tools.brain_tool import BrainTool
    brain_tool = BrainTool(project_root)
    registry.register(
        name="brain",
        toolset="analysis",
        category="meta-analysis",
        schema=brain_tool.get_tool_definition(),
        handler=_make_handler(brain_tool),
        description="One-call complete project awareness: full file context, hotspots, impact analysis. No further tool calls needed after warm-up.",
        emoji="🧠",
    )
