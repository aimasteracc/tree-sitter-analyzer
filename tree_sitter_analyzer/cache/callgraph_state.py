"""Persisted call-graph pipeline certification for AST cache readers."""

from __future__ import annotations

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

CALL_GRAPH_PIPELINE_VERSION = 2
_BUILT_MARKER_ID = 1
_EXPLICITLY_INCOMPLETE_ID = 2
_CREATE_DDL = (
    "CREATE TABLE IF NOT EXISTS ast_call_graph_state ("
    "id INTEGER PRIMARY KEY, "
    "built INTEGER NOT NULL, "
    "built_at REAL NOT NULL, "
    "pipeline_version INTEGER NOT NULL DEFAULT 0)"
)


def _ensure_state_schema(conn: sqlite3.Connection) -> None:
    """Create the writer schema and downgrade legacy markers to version zero."""
    conn.execute(_CREATE_DDL)
    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(ast_call_graph_state)")
    }
    if "pipeline_version" not in columns:
        try:
            conn.execute(
                "ALTER TABLE ast_call_graph_state "
                "ADD COLUMN pipeline_version INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            # Another writer may have won the migration race.
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(ast_call_graph_state)")
            }
            if "pipeline_version" not in columns:
                raise


def mark_call_graph_built(conn: sqlite3.Connection) -> None:
    """Best-effort wrapper for authoritative pipeline certifiers."""
    try:
        mark_call_graph_built_strict(conn)
    except sqlite3.OperationalError:
        logger.debug("could not mark call-graph-built", exc_info=True)


def mark_call_graph_built_strict(conn: sqlite3.Connection) -> None:
    """Persist and verify the exact current pipeline marker."""
    _ensure_state_schema(conn)
    conn.execute(
        "INSERT INTO ast_call_graph_state (id, built, built_at, pipeline_version) "
        "VALUES (1, 1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "built = excluded.built, built_at = excluded.built_at, "
        "pipeline_version = excluded.pipeline_version",
        (time.time(), CALL_GRAPH_PIPELINE_VERSION),
    )
    conn.execute(
        "DELETE FROM ast_call_graph_state WHERE id = ?",
        (_EXPLICITLY_INCOMPLETE_ID,),
    )
    rows = conn.execute(
        "SELECT id, built, pipeline_version FROM ast_call_graph_state "
        "WHERE id IN (?, ?) ORDER BY id",
        (_BUILT_MARKER_ID, _EXPLICITLY_INCOMPLETE_ID),
    ).fetchall()
    exact = [tuple(row) for row in rows]
    if not (
        len(exact) == 1
        and all(type(value) is int for value in exact[0])
        and exact[0] == (_BUILT_MARKER_ID, 1, CALL_GRAPH_PIPELINE_VERSION)
    ):
        raise sqlite3.OperationalError("CALL_GRAPH_MARKER_VERIFY_FAILED")
    conn.commit()


def clear_call_graph_built(conn: sqlite3.Connection) -> None:
    """Best-effort invalidation of pipeline certification."""
    try:
        clear_call_graph_built_strict(conn)
    except sqlite3.OperationalError:
        logger.debug("could not clear call-graph-built", exc_info=True)


def clear_call_graph_built_strict(conn: sqlite3.Connection) -> None:
    """Write an explicit incomplete marker at pipeline version zero."""
    _ensure_state_schema(conn)
    now = time.time()
    conn.execute(
        "INSERT INTO ast_call_graph_state (id, built, built_at, pipeline_version) "
        "VALUES (1, 0, ?, 0) "
        "ON CONFLICT(id) DO UPDATE SET built = excluded.built, "
        "built_at = excluded.built_at, pipeline_version = 0",
        (now,),
    )
    conn.execute(
        "INSERT INTO ast_call_graph_state (id, built, built_at, pipeline_version) "
        "VALUES (?, 0, ?, 0) "
        "ON CONFLICT(id) DO UPDATE SET built = excluded.built, "
        "built_at = excluded.built_at, pipeline_version = 0",
        (_EXPLICITLY_INCOMPLETE_ID, now),
    )
    conn.commit()


def call_graph_built(conn: sqlite3.Connection) -> bool:
    """Return True only for the singleton current-pipeline certification."""
    try:
        rows = conn.execute(
            "SELECT id, built, pipeline_version FROM ast_call_graph_state "
            "WHERE id IN (?, ?) ORDER BY id",
            (_BUILT_MARKER_ID, _EXPLICITLY_INCOMPLETE_ID),
        ).fetchall()
    except sqlite3.DatabaseError:
        return False
    exact = [tuple(row) for row in rows]
    return bool(
        len(exact) == 1
        and all(type(value) is int for value in exact[0])
        and exact[0] == (_BUILT_MARKER_ID, 1, CALL_GRAPH_PIPELINE_VERSION)
    )
