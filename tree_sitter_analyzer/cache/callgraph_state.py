"""Persisted call-graph pipeline certification for AST cache readers."""

from __future__ import annotations

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

CALL_GRAPH_PIPELINE_VERSION = 2
_CALL_GRAPH_MARKER_DEADLINE_SECONDS = 5.0
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
    if not call_graph_edges_are_consistent(conn):
        raise sqlite3.OperationalError("CALL_GRAPH_DANGLING_RESOLUTION")
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
    if not exact_call_graph_marker(conn):
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


def exact_call_graph_marker(
    conn: sqlite3.Connection, *, deadline: float | None = None
) -> bool:
    """Check the exact marker with bounded SQL and scalar-only fetches."""
    expires_at = (
        time.monotonic() + _CALL_GRAPH_MARKER_DEADLINE_SECONDS
        if deadline is None
        else deadline
    )

    def expired() -> int:
        return int(time.monotonic() > expires_at)

    set_progress_handler = getattr(conn, "set_progress_handler", None)
    if callable(set_progress_handler):
        set_progress_handler(expired, 1_000)
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM ast_call_graph_state WHERE id IN (1, 2)"
        ).fetchone()
        if (
            time.monotonic() > expires_at
            or count_row is None
            or len(count_row) != 1
            or type(count_row[0]) is not int
            or count_row[0] != 1
        ):
            return False
        marker_row = conn.execute(
            "SELECT 1 FROM ast_call_graph_state "
            "WHERE id = 1 AND typeof(id) = 'integer' "
            "AND built = 1 AND typeof(built) = 'integer' "
            f"AND pipeline_version = {CALL_GRAPH_PIPELINE_VERSION} "
            "AND typeof(pipeline_version) = 'integer' LIMIT 1"
        ).fetchone()
        return bool(
            time.monotonic() <= expires_at
            and marker_row is not None
            and len(marker_row) == 1
            and type(marker_row[0]) is int
            and marker_row[0] == 1
        )
    except (sqlite3.DatabaseError, AttributeError, TypeError, ValueError):
        return False
    finally:
        if callable(set_progress_handler):
            set_progress_handler(None, 0)


def call_graph_edges_are_consistent(
    conn: sqlite3.Connection, *, deadline: float | None = None
) -> bool:
    """Reject resolved call targets that no longer have canonical rows."""
    expires_at = (
        time.monotonic() + _CALL_GRAPH_MARKER_DEADLINE_SECONDS
        if deadline is None
        else deadline
    )

    def expired() -> int:
        return int(time.monotonic() > expires_at)

    set_progress_handler = getattr(conn, "set_progress_handler", None)
    if callable(set_progress_handler):
        set_progress_handler(expired, 1_000)
    try:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('edges', 'ast_index', 'ast_symbol_rows')"
            ).fetchall()
        }
        if "edges" not in tables:
            return True
        if "ast_index" in tables:
            missing_file = conn.execute(
                "SELECT 1 FROM edges AS e WHERE e.kind = 'calls' "
                "AND e.callee_resolved_file <> '' AND NOT EXISTS ("
                "SELECT 1 FROM ast_index AS i "
                "WHERE i.file_path = e.callee_resolved_file) LIMIT 1"
            ).fetchone()
        else:
            missing_file = conn.execute(
                "SELECT 1 FROM edges WHERE kind = 'calls' "
                "AND callee_resolved_file <> '' LIMIT 1"
            ).fetchone()
        if missing_file is not None:
            return False
        if "ast_symbol_rows" in tables:
            missing_symbol = conn.execute(
                "SELECT 1 FROM edges AS e WHERE e.kind = 'calls' "
                "AND e.callee_symbol_id IS NOT NULL AND NOT EXISTS ("
                "SELECT 1 FROM ast_symbol_rows AS s "
                "WHERE s.id = e.callee_symbol_id) LIMIT 1"
            ).fetchone()
        else:
            missing_symbol = conn.execute(
                "SELECT 1 FROM edges WHERE kind = 'calls' "
                "AND callee_symbol_id IS NOT NULL LIMIT 1"
            ).fetchone()
        return bool(time.monotonic() <= expires_at and missing_symbol is None)
    except (sqlite3.DatabaseError, AttributeError, TypeError, ValueError):
        return False
    finally:
        if callable(set_progress_handler):
            set_progress_handler(None, 0)


def call_graph_marker_is_current(conn: sqlite3.Connection) -> bool:
    """Require both the exact marker and non-dangling resolved call targets."""
    deadline = time.monotonic() + _CALL_GRAPH_MARKER_DEADLINE_SECONDS
    return exact_call_graph_marker(
        conn, deadline=deadline
    ) and call_graph_edges_are_consistent(conn, deadline=deadline)


def call_graph_built(conn: sqlite3.Connection) -> bool:
    """Compatibility name for the shared exact marker predicate."""
    return call_graph_marker_is_current(conn)
