#!/usr/bin/env python3
"""β legacy-name shim (Wave C2, G2) — one deprecation cycle (removed v2.x).

v2.0 hard-cut the public MCP surface from 63 discrete tools to 8 facades. For one
release cycle the 63 old tool names keep working: a call to ``codegraph_callers``
is transparently forwarded to ``nav.execute({"action": "callers", ...})``.

Deprecation visibility is **dual-channel** (PRD G2):

1. **stderr** — a one-line ``DeprecationWarning``-style log so operators with a
   terminal see it. (CLAUDE.md §3: diagnostic output goes to stderr, never
   stdout.)
2. **response envelope** — a ``deprecation`` field injected into the (dict)
   response so the calling *agent* sees it inline and can migrate. Non-dict
   returns (the ``search_content`` / ``find_and_grep`` ``int`` exit-code path)
   are forwarded verbatim — there is nowhere to attach the field, and the stderr
   channel still fires.

The crosswalk lives in ``facade_map.LEGACY_TOOL_MAP`` (single source of truth,
shared with the parity contracts). ``set_project_path`` is NOT shimmed — it is a
standalone infrastructure entry, not a former facade action.
"""

from __future__ import annotations

import sys
from typing import Any

from .facade_map import LEGACY_TOOL_MAP

# Legacy names whose facade route needs an extra control key beyond ``action``.
# ``codegraph_call_graph`` historically returned a full call graph; route it to
# ``nav.callers`` with ``scope=graph`` (R4) so the BFS traversal behaviour is
# preserved rather than collapsing to a 1-hop point lookup.
_LEGACY_EXTRA_ARGS: dict[str, dict[str, Any]] = {
    "codegraph_call_graph": {"scope": "graph"},
}


def is_legacy_name(name: str) -> bool:
    """True if ``name`` is a deprecated 1.x tool name with a facade route."""
    return name in LEGACY_TOOL_MAP


def _emit_stderr_warning(old_name: str, facade: str, action: str) -> None:
    """Channel 1: one-line stderr deprecation notice (CLAUDE.md §3 compliant)."""
    try:
        print(
            f"DeprecationWarning: MCP tool '{old_name}' is deprecated and will be "
            f"removed in a future release. Use '{facade}' with action='{action}' "
            f"instead.",
            file=sys.stderr,
        )
    except (ValueError, OSError):  # stream closed during shutdown
        pass


def _deprecation_field(old_name: str, facade: str, action: str) -> dict[str, Any]:
    """Channel 2 payload: the ``deprecation`` envelope field agents can read."""
    return {
        "deprecated": True,
        "old_name": old_name,
        "facade": facade,
        "action": action,
        "message": (
            f"'{old_name}' is deprecated; call '{facade}' with "
            f"action='{action}'. The legacy name works for one release cycle."
        ),
    }


async def dispatch_legacy(server: Any, name: str, arguments: dict[str, Any]) -> Any:
    """Forward a legacy tool name to its facade and annotate the response.

    Returns the inner result verbatim except that, when the result is a ``dict``,
    a ``deprecation`` field is added (idempotent — never clobbers existing keys
    beyond ``deprecation`` itself). Raises ``KeyError`` only if ``name`` is not a
    legacy name (callers should gate on :func:`is_legacy_name` first).
    """
    facade_name, action = LEGACY_TOOL_MAP[name]
    facade = server.tools.get(facade_name)
    if facade is None:
        raise ValueError(
            f"legacy shim: facade '{facade_name}' for deprecated tool "
            f"'{name}' is not registered"
        )

    _emit_stderr_warning(name, facade_name, action)

    forwarded: dict[str, Any] = dict(arguments)
    forwarded["action"] = action
    forwarded.update(_LEGACY_EXTRA_ARGS.get(name, {}))

    result = await facade.execute(forwarded)

    if isinstance(result, dict):
        # Inject the deprecation field without disturbing the verdict envelope.
        annotated = dict(result)
        annotated["deprecation"] = _deprecation_field(name, facade_name, action)
        return annotated
    # Non-dict (int exit-code) path: nothing to annotate; stderr channel fired.
    return result
