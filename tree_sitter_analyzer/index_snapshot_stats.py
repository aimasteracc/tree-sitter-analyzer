"""Bounded statistics collected from an acquired index snapshot."""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from .index_snapshot_schema import SNAPSHOT_SCHEMA_VERSION
from .index_snapshot_symbols import (
    fallback_symbol_counts,
    has_ordinary_symbol_projection,
    ordinary_edge_counts,
    ordinary_symbol_counts,
)
from .index_symbol_projection import symbol_projection_is_exact


def collect_snapshot_stats(
    conn: sqlite3.Connection, *, deadline: float | None = None
) -> dict[str, Any]:
    """Collect status fields within the owner capture's absolute deadline."""
    if deadline is None:
        deadline = time.monotonic() + 5.0
    if time.monotonic() >= deadline:
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")

    def expired() -> int:
        return int(time.monotonic() >= deadline)

    conn.set_progress_handler(expired, 1_000)
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        fts5_available = {"ast_symbols_fts", "ast_symbol_rows"}.issubset(tables)
        if has_ordinary_symbol_projection(conn, tables) and symbol_projection_is_exact(
            conn, deadline=deadline
        ):
            total_symbols, symbols_by_kind, symbols_by_language = (
                ordinary_symbol_counts(conn, deadline=deadline)
            )
        else:
            total_symbols, symbols_by_kind, symbols_by_language = (
                fallback_symbol_counts(conn, deadline=deadline)
            )
        total_edges, edges_by_kind = ordinary_edge_counts(conn, deadline=deadline)
        if time.monotonic() >= deadline:
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
        return {
            "total_files": int(
                conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
            ),
            "total_symbols": total_symbols,
            "total_edges": total_edges,
            "symbols_by_kind": symbols_by_kind,
            "symbols_by_language": symbols_by_language,
            "edges_by_kind": edges_by_kind,
            "fts5_available": fts5_available,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "db_size_bytes": page_size * page_count,
            "db_page_size": page_size,
            "db_page_count": page_count,
            "db_free_pages": free_pages,
            "db_free_bytes": free_pages * page_size,
            "db_auto_vacuum_mode": int(
                conn.execute("PRAGMA auto_vacuum").fetchone()[0]
            ),
        }
    except sqlite3.DatabaseError as exc:
        if time.monotonic() >= deadline or "interrupt" in str(exc).lower():
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE") from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)
