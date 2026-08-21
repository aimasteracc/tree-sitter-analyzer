#!/usr/bin/env python3
"""``health`` facade — Wave B facade for the FacadeTool framework (P0 geode layer).

Folds 12 health/analysis capabilities behind one ``action`` parameter.
The ``uml`` / ``graph`` / ``similarity`` trio have been split into the
separate ``viz`` facade (see ``viz_facade.py``).

==========  ===========================================  ===================================================
action      inner / route                                engine / purpose
==========  ===========================================  ===================================================
project     ``project_health``  (ProjectHealthTool)      overall project code-quality grade
file        ``file_health``     (FileHealthTool)         per-file health metrics
scale       ``analyze_scale``   (AnalyzeScaleTool)       LOC / complexity / size metrics
patterns    ``code_patterns``   (CodePatternsTool)       anti-pattern detection by category
heatmap     ``codegraph_complexity_heatmap``             complexity ranked by file / function
imports     ``codegraph_import_graph``                   module import dependency graph
matrix      ``codegraph_dependency_matrix``              coupling matrix, coupling ranks
dead        ``codegraph_dead_code``                      unreferenced functions / imports / vars
routes      ``route_detector``  (RouteDetectorTool)      HTTP route discovery
overview    ``codegraph_overview``                       entry-points / hubs / dead summary
deps        ``analyze_dependencies`` (R5)                dependency analysis — mode sub-param:
                                                         summary|cycles|blast|file_deps
test_gap    ``codegraph_test_gap`` (CodeGraphTestGapTool) untested symbol discovery, complexity-ranked
self        ``self_health``     (SelfHealthTool)         RFC-0025 Layer 5 self-proprioception: per-route
                                                         p50/p95 latency by tier + analysis-cache hit rate + AST-index state
refactor_queue ``refactor_queue`` (RefactorQueueTool)     RFC-0027 §L8 top-N prioritized refactor queue
==========  ===========================================  ===================================================

R5 (PRD §3): ``deps`` maps to the single ``DependencyAnalysisTool`` whose
``mode`` param (``summary`` / ``cycles`` / ``blast`` / ``file_deps``) is
declared in the inner schema. The framework's arg-projection filter KEEPS
``mode`` because the inner declares it — no bespoke closure needed.

Annotation honesty: every action in this facade is read-only, so
``readOnlyHint=True`` is valid (unlike the ``edit`` / ``project`` facades
that span mutating actions).
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# All health actions are read-only — a single honest ``readOnlyHint=True``
# is valid here (same rationale as the ``search`` facade).
_HEALTH_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

_HEALTH_DESCRIPTION = (
    "Code-intelligence (codegraph-compatible) health and analysis facade. "
    "Covers codegraph_complexity_heatmap, codegraph_import_graph, "
    "codegraph_dependency_matrix, codegraph_dead_code, codegraph_overview, "
    "and project/file health metrics in one tool. "
    "Pick a capability via `action`:\n"
    "- action=project — overall project code-quality grade + per-file grade "
    "breakdown. Params: min_grade, max_files.\n"
    "- action=file — per-file health: complexity, duplication, style. "
    "Params: file_path (required), language.\n"
    "- action=scale — lines-of-code / complexity / size metrics. "
    "Params: file_path, file_paths, language, metrics_only, include_complexity, "
    "include_details, include_guidance.\n"
    "- action=patterns — anti-pattern detection by category and severity. "
    "Params: file_path (required), categories, severity_threshold.\n"
    "- action=heatmap — complexity heatmap ranked by file or function "
    "(codegraph_complexity_heatmap equivalent). "
    "Params: mode, file_path, function_name, language, directory, max_files.\n"
    "- action=imports — module import dependency graph (who imports whom, "
    "codegraph_import_graph equivalent). Params: mode, file_path, max_depth.\n"
    "- action=matrix — coupling matrix and top-k coupling ranks "
    "(codegraph_dependency_matrix equivalent). "
    "Params: mode, file_path, top_k, threshold.\n"
    "- action=dead — unreferenced functions / unused imports / unused variables "
    "(codegraph_dead_code equivalent). "
    "Params: mode, include_test_files, max_dead, max_imports, max_variables.\n"
    "- action=routes — HTTP route discovery across framework conventions. "
    "Params: mode, url_pattern, file_path, framework.\n"
    "- action=overview — entry-points / hub files / dead-code summary "
    "(codegraph_overview equivalent). "
    "Params: max_entry_points, max_hubs, max_dead, max_coupled_files.\n"
    "- action=deps — dependency analysis (R5 multi-mode). "
    "Params: mode (summary|cycles|blast|file_deps), file_path.\n"
    "  mode=summary: project-level dependency overview.\n"
    "  mode=cycles: detect circular dependencies.\n"
    "  mode=blast: blast-radius for a given file_path.\n"
    "  mode=file_deps: file-level dependency details.\n"
    "- action=test_gap — untested symbol discovery ranked by cyclomatic complexity. "
    "Params: mode (summary|gaps|file), file_path, language, max_files, max_gaps, "
    "include_covered, output_format.\n"
    "- action=self — self-proprioception (RFC-0025 Layer 5): per-(tool, action) "
    "p50/p95 latency split by tier (cold/warm/cached), exact invocation counts, "
    "the in-process analysis-cache hit rate, and the on-disk AST-index state "
    "(.ast-cache/index.db) for THIS process. No params. Unmeasured values "
    "are `null` with status NO_OBSERVATIONS — never a fabricated 0.0.\n"
    "- action=refactor_queue — top-N prioritized refactor queue (RFC-0027 §L8): "
    "files ranked by (1 - health/100) * log(1 + churn_30d) * (dead_ratio + 0.1), "
    "each row carrying grade, weakest dimension, 30-day churn, dead-symbol "
    "count and a concrete action (split / delete dead / extract). Returns "
    "CHURN_UNAVAILABLE rather than a queue of zeros when the AST index has no "
    "churn to read. Params: top_n.\n"
    "For UML diagrams, call/dependency graph visualizations, and similarity "
    "analysis, use the ``viz`` facade instead."
)


def build_health_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``health`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).

    The ``uml`` / ``graph`` / ``similarity`` trio have been moved to the
    ``viz`` facade (``build_viz_facade``). This facade now has 11 actions.
    """
    from .analyze_scale_tool import AnalyzeScaleTool
    from .code_patterns_tool import CodePatternsTool
    from .codegraph_overview_tool import CodeGraphOverviewTool
    from .complexity_heatmap_tool import CodeGraphComplexityHeatmapTool
    from .dead_code_tool import CodeGraphDeadCodeTool
    from .dependency_analysis_tool import DependencyAnalysisTool
    from .dependency_matrix_tool import CodeGraphDependencyMatrixTool
    from .file_health_tool import FileHealthTool
    from .import_graph_tool import CodeGraphImportGraphTool
    from .project_health_tool import ProjectHealthTool
    from .refactor_queue_tool import RefactorQueueTool
    from .route_detector_tool import RouteDetectorTool
    from .self_health_tool import SelfHealthTool
    from .test_gap_tool import CodeGraphTestGapTool

    facade = FacadeTool(
        facade_name="health",
        action_map={
            # Core quality gates
            "project": ProjectHealthTool(project_root),
            "file": FileHealthTool(project_root),
            "scale": AnalyzeScaleTool(project_root),
            "patterns": CodePatternsTool(project_root),
            # Codegraph-backed structural analysis (all keep ``mode`` via R5)
            "heatmap": CodeGraphComplexityHeatmapTool(project_root),
            "imports": CodeGraphImportGraphTool(project_root),
            "matrix": CodeGraphDependencyMatrixTool(project_root),
            "dead": CodeGraphDeadCodeTool(project_root),
            "routes": RouteDetectorTool(project_root),
            "overview": CodeGraphOverviewTool(project_root),
            # R5: deps — multi-mode, ``mode`` kept by projection filter automatically
            "deps": DependencyAnalysisTool(project_root),
            # RFC-0003 pre-requisite: wire orphaned test-gap tool into the facade
            "test_gap": CodeGraphTestGapTool(project_root),
            # RFC-0025 Layer 5: self-proprioception (latency p50/p95 by tier)
            "self": SelfHealthTool(project_root),
            # RFC-0027 §L8: the refactor-priority formula, now in code.
            # Read-only (three signal reads, zero writes) so the facade-wide
            # readOnlyHint=True above stays honest.
            "refactor_queue": RefactorQueueTool(project_root),
        },
        bespoke_map={},  # no F5 bespoke routes needed for health
        description=_HEALTH_DESCRIPTION,
        annotations=_HEALTH_ANNOTATIONS,
        project_root=project_root,
    )
    return facade
