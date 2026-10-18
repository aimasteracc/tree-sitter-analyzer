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

Imports are inlined (not module-top) so the ~316 ms cold-start cost is only paid
when a registry is actually built (PERF-3).
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

#: Registered facades in public registration order (governs ``tools/list``
#: order) -> whether the builder ``tools/<name>_facade.build_<name>_facade``
#: also takes the subscription lifecycle manager. A dict literal keyed by the
#: public name, so ``scripts/codemap_surface.py`` reads the surface statically.
_FACADES: dict[str, bool] = {
    "search": True,
    "nav": False,
    "structure": False,
    "health": False,
    "edit": False,
    "project": False,
    "index": True,
    "viz": False,
}
FACADE_NAMES: tuple[str, ...] = tuple(_FACADES)


def build_facade(
    name: str,
    project_root: str | None,
    lifecycle_manager: Any | None = None,
) -> Any:
    """Build ONE facade, importing only that facade's inner tools (#1675).

    A cold server answering its first ``nav`` call used to import and construct
    all 8 facades (~100 inner tools, ~500 modules) first; building just the
    facade being called skips the other seven.
    """
    if name not in _FACADES:
        raise ValueError(f"unknown facade: {name!r}")
    module = importlib.import_module(f".tools.{name}_facade", __package__)
    builder = getattr(module, f"build_{name}_facade")
    if _FACADES[name]:
        return builder(project_root, lifecycle_manager)
    return builder(project_root)


def create_tool_registry(
    project_root: str | None,
    lifecycle_manager: Any | None = None,
    prebuilt: Mapping[str, Any] | None = None,
) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Instantiate and return the 8 facade tools.

    Returns ``(tool_instances, lookup)`` where ``tool_instances`` is an ordered
    ``[(facade_name, facade_instance), ...]`` list and ``lookup`` is the same
    keyed by name. The tuple order governs public registration order in the MCP
    ``list_tools`` response.

    Inner tool classes are still imported (lazily, inside each ``build_*_facade``)
    — they back the facade actions and the legacy shim. They are simply no longer
    registered as top-level MCP tools.

    ``prebuilt`` facades (already built one at a time by a server answering
    ``tools/call``) are reused rather than rebuilt, so every caller keeps
    seeing the same facade instance and its state (#1675).
    """
    ready = prebuilt or {}
    tool_instances: list[tuple[str, Any]] = [
        (
            name,
            ready[name]
            if name in ready
            else build_facade(name, project_root, lifecycle_manager),
        )
        for name in FACADE_NAMES
    ]
    return tool_instances, dict(tool_instances)
