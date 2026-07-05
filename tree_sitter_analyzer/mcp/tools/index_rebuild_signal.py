"""Shared read-side signal for AST cache full rebuild windows (#578)."""

from __future__ import annotations

import os
import sqlite3


def is_index_rebuilding(project_root: str | None) -> bool:
    """Return True when a full AST-cache rebuild marker is active.

    Best-effort and deliberately fail-open. A slow/locked marker read must not
    block navigation tools; missing the warning is preferable to turning every
    read into a lock-contention failure.
    """
    if not project_root:
        return False
    db_path = os.path.join(project_root, ".ast-cache", "index.db")
    if not os.path.exists(db_path):
        return False
    try:
        from tree_sitter_analyzer.cache.build_state import build_in_progress

        conn = sqlite3.connect(db_path, timeout=2)
        try:
            return bool(build_in_progress(conn))
        finally:
            conn.close()
    except Exception:
        return False


def rebuild_in_progress_next_step() -> str:
    return (
        "Full rebuild in progress — cached graph rows are transiently empty or "
        "partial. Do NOT start another index; retry this read shortly."
    )
