"""Pure module-level helpers for ASTCache.

Extracted from ast_cache.py to reduce its line count.
These functions have no dependency on ASTCache instance state.
"""

from __future__ import annotations

import os
from typing import Any


def _build_function_entry(
    sym: dict[str, Any], file_path: str, language: str
) -> dict[str, Any]:
    """Build one function-entry dict from a symbol row."""
    entry: dict[str, Any] = {
        "name": sym["name"],
        "file": file_path,
        "line": sym.get("line", 0),
        "end_line": sym.get("end_line", 0),
        "language": language,
        "params": sym.get("params", ""),
    }
    if sym.get("class"):
        entry["class"] = sym["class"]
    return entry


def _project_index_activation_enabled(include_activation: bool | None) -> bool:
    """Return whether project-wide indexing should compute git activation."""
    if include_activation is not None:
        return bool(include_activation)
    value = os.environ.get("TSA_INDEX_ACTIVATION", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _process_one_index_result(
    r: dict[str, Any],
    stats: dict[str, Any],
    insert_fn: Any,
    indexed_at: str,
    activation_enabled: bool,
) -> None:
    """Apply one worker result dict to stats and DB (in-place)."""
    if r["status"] in ("io_error", "parse_failed"):
        stats["errors"] += 1
        stats["files"].append(
            {"file": r["rel_path"], "status": "error", "reason": r["reason"]}
        )
        return
    insert_fn(r, indexed_at, include_activation=activation_enabled)
    stats["indexed"] += 1
    stats["files"].append(
        {
            "file": r["rel_path"],
            "status": "indexed",
            "symbols": r["symbols_count"],
            "content_hash": r["content_hash"][:16],
        }
    )


def _make_error_entry(rel_path: str, reason: str) -> dict[str, Any]:
    return {"file": rel_path, "status": "error", "reason": reason}


# A4: write the index in bounded transactions instead of one giant BEGIN…COMMIT.
# On large repos (e.g. 7.9k Java files / 884k edges) accumulating every insert in
# a single transaction pushed RSS high enough to trigger OOM/swap and the apparent
# "stall". Committing every _COMMIT_BATCH_SIZE files caps the dirty-page set.
_COMMIT_BATCH_SIZE = 500


def _commit_index_results(
    conn: Any,
    results: list[dict[str, Any]],
    stats: dict[str, Any],
    insert_fn: Any,
    indexed_at: str,
    activation_enabled: bool,
    batch_size: int = _COMMIT_BATCH_SIZE,
) -> None:
    """Commit worker results to the DB in bounded-size transactions.

    Iterates *results*, accumulates into *stats* via ``_process_one_index_result``,
    committing every *batch_size* files so the dirty-page set (and RSS) stays
    bounded on large repos. A failure rolls back only the current batch and
    re-raises; previously committed batches persist.
    """
    pending = 0
    conn.execute("BEGIN")
    try:
        for r in results:
            _process_one_index_result(
                r, stats, insert_fn, indexed_at, activation_enabled
            )
            pending += 1
            if pending >= batch_size:
                conn.execute("COMMIT")
                pending = 0
                conn.execute("BEGIN")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
