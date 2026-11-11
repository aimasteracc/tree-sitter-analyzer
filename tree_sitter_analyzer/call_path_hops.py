"""Hop builders of :mod:`.call_path`: one per search direction and backend.

#1942: every SQL hop carries the call-site line (``line`` and
``call_site_line``) and whether the edge is bound to a definition file
(``callee_resolution``); a backward hop no longer reports the caller's
definition line as its line.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Direction helpers — forward (callee) direction
# ---------------------------------------------------------------------------


def _fwd_state(row: dict[str, Any]) -> tuple[str, str | None]:
    """Extract the next (name, file) state from a forward-edge row."""
    # #735: callee_resolved_file is the definition file; file_path is the
    # CALLER's file (call-site).  When resolution is unknown, use None so
    # _query_forward_edges falls back to a name-only query (PR #912) rather
    # than searching for outgoing edges under the wrong (caller) file.
    callee_file = row.get("callee_resolved_file") or None
    return (row["callee_name"], callee_file)


def _fwd_hop(
    current_name: str, current_file: str | None, row: dict[str, Any]
) -> dict[str, Any]:
    """Build a hop dict for a forward (callee direction) step."""
    # #735: callee_file must be the DEFINITION file, not the call-site file.
    # file_path in the row is the caller's file; callee_resolved_file is what
    # we want.  Fall back to empty string (unknown) rather than the caller's
    # file, which would be misleading.
    callee_file = row.get("callee_resolved_file") or ""
    line = row.get("callee_line", 0)
    return {
        "caller": current_name,
        "caller_file": current_file or "",
        "callee": row["callee_name"],
        "callee_file": callee_file,
        "line": line,
        "call_site_line": line,
        "callee_resolution": _resolution(row),
    }


def _resolution(row: dict[str, Any]) -> str:
    """#1942: ``name_only`` when the edge is not bound to a definition file."""
    return "resolved" if row.get("callee_resolved_file") else "name_only"


# ---------------------------------------------------------------------------
# Direction helpers — backward (caller) direction
# ---------------------------------------------------------------------------


def _bwd_state(row: dict[str, Any]) -> tuple[str, str | None]:
    """Extract the next (name, file) state from a backward-edge row."""
    return (row["caller_name"], row.get("caller_file") or None)


def _bwd_hop(
    current_name: str, current_file: str | None, row: dict[str, Any]
) -> dict[str, Any]:
    """Build a hop dict for a backward (caller direction) step."""
    # #735: callee_resolved_file in a backward edge row IS the definition file
    # of current_name (the callee we're looking up callers for). Use it when
    # target_file was not provided (current_file is None/empty).
    callee_def_file = row.get("callee_resolved_file") or current_file or ""
    return _backward_hop(row, current_name, callee_def_file)


def _backward_hop(row: dict[str, Any], callee: str, callee_file: str) -> dict[str, Any]:
    """#1942: ``line`` is the call site (as on forward hops), not the caller's
    definition line; that one is ``caller_line``."""
    site = row.get("call_site_line") or 0
    hop = {
        "caller": row["caller_name"],
        "caller_file": row.get("caller_file", ""),
        "callee": callee,
        "callee_file": callee_file,
        "line": site,
        "call_site_line": site,
        "callee_resolution": _resolution(row),
    }
    if row.get("caller_line"):
        hop["caller_line"] = row["caller_line"]
    return hop


# ---------------------------------------------------------------------------
# Direction helpers — forward graph direction
# ---------------------------------------------------------------------------


def _graph_fwd_state(callee: dict[str, Any]) -> tuple[str, str | None]:
    return (callee.get("name", ""), callee.get("file", "") or None)


def _graph_fwd_hop(
    current_name: str, current_file: str | None, callee: dict[str, Any]
) -> dict[str, Any]:
    return {
        "caller": current_name,
        "caller_file": current_file or "",
        "callee": callee.get("name", ""),
        "callee_file": callee.get("file", ""),
        "line": callee.get("line", 0),
    }


# ---------------------------------------------------------------------------
# Direction helpers — backward graph direction
# ---------------------------------------------------------------------------


def _graph_bwd_state(caller: dict[str, Any]) -> tuple[str, str | None]:
    return (caller.get("name", ""), caller.get("file", "") or None)


def _graph_bwd_hop(
    current_name: str, current_file: str | None, caller: dict[str, Any]
) -> dict[str, Any]:
    return {
        "caller": caller.get("name", ""),
        "caller_file": caller.get("file", ""),
        "callee": current_name,
        "callee_file": current_file or "",
        "line": caller.get("line", 0),
    }
