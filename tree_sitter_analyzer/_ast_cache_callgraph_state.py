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
    """Return True iff this cache explicitly records a built call graph."""
    try:
        row = conn.execute(
            "SELECT built FROM ast_call_graph_state WHERE id = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    if row is None:
        return False
    if isinstance(row, sqlite3.Row):
        return bool(row["built"])
    return bool(row[0])
