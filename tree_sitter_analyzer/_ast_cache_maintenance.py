"""SQLite storage maintenance helpers for the AST cache."""

from __future__ import annotations

import os
import sqlite3
from typing import Any

SQLITE_AUTO_VACUUM_NONE = 0
SQLITE_AUTO_VACUUM_INCREMENTAL = 2

# Default SQLite page size is 4096 bytes, so this catches ~2 MiB+ freelists.
DEFAULT_VACUUM_MIN_FREE_PAGES = 512


def _pragma_int(conn: sqlite3.Connection, pragma_name: str) -> int:
    row = conn.execute(f"PRAGMA {pragma_name}").fetchone()
    return int(row[0]) if row is not None else 0


def get_db_storage_stats(
    conn: sqlite3.Connection, db_path: str
) -> dict[str, int | str]:
    """Return exact SQLite file/page/free-list storage counters."""
    page_size = _pragma_int(conn, "page_size")
    page_count = _pragma_int(conn, "page_count")
    free_pages = _pragma_int(conn, "freelist_count")
    auto_vacuum_mode = _pragma_int(conn, "auto_vacuum")
    logical_size = page_size * page_count
    try:
        db_size_bytes = os.path.getsize(db_path)
    except OSError:
        db_size_bytes = logical_size
    return {
        "db_path": db_path,
        "db_size_bytes": int(db_size_bytes),
        "db_page_size": page_size,
        "db_page_count": page_count,
        "db_free_pages": free_pages,
        "db_free_bytes": free_pages * page_size,
        "db_auto_vacuum_mode": auto_vacuum_mode,
    }


def reclaim_storage_after_full_rebuild(
    conn: sqlite3.Connection,
    db_path: str,
    *,
    min_free_pages: int = DEFAULT_VACUUM_MIN_FREE_PAGES,
) -> dict[str, Any]:
    """Reclaim freelist pages after a force rebuild when the waste is material.

    Legacy cache DBs were created with ``auto_vacuum=NONE``. Incremental vacuum
    cannot reclaim those pages until SQLite rewrites the DB once, so the first
    qualifying legacy rebuild enables incremental mode and runs ``VACUUM``.
    Newer DBs in incremental mode use ``PRAGMA incremental_vacuum``.
    """
    before = get_db_storage_stats(conn, db_path)
    if int(before["db_free_pages"]) < min_free_pages:
        return {
            "action": "skipped",
            "reason": "below_threshold",
            "min_free_pages": min_free_pages,
            "before": before,
            "after": before,
        }

    try:
        conn.commit()
        free_pages = int(before["db_free_pages"])
        auto_vacuum_mode = int(before["db_auto_vacuum_mode"])
        if auto_vacuum_mode == SQLITE_AUTO_VACUUM_INCREMENTAL:
            conn.execute(f"PRAGMA incremental_vacuum({free_pages})")
            action = "incremental_vacuum"
        else:
            if auto_vacuum_mode == SQLITE_AUTO_VACUUM_NONE:
                conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
                action = "enable_incremental_vacuum"
            else:
                action = "vacuum"
            conn.execute("VACUUM")
        conn.commit()
        after = get_db_storage_stats(conn, db_path)
        return {
            "action": action,
            "min_free_pages": min_free_pages,
            "before": before,
            "after": after,
        }
    except sqlite3.DatabaseError as exc:
        return {
            "action": "error",
            "error": str(exc),
            "min_free_pages": min_free_pages,
            "before": before,
            "after": before,
        }
