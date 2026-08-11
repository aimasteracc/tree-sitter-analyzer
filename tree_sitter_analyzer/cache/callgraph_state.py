"""Persisted call-graph-built marker for AST cache readers (#708)."""

from __future__ import annotations

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

_CREATE_DDL = (
    "CREATE TABLE IF NOT EXISTS ast_call_graph_state ("
    "id INTEGER PRIMARY KEY, "
    "built INTEGER NOT NULL, "
    "built_at REAL NOT NULL)"
)
_BUILT_MARKER_ID = 1
_EXPLICITLY_INCOMPLETE_ID = 2


def mark_call_graph_built(conn: sqlite3.Connection) -> None:
    """Best-effort wrapper for callers that cannot publish certification."""
    try:
        mark_call_graph_built_strict(conn)
    except sqlite3.OperationalError:
        logger.debug("could not mark call-graph-built", exc_info=True)


def mark_call_graph_built_strict(conn: sqlite3.Connection) -> None:
    """Persist and verify the exact authoritative built marker."""
    conn.execute(_CREATE_DDL)
    conn.execute(
        "INSERT INTO ast_call_graph_state (id, built, built_at) "
        "VALUES (1, 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "built = excluded.built, "
        "built_at = excluded.built_at",
        (time.time(),),
    )
    conn.execute(
        "DELETE FROM ast_call_graph_state WHERE id = ?",
        (_EXPLICITLY_INCOMPLETE_ID,),
    )
    rows = conn.execute(
        "SELECT id, built FROM ast_call_graph_state WHERE id IN (?, ?) ORDER BY id",
        (_BUILT_MARKER_ID, _EXPLICITLY_INCOMPLETE_ID),
    ).fetchall()
    exact = [
        (
            int(row["id"] if isinstance(row, sqlite3.Row) else row[0]),
            int(row["built"] if isinstance(row, sqlite3.Row) else row[1]),
        )
        for row in rows
    ]
    if exact != [(_BUILT_MARKER_ID, 1)]:
        raise sqlite3.OperationalError("CALL_GRAPH_MARKER_VERIFY_FAILED")
    conn.commit()


def clear_call_graph_built(conn: sqlite3.Connection) -> None:
    """Clear the marker before replacing the derived call graph."""
    try:
        clear_call_graph_built_strict(conn)
    except sqlite3.OperationalError:
        logger.debug("could not clear call-graph-built", exc_info=True)


def clear_call_graph_built_strict(conn: sqlite3.Connection) -> None:
    """Clear the marker, propagating failures to transactional callers."""
    conn.execute(_CREATE_DDL)
    conn.execute(
        "INSERT INTO ast_call_graph_state (id, built, built_at) "
        "VALUES (1, 0, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "built = excluded.built, "
        "built_at = excluded.built_at",
        (time.time(),),
    )
    conn.execute(
        "INSERT INTO ast_call_graph_state (id, built, built_at) "
        "VALUES (?, 0, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "built = excluded.built, "
        "built_at = excluded.built_at",
        (_EXPLICITLY_INCOMPLETE_ID, time.time()),
    )
    conn.commit()


def call_graph_built(conn: sqlite3.Connection) -> bool:
    """Return True iff this cache holds a built call graph.

    Fast path: trust the ``ast_call_graph_state`` marker when it is explicitly
    set. An explicit-incomplete sentinel makes invalidation authoritative even
    while unrelated edges remain. Safety net (#1005): legacy caches without
    that sentinel may carry a populated ``edges`` table but no reliable marker;
    treat those edges as proof the graph exists. One cheap COUNT query; no
    source-tree walk.
    """
    # Fast path: trust the marker if explicitly set.
    try:
        rows = conn.execute(
            "SELECT id, built FROM ast_call_graph_state WHERE id IN (?, ?)",
            (_BUILT_MARKER_ID, _EXPLICITLY_INCOMPLETE_ID),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []  # marker table missing — fall through to the edges probe
    marker_values = {
        int(row["id"] if isinstance(row, sqlite3.Row) else row[0]): int(
            row["built"] if isinstance(row, sqlite3.Row) else row[1]
        )
        for row in rows
    }
    if _EXPLICITLY_INCOMPLETE_ID in marker_values:
        return False
    if _BUILT_MARKER_ID in marker_values:
        built = marker_values[_BUILT_MARKER_ID]
        if bool(built):
            return True
    # Safety net: a populated edges table means the graph exists.
    try:
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()
    except sqlite3.OperationalError:
        return False
    return bool(edge_count and edge_count[0] > 0)
