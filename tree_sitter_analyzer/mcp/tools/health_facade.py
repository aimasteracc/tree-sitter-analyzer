#!/usr/bin/env python3
"""``health`` facade — Wave B facade for the FacadeTool framework (P0 geode layer).

Folds 14 health/analysis capabilities behind one ``action`` parameter.

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
uml         ``codegraph_uml``   (CodeGraphUMLTool)       UML class/sequence diagrams
graph       ``codegraph_visualize``                      call/dependency graph visualizations
overview    ``codegraph_overview``                       entry-points / hubs / dead summary
similarity  ``codegraph_similarity``                     duplicate / near-duplicate detection
deps        ``analyze_dependencies`` (R5)                dependency analysis — mode sub-param:
                                                         summary|cycles|blast|file_deps
==========  ===========================================  ===================================================

R5 (PRD §3): ``deps`` maps to the single ``DependencyAnalysisTool`` whose
``mode`` param (``summary`` / ``cycles`` / ``blast`` / ``file_deps``) is
declared in the inner schema. The framework's arg-projection filter KEEPS
``mode`` because the inner declares it — no bespoke closure needed.

Annotation honesty: every action in this facade is read-only, so
``readOnlyHint=True`` is valid (unlike the ``edit`` / ``project`` facades
that span mutating actions).

NOTE on action count: this facade has 14 actions. PRD §3 notes that >12
may feel large; the ``uml`` / ``graph`` / ``similarity`` trio are flagged
as candidates for a future ``viz`` split (see final message in build session).
This facade keeps all 14 for Wave B; the caller is informed.
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
    "Unified code health and analysis. Pick a capability via `action`:\n"
    "- action=project — overall project code-quality grade + per-file grade "
    "breakdown. Params: min_grade, max_files.\n"
    "- action=file — per-file health: complexity, duplication, style. "
    "Params: file_path (required), language.\n"
    "- action=scale — lines-of-code / complexity / size metrics. "
    "Params: file_path, file_paths, language, metrics_only, include_complexity, "
    "include_details, include_guidance.\n"
    "- action=patterns — anti-pattern detection by category and severity. "
    "Params: file_path (required), categories, severity_threshold.\n"
    "- action=heatmap — complexity heatmap ranked by file or function. "
    "Params: mode, file_path, function_name, language, directory, max_files.\n"
    "- action=imports — module import dependency graph (who imports whom). "
    "Params: mode, file_path, max_depth.\n"
    "- action=matrix — coupling matrix and top-k coupling ranks. "
    "Params: mode, file_path, top_k, threshold.\n"
    "- action=dead — unreferenced functions / unused imports / unused variables. "
    "Params: mode, include_test_files, max_dead, max_imports, max_variables.\n"
    "- action=routes — HTTP route discovery across framework conventions. "
    "Params: mode, url_pattern, file_path, framework.\n"
    "- action=uml — UML class or sequence diagrams. "
    "Params: diagram, source, target, max_edges, max_depth, max_paths, "
    "package_depth, include_external_bases.\n"
    "- action=graph — call/dependency graph visualizations. "
    "Params: mode, file_path, function, depth, max_edges, direction.\n"
    "- action=overview — entry-points / hub files / dead-code summary. "
    "Params: max_entry_points, max_hubs, max_dead, max_coupled_files.\n"
    "- action=similarity — duplicate / near-duplicate code detection. "
    "Params: mode, min_lines, min_group_size, max_groups, use_cache.\n"
    "- action=deps — dependency analysis (R5 multi-mode). "
    "Params: mode (summary|cycles|blast|file_deps), file_path.\n"
    "  mode=summary: project-level dependency overview.\n"
    "  mode=cycles: detect circular dependencies.\n"
    "  mode=blast: blast-radius for a given file_path.\n"
    "  mode=file_deps: file-level dependency details."
)


def build_health_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``health`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).
    """
    from .analyze_scale_tool import AnalyzeScaleTool
    from .code_patterns_tool import CodePatternsTool
    from .code_similarity_tool import CodeGraphSimilarityTool
    from .codegraph_overview_tool import CodeGraphOverviewTool
    from .codegraph_visualize_tool import CodeGraphVisualizeTool
    from .complexity_heatmap_tool import CodeGraphComplexityHeatmapTool
    from .dead_code_tool import CodeGraphDeadCodeTool
    from .dependency_analysis_tool import DependencyAnalysisTool
    from .dependency_matrix_tool import CodeGraphDependencyMatrixTool
    from .file_health_tool import FileHealthTool
    from .import_graph_tool import CodeGraphImportGraphTool
    from .project_health_tool import ProjectHealthTool
    from .route_detector_tool import RouteDetectorTool
    from .uml_tool import CodeGraphUMLTool

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
            # Visualization / diagram cluster (uml/graph/similarity flagged as
            # split candidates if the 14-action count becomes unwieldy — Wave C)
            "uml": CodeGraphUMLTool(project_root),
            "graph": CodeGraphVisualizeTool(project_root),
            "overview": CodeGraphOverviewTool(project_root),
            "similarity": CodeGraphSimilarityTool(project_root),
            # R5: deps — multi-mode, ``mode`` kept by projection filter automatically
            "deps": DependencyAnalysisTool(project_root),
        },
        bespoke_map={},  # no F5 bespoke routes needed for health
        description=_HEALTH_DESCRIPTION,
        annotations=_HEALTH_ANNOTATIONS,
        project_root=project_root,
    )
    return facade
