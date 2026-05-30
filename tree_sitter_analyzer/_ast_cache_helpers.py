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
