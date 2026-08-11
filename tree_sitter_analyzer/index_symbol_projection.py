"""Bounded SQL verification for the ordinary symbol projection."""

from __future__ import annotations

import sqlite3
import time


def projection_schema_columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    """Read one small, trusted projection schema under the caller's deadline."""
    return tuple(str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})"))


def index_content_hash_sql(conn: sqlite3.Connection) -> str:
    """Return the generation expression, supporting pre-hash test fixtures."""
    try:
        conn.execute("SELECT content_hash FROM ast_index LIMIT 0")
    except sqlite3.OperationalError as exc:
        if "no such column" not in str(exc).lower():
            raise
        return "''"
    return "source.content_hash"


def delete_projection_state_if_present(conn: sqlite3.Connection, rel_path: str) -> None:
    """Delete state while tolerating pre-projection compatibility fixtures."""
    try:
        conn.execute(
            "DELETE FROM ast_symbol_projection_state WHERE file_path = ?", (rel_path,)
        )
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise


def upsert_symbol_projection_state(conn: sqlite3.Connection, rel_path: str) -> None:
    """Bind ordinary rows to the canonical ast_index generation when installed."""
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='ast_symbol_projection_state'"
    ).fetchone()
    if table is None:
        return
    source = conn.execute(
        "SELECT content_hash FROM ast_index WHERE file_path = ?", (rel_path,)
    ).fetchone()
    if source is None:
        conn.execute(
            "DELETE FROM ast_symbol_projection_state WHERE file_path = ?", (rel_path,)
        )
        return
    count = conn.execute(
        "SELECT COUNT(*) FROM ast_symbol_rows WHERE file_path = ?", (rel_path,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO ast_symbol_projection_state "
        "(file_path, content_hash, symbol_count) VALUES (?, ?, ?) "
        "ON CONFLICT(file_path) DO UPDATE SET "
        "content_hash=excluded.content_hash, symbol_count=excluded.symbol_count",
        (rel_path, source[0], count),
    )


def symbol_projection_is_exact(
    conn: sqlite3.Connection, max_symbols: int = 2_000_000
) -> bool:
    """Boundedly verify the global marker and per-file generation evidence."""
    deadline = time.monotonic() + 5.0

    def expired() -> int:
        return int(time.monotonic() > deadline)

    conn.set_progress_handler(expired, 1_000)
    try:
        conn.execute("SELECT file_path, symbols_json FROM ast_index LIMIT 0")
        row_columns = set(projection_schema_columns(conn, "ast_symbol_rows"))
        state_columns = projection_schema_columns(conn, "ast_symbol_projection_state")
        metadata_columns = projection_schema_columns(conn, "ast_cache_metadata")
        if not {"file_path", "name", "kind", "language", "line", "end_line"}.issubset(
            row_columns
        ):
            return False
        if state_columns != ("file_path", "content_hash", "symbol_count"):
            return False
        if metadata_columns != ("key", "value"):
            return False
        marker = conn.execute(
            "SELECT COUNT(*), "
            "COUNT(*) FILTER (WHERE typeof(key)='text' AND typeof(value)='text' "
            "AND value='complete') FROM ast_cache_metadata "
            "WHERE key='symbol_rows_projection_v1'"
        ).fetchone()
        if (
            marker is None
            or any(type(value) is not int for value in marker)
            or tuple(marker) != (1, 1)
        ):
            return False
        hash_sql = index_content_hash_sql(conn)
        checks = (
            "SELECT 1 FROM ast_index AS source LEFT JOIN "
            "ast_symbol_projection_state AS state ON state.file_path=source.file_path "
            f"WHERE typeof(source.file_path)!='text' OR state.file_path IS NULL "
            f"OR state.content_hash IS NOT {hash_sql} LIMIT 1",
            "SELECT 1 FROM ast_symbol_projection_state AS state LEFT JOIN "
            "ast_index AS source ON source.file_path=state.file_path "
            "WHERE source.file_path IS NULL LIMIT 1",
            "SELECT 1 FROM ast_symbol_projection_state AS state LEFT JOIN "
            "(SELECT file_path, COUNT(*) AS actual FROM ast_symbol_rows "
            "GROUP BY file_path) AS rows ON rows.file_path=state.file_path "
            "WHERE typeof(state.file_path)!='text' OR "
            "typeof(state.content_hash)!='text' OR "
            "typeof(state.symbol_count)!='integer' OR state.symbol_count < 0 "
            f"OR state.symbol_count > {max_symbols} "
            "OR state.symbol_count != COALESCE(rows.actual, 0) LIMIT 1",
            "SELECT 1 FROM ast_symbol_rows AS rows LEFT JOIN "
            "ast_symbol_projection_state AS state ON state.file_path=rows.file_path "
            "WHERE state.file_path IS NULL OR typeof(rows.file_path)!='text' LIMIT 1",
        )
        return all(conn.execute(query).fetchone() is None for query in checks)
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.set_progress_handler(None, 0)
