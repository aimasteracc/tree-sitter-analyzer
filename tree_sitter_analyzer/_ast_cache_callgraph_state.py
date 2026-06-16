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


def mark_call_graph_built(conn: sqlite3.Connection) -> None:
    """Record that the call-graph derivation completed for this cache."""
    try:
        conn.execute(_CREATE_DDL)
        conn.execute(
            "INSERT INTO ast_call_graph_state (id, built, built_at) "
            "VALUES (1, 1, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "built = excluded.built, "
            "built_at = excluded.built_at",
            (time.time(),),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("could not mark call-graph-built", exc_info=True)


def clear_call_graph_built(conn: sqlite3.Connection) -> None:
    """Clear the marker before replacing the derived call graph."""
    try:
        conn.execute(_CREATE_DDL)
        conn.execute(
            "INSERT INTO ast_call_graph_state (id, built, built_at) "
            "VALUES (1, 0, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "built = excluded.built, "
            "built_at = excluded.built_at",
            (time.time(),),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("could not clear call-graph-built", exc_info=True)


def call_graph_built(conn: sqlite3.Connection) -> bool:
    """Return True iff this cache holds a built call graph.

    Fast path: trust the ``ast_call_graph_state`` marker when it is explicitly
    set. Safety net (#1005): legacy/crashed/partial-write caches can carry a
    fully populated ``edges`` table with NO marker (or a cleared ``built=0``)
    — treat a non-empty ``edges`` table as proof the graph exists, otherwise
    every consumer gating on this signal wrongly reports the index empty
    (#981/#987/#990/#1001/#1004). One cheap COUNT query; no source-tree walk.
    """
    # Fast path: trust the marker if explicitly set.
    try:
        row = conn.execute(
            "SELECT built FROM ast_call_graph_state WHERE id = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        row = None  # marker table missing — fall through to the edges probe
    if row is not None:
        built = row["built"] if isinstance(row, sqlite3.Row) else row[0]
        if bool(built):
            return True
    # Safety net: a populated edges table means the graph exists.
    try:
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()
    except sqlite3.OperationalError:
        return False
    return bool(edge_count and edge_count[0] > 0)
