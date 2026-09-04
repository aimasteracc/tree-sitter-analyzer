"""Tool registry factory for the MCP server (Wave C2 — 8-facade cutover).

v2.0 β hard cut: the public MCP surface is the **8 domain facades**
(``search`` / ``nav`` / ``structure`` / ``health`` / ``edit`` / ``project`` /
``index`` / ``viz``) instead of the 63 discrete inner tools. Each facade fans an
``action`` parameter out to the unchanged inner tools (verdict / JSON envelope
preserved verbatim — see ``facade_tool.py`` and PRD §7).

The 63 legacy tool names are NOT registered here anymore. They remain reachable
for one deprecation cycle (v2.x) via the legacy-name shim in
``server_utils/tool_registration.py`` (β / G2), which forwards
``old_name`` → ``facade.execute({action: ...})`` using ``facade_map.LEGACY_TOOL_MAP``.

``set_project_path`` is a standalone infrastructure entry registered separately
in ``tool_registration.py`` (it mutates server-level state no inner tool can
reach), so the final client-visible surface is **8 facades + set_project_path**.

Pulse API tools (``pulse`` / ``pulse_batch`` / ``get_project_schema``) are
registered as first-class entries alongside the facades. They provide 1-query
symbol context for AI agents replacing 10-20 individual tool calls.

Imports are inlined (not module-top) so the ~316 ms cold-start cost is only paid
when a registry is actually built (PERF-3).
"""

from __future__ import annotations

from typing import Any


def create_tool_registry(
    project_root: str | None,
) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Instantiate and return the 8 facade tools.

    Returns ``(tool_instances, lookup)`` where ``tool_instances`` is an ordered
    ``[(facade_name, facade_instance), ...]`` list and ``lookup`` is the same
    keyed by name. The tuple order governs public registration order in the MCP
    ``list_tools`` response.

    Inner tool classes are still imported (lazily, inside each ``build_*_facade``)
    — they back the facade actions and the legacy shim. They are simply no longer
    registered as top-level MCP tools.
    """
    from .tools.edit_facade import build_edit_facade
    from .tools.health_facade import build_health_facade
    from .tools.index_facade import build_index_facade
    from .tools.nav_facade import build_nav_facade
    from .tools.project_facade import build_project_facade
    from .tools.pulse_tool import (
        build_project_schema_tool,
        build_pulse_batch_tool,
        build_pulse_tool,
    )
    from .tools.search_facade import build_search_facade
    from .tools.semantic_tool import build_semantic_neighbors_tool
    from .tools.tql_tool import build_tql_execute_tool, build_tql_schema_tool
    from .tools.structure_facade import build_structure_facade
    from .tools.viz_facade import build_viz_facade

    tool_instances: list[tuple[str, Any]] = [
        ("search", build_search_facade(project_root)),
        ("nav", build_nav_facade(project_root)),
        ("structure", build_structure_facade(project_root)),
        ("health", build_health_facade(project_root)),
        ("edit", build_edit_facade(project_root)),
        ("project", build_project_facade(project_root)),
        ("index", build_index_facade(project_root)),
        ("viz", build_viz_facade(project_root)),
        # Pulse API — 1-query symbol context for AI agents.
        ("get_project_schema", build_project_schema_tool(project_root)),
        ("pulse", build_pulse_tool(project_root)),
        ("pulse_batch", build_pulse_batch_tool(project_root)),
        # TQL — extended Hyphae DSL with temporal + depth-quantifier pseudo-classes.
        ("tql_schema", build_tql_schema_tool(project_root)),
        ("tql_execute", build_tql_execute_tool(project_root)),
        # Semantic search — vector similarity over indexed symbol embeddings.
        ("semantic_neighbors", build_semantic_neighbors_tool(project_root)),
    ]
    return tool_instances, dict(tool_instances)
