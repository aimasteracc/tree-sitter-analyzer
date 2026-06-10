#!/usr/bin/env python3
"""``viz`` facade — Wave B facade for the FacadeTool framework (P0 geode layer).

Folds 3 visualization capabilities behind one ``action`` parameter, split
from the ``health`` facade (which had 14 actions — the uml/graph/similarity
trio was flagged as a split candidate per PRD §3).

==========  ====================================  =============================================
action      inner / route                         engine / purpose
==========  ====================================  =============================================
uml         ``codegraph_uml`` (CodeGraphUMLTool)  UML class/sequence diagrams
graph       ``codegraph_visualize``               call/dependency graph visualizations
similarity  ``codegraph_similarity``              duplicate / near-duplicate code detection
==========  ====================================  =============================================

Annotation honesty: every action in this facade is read-only (pure generation
/ analysis, no mutations), so ``readOnlyHint=True`` is valid.
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# All viz actions are read-only — pure diagram/analysis generation.
_VIZ_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

_VIZ_DESCRIPTION = (
    "Code-intelligence (codegraph-compatible) visualization and similarity facade. "
    "Covers codegraph_uml (UML diagrams), codegraph_visualize (call/dependency "
    "graph visualizations), and codegraph_similarity (duplicate code detection) "
    "in one tool. Pick a capability via `action`:\n"
    "- action=uml — UML class or sequence diagrams "
    "(codegraph_uml equivalent). "
    "Params: diagram, source, target, max_edges, max_depth, max_paths, "
    "package_depth, include_external_bases, file_path, class_name, include_tests.\n"
    "- action=graph — call/dependency graph visualizations "
    "(codegraph_visualize equivalent). "
    "Params: mode, file_path, function, depth, max_edges, direction.\n"
    "- action=similarity — duplicate / near-duplicate code detection "
    "(codegraph_similarity equivalent). "
    "Params: mode, min_lines, min_group_size, max_groups, use_cache.\n"
)


def build_viz_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``viz`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).
    """
    from .code_similarity_tool import CodeGraphSimilarityTool
    from .codegraph_visualize_tool import CodeGraphVisualizeTool
    from .uml_tool import CodeGraphUMLTool

    facade = FacadeTool(
        facade_name="viz",
        action_map={
            "uml": CodeGraphUMLTool(project_root),
            "graph": CodeGraphVisualizeTool(project_root),
            "similarity": CodeGraphSimilarityTool(project_root),
        },
        bespoke_map={},  # no F5 bespoke routes needed for viz
        description=_VIZ_DESCRIPTION,
        annotations=_VIZ_ANNOTATIONS,
        project_root=project_root,
    )
    return facade
