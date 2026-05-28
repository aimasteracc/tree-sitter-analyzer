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
from typing import Any


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
    visited: set[str] = set()
    result: list[dict[str, Any]] = []
    queue: list[tuple[str, str | None, int]] = [(callee_name, callee_file, 0)]
    while queue:
        current_name, current_file, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        if current_file:
            rows = conn.execute(
                "SELECT caller_name, caller_file, caller_line, "
                "callee_name, callee_full, file_path, callee_line, "
                "callee_resolved_file "
                "FROM ast_call_edges "
                "WHERE (callee_name = ? OR callee_full = ?) "
                "AND callee_resolved_file = ?",
                (current_name, current_name, current_file),
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    "SELECT caller_name, caller_file, caller_line, "
                    "callee_name, callee_full, file_path, callee_line, "
                    "callee_resolved_file "
                    "FROM ast_call_edges "
                    "WHERE (callee_name = ? OR callee_full = ?) "
                    "AND file_path = ?",
                    (current_name, current_name, current_file),
                ).fetchall()
        else:
            rows = conn.execute(
                "SELECT caller_name, caller_file, caller_line, "
                "callee_name, callee_full, file_path, callee_line, "
                "callee_resolved_file "
                "FROM ast_call_edges WHERE callee_name = ? OR callee_full = ?",
                (current_name, current_name),
            ).fetchall()
        for row in rows:
            key = f"{row['caller_file']}:{row['caller_name']}:{row['caller_line']}"
            if key in visited:
                continue
            visited.add(key)
            callee_file_val = row["callee_resolved_file"] or row["file_path"]
            entry: dict[str, Any] = {
                "caller_name": row["caller_name"],
                "caller_file": row["caller_file"],
                "caller_line": row["caller_line"],
                "callee_name": row["callee_name"],
                "callee_full": row["callee_full"],
                "callee_file": callee_file_val,
                "callee_line": row["callee_line"],
                "depth": depth + 1,
            }
            result.append(entry)
            if max_depth > 1:
                queue.append((row["caller_name"], row["caller_file"], depth + 1))
    return result


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
    visited: set[str] = set()
    result: list[dict[str, Any]] = []
    queue: list[tuple[str, str | None, int]] = [(caller_name, caller_file, 0)]
    while queue:
        current_name, current_file, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        if current_file:
            rows = conn.execute(
                "SELECT caller_name, caller_file, caller_line, "
                "callee_name, callee_full, file_path, callee_line, callee_resolved_file "
                "FROM ast_call_edges "
                "WHERE caller_name = ? AND caller_file = ?",
                (current_name, current_file),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT caller_name, caller_file, caller_line, "
                "callee_name, callee_full, file_path, callee_line, callee_resolved_file "
                "FROM ast_call_edges WHERE caller_name = ?",
                (current_name,),
            ).fetchall()
        for row in rows:
            key = f"{row['callee_name']}:{row['file_path']}:{row['callee_line']}"
            if key in visited:
                continue
            visited.add(key)
            callee_file_val = row["callee_resolved_file"] or row["file_path"]
            entry: dict[str, Any] = {
                "caller_name": row["caller_name"],
                "caller_file": row["caller_file"],
                "caller_line": row["caller_line"],
                "callee_name": row["callee_name"],
                "callee_full": row["callee_full"],
                "callee_file": callee_file_val,
                "callee_resolved_file": row["callee_resolved_file"] or "",
                "callee_line": row["callee_line"],
                "depth": depth + 1,
            }
            result.append(entry)
            if max_depth > 1:
                queue.append((row["callee_name"], None, depth + 1))
    return result
