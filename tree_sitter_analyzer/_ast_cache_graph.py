"""BFS graph traversal helpers for ASTCache.

These are pure functions — they take an explicit ``conn`` argument and do not
access any class state.  Extracted from ``ASTCache._bfs_callers`` /
``_bfs_callees`` so that:

1. The functions can be unit-tested without an ``ASTCache`` instance.
2. The line count (and therefore size score) of ``ast_cache.py`` is reduced.
3. The call-graph traversal logic lives in one place with a clear contract.

``ASTCache._bfs_callers`` and ``ASTCache._bfs_callees`` are now thin wrappers
that delegate to these functions.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Shared SQL fragment
# ---------------------------------------------------------------------------

_EDGE_SELECT = (
    "SELECT caller_name, caller_file, caller_line, "
    "callee_name, callee_full, file_path, callee_line, callee_resolved_file "
    "FROM ast_call_edges "
)

# ---------------------------------------------------------------------------
# Direction-specific row fetchers
# ---------------------------------------------------------------------------


def _fetch_caller_rows(
    conn: sqlite3.Connection,
    name: str,
    file_: str | None,
) -> list[Any]:
    """Return rows where *name*/*file_* is the callee (i.e. rows with callers)."""
    if file_:
        rows = conn.execute(
            _EDGE_SELECT
            + "WHERE (callee_name = ? OR callee_full = ?) AND callee_resolved_file = ?",
            (name, name, file_),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                _EDGE_SELECT
                + "WHERE (callee_name = ? OR callee_full = ?) AND file_path = ?",
                (name, name, file_),
            ).fetchall()
        return rows
    return conn.execute(
        _EDGE_SELECT + "WHERE callee_name = ? OR callee_full = ?",
        (name, name),
    ).fetchall()


def _fetch_callee_rows(
    conn: sqlite3.Connection,
    name: str,
    file_: str | None,
) -> list[Any]:
    """Return rows where *name*/*file_* is the caller (i.e. rows with callees)."""
    if file_:
        return conn.execute(
            _EDGE_SELECT + "WHERE caller_name = ? AND caller_file = ?",
            (name, file_),
        ).fetchall()
    return conn.execute(
        _EDGE_SELECT + "WHERE caller_name = ?",
        (name,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Direction-specific key / entry / next-hop helpers
# ---------------------------------------------------------------------------


def _caller_key(row: Any) -> str:
    return f"{row['caller_file']}:{row['caller_name']}:{row['caller_line']}"


def _caller_entry(row: Any, depth: int) -> dict[str, Any]:
    _cfile = row["callee_resolved_file"] or row["file_path"]
    return {
        "caller_name": row["caller_name"],
        "caller_file": row["caller_file"],
        "caller_line": row["caller_line"],
        "callee_name": row["callee_name"],
        "callee_full": row["callee_full"],
        "callee_file": _cfile,
        "callee_line": row["callee_line"],
        "depth": depth + 1,
    }


def _caller_next_hop(row: Any) -> tuple[str, str | None]:
    return row["caller_name"], row["caller_file"]


def _callee_key(row: Any) -> str:
    return f"{row['callee_name']}:{row['file_path']}:{row['callee_line']}"


def _callee_entry(row: Any, depth: int) -> dict[str, Any]:
    _cfile = row["callee_resolved_file"] or row["file_path"]
    return {
        "caller_name": row["caller_name"],
        "caller_file": row["caller_file"],
        "caller_line": row["caller_line"],
        "callee_name": row["callee_name"],
        "callee_full": row["callee_full"],
        "callee_file": _cfile,
        "callee_resolved_file": row["callee_resolved_file"] or "",
        "callee_line": row["callee_line"],
        "depth": depth + 1,
    }


def _callee_next_hop(row: Any) -> tuple[str, str | None]:
    return row["callee_name"], None


# ---------------------------------------------------------------------------
# Generic BFS engine
# ---------------------------------------------------------------------------


def _bfs_traverse(
    conn: sqlite3.Connection,
    start_name: str,
    start_file: str | None,
    max_depth: int,
    fetch_rows: Callable,
    make_key: Callable,
    make_entry: Callable,
    next_hop: Callable,
) -> list[dict[str, Any]]:
    """BFS traversal over ``ast_call_edges`` in either direction.

    Args:
        conn: Live SQLite connection.
        start_name: Seed symbol name.
        start_file: Optional file path to narrow the seed lookup.
        max_depth: Maximum hops (0 → empty, 1 → direct neighbours only).
        fetch_rows: Callable(conn, name, file_) → list of row dicts.
        make_key: Callable(row) → deduplication key string.
        make_entry: Callable(row, depth) → result entry dict.
        next_hop: Callable(row) → (name, file_) for the next BFS frontier.
    """
    visited: set[str] = set()
    result: list[dict[str, Any]] = []
    queue: list[tuple[str, str | None, int]] = [(start_name, start_file, 0)]
    while queue:
        current_name, current_file, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        for row in fetch_rows(conn, current_name, current_file):
            key = make_key(row)
            if key in visited:
                continue
            visited.add(key)
            result.append(make_entry(row, depth))
            if max_depth > 1:
                nxt_name, nxt_file = next_hop(row)
                queue.append((nxt_name, nxt_file, depth + 1))
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def bfs_callers(
    conn: sqlite3.Connection,
    callee_name: str,
    callee_file: str | None,
    max_depth: int,
) -> list[dict[str, Any]]:
    """BFS traversal returning all callers of ``callee_name``.

    Args:
        conn: Live SQLite connection with ``ast_call_edges`` table.
        callee_name: Name of the function/method being looked up.
        callee_file: Optional resolved file path to narrow the match.
        max_depth: Maximum BFS hops (0 → empty, 1 → direct callers only).

    Returns:
        List of caller dicts with keys: caller_name, caller_file,
        caller_line, callee_name, callee_full, callee_file, callee_line,
        depth.  Deduplicated by (caller_file, caller_name, caller_line).
    """
    return _bfs_traverse(
        conn,
        callee_name,
        callee_file,
        max_depth,
        _fetch_caller_rows,
        _caller_key,
        _caller_entry,
        _caller_next_hop,
    )


def bfs_callees(
    conn: sqlite3.Connection,
    caller_name: str,
    caller_file: str | None,
    max_depth: int,
) -> list[dict[str, Any]]:
    """BFS traversal returning all callees of ``caller_name``.

    Args:
        conn: Live SQLite connection with ``ast_call_edges`` table.
        caller_name: Name of the calling function/method.
        caller_file: Optional file path to narrow the match.
        max_depth: Maximum BFS hops (0 → empty, 1 → direct callees only).

    Returns:
        List of callee dicts with keys: caller_name, caller_file,
        caller_line, callee_name, callee_full, callee_file,
        callee_resolved_file, callee_line, depth.  Deduplicated by
        (callee_name, file_path, callee_line).
    """
    return _bfs_traverse(
        conn,
        caller_name,
        caller_file,
        max_depth,
        _fetch_callee_rows,
        _callee_key,
        _callee_entry,
        _callee_next_hop,
    )
