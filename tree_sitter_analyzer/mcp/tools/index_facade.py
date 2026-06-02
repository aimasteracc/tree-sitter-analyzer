#!/usr/bin/env python3
"""``index`` facade — Wave B consolidation, 6-action index lifecycle hub.

Folds index lifecycle capabilities behind one ``action`` parameter:

==========  ==========================================  ==================================
action      inner / route                               when to use
==========  ==========================================  ==================================
status      ``codegraph_status``                        index health check (read-only)
build       ``build_project_index``                     full (re)build of index
full        ``codegraph_full_index``                    force full reindex
auto        ``codegraph_autoindex``                     enable background auto-indexing
sync        ``codegraph_incremental_sync``              fast incremental sync after edits
cache       ``ast_cache``                               raw AST cache query
==========  ==========================================  ==================================

Annotation note (spec §6 / review §8 F-extra-3):
    ``build`` / ``full`` / ``auto`` / ``sync`` WRITE the on-disk index.
    ``readOnlyHint=False`` is therefore honest. ``status`` and ``cache`` are
    read-only but a facade cannot split its hint per-action, so the mutating
    actions govern the facade-level annotation.
    ``destructiveHint=False`` because all writes are additive (re-index) or
    cache-read; no data is destroyed.

    At P0 this facade is NOT registered in ``_tool_registry.py`` (Wave C
    cutover handles registration). The annotation is set correctly now so
    Wave C is clean.
"""

from __future__ import annotations

from typing import Any

from .facade_tool import FacadeTool

# annotation-honesty rationale in module docstring above
_INDEX_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": False,  # build/full/auto/sync write the on-disk index
    "destructiveHint": False,  # writes are additive (re-index); no data destroyed
    "idempotentHint": False,  # build/full are not strictly idempotent
    "openWorldHint": False,
}

_INDEX_DESCRIPTION = (
    "Code-intelligence (codegraph-compatible) index lifecycle hub. "
    "Covers codegraph_status, codegraph_full_index, codegraph_autoindex, "
    "codegraph_incremental_sync, and AST cache query in one tool. "
    "Pick a capability via `action`:\n"
    "\n"
    "READ-ONLY:\n"
    "- action=status — check codegraph index health without writing "
    "(codegraph_status equivalent). "
    "Returns node/edge counts, staleness, and error indicators. "
    "Params: (none).\n"
    "- action=cache — query the raw AST cache for symbols, types, and "
    "references. Params: query, file_path, kind, limit.\n"
    "\n"
    "WRITES ON-DISK INDEX:\n"
    "- action=build — full (re)build of the project index. Slow; use "
    "when index is absent or corrupt. Params: force.\n"
    "- action=full — force a complete full reindex "
    "(codegraph_full_index equivalent). Params: (none).\n"
    "- action=auto — enable/configure background auto-indexing "
    "(codegraph_autoindex equivalent). Params: enable, watch.\n"
    "- action=sync — run one incremental sync pass (fast; use after "
    "editing files, codegraph_incremental_sync equivalent). Params: paths.\n"
)


def build_index_facade(project_root: str | None = None) -> FacadeTool:
    """Construct the ``index`` facade wired to live inner tool instances.

    Imports are inlined to keep cold-start cost off the import path for callers
    that don't build the facade (matches the lazy-import convention in
    ``_tool_registry.py``).
    """
    from .ast_cache_tool import ASTCacheTool
    from .auto_index_tool import CodeGraphAutoIndexTool
    from .build_project_index_tool import BuildProjectIndexTool
    from .codegraph_status_tool import CodeGraphStatusTool
    from .full_index_tool import CodeGraphFullIndexTool
    from .incremental_sync_tool import CodeGraphIncrementalSyncTool

    facade = FacadeTool(
        facade_name="index",
        action_map={
            # -- read-only -------------------------------------------------
            "status": CodeGraphStatusTool(project_root),
            "cache": ASTCacheTool(project_root),
            # -- writes on-disk index --------------------------------------
            "build": BuildProjectIndexTool(project_root),
            "full": CodeGraphFullIndexTool(project_root),
            "auto": CodeGraphAutoIndexTool(project_root),
            "sync": CodeGraphIncrementalSyncTool(project_root),
        },
        bespoke_map={},  # all 6 actions are clean action_map delegates
        description=_INDEX_DESCRIPTION,
        annotations=_INDEX_ANNOTATIONS,
        project_root=project_root,
    )
    # No bespoke inners to register: every action routes via action_map,
    # so G3 rebind propagation is fully automatic.
    return facade
