"""Synapse call-edge resolution helpers for ASTCache.

Functions extracted from ast_cache.py to reduce its line count.
ASTCache delegates to these via thin wrapper methods.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def resolve_call_edges_for_file(
    cache: Any,
    conn: sqlite3.Connection,
    rel_path: str,
) -> None:
    """Resolve Synapse call-edge columns for ``rel_path`` (skipped when disabled)."""
    try:
        from .synapse_resolver import build_resolver_context, is_enabled, resolve_callee
    except Exception as exc:  # pragma: no cover
        logger.debug("synapse_resolver import failed: %s", exc)
        return
    if not is_enabled():
        return
    try:
        ctx = build_resolver_context(cache)
    except Exception as exc:  # pragma: no cover
        logger.debug("build_resolver_context failed: %s", exc)
        return
    try:
        rows = conn.execute(
            "SELECT id, caller_name, caller_file, callee_name "
            "FROM ast_call_edges WHERE file_path = ?",
            (rel_path,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("call_edge select failed for %s: %s", rel_path, exc)
        return
    for row in rows:
        try:
            resolved = resolve_callee(row["callee_name"], row["caller_file"], ctx)
        except Exception as exc:  # pragma: no cover
            logger.debug("resolve_callee crashed on %s: %s", row["callee_name"], exc)
            continue
        try:
            conn.execute(
                "UPDATE ast_call_edges "
                "SET callee_symbol_id = ?, callee_resolution = ?, callee_resolved_file = ? "
                "WHERE id = ?",
                (
                    resolved.callee_symbol_id,
                    resolved.resolution,
                    resolved.resolved_file,
                    row["id"],
                ),
            )
        except sqlite3.OperationalError as exc:
            logger.debug("call_edge update failed for id=%s: %s", row["id"], exc)
            return


def run_synapse_backfill(cache: Any, conn: sqlite3.Connection) -> dict[str, int] | None:
    """Re-resolve every unresolved call edge. Returns stats dict or None."""
    try:
        from .synapse_resolver import build_resolver_context, is_enabled, resolve_callee
    except Exception as exc:
        logger.debug("synapse_resolver import failed: %s", exc)
        return None
    if not is_enabled():
        return None
    try:
        rows = conn.execute(
            "SELECT id, caller_name, caller_file, callee_name FROM ast_call_edges "
            "WHERE callee_resolution = 'unknown' OR callee_resolved_file = ''"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("synapse backfill select failed: %s", exc)
        return None
    if not rows:
        return None
    try:
        ctx = build_resolver_context(cache)
    except Exception as exc:
        logger.debug("build_resolver_context failed in backfill: %s", exc)
        return None
    total = len(rows)
    resolved = unchanged = errors = 0
    updates: list[tuple[Any, str, str, int]] = []
    for row in rows:
        try:
            result = resolve_callee(row["callee_name"], row["caller_file"], ctx)
        except Exception as exc:
            logger.debug("resolve_callee failed in backfill: %s", exc)
            errors += 1
            continue
        if result.resolution == "unknown" and not result.resolved_file:
            unchanged += 1
            continue
        updates.append(
            (
                result.callee_symbol_id,
                result.resolution,
                result.resolved_file,
                row["id"],
            )
        )
    if updates:
        try:
            conn.executemany(
                "UPDATE ast_call_edges "
                "SET callee_symbol_id = ?, callee_resolution = ?, callee_resolved_file = ? "
                "WHERE id = ?",
                updates,
            )
            resolved += len(updates)
        except sqlite3.OperationalError as exc:
            logger.debug("synapse backfill update failed: %s", exc)
            errors += len(updates)
    try:
        conn.commit()
    except sqlite3.OperationalError:
        pass
    return {
        "total": total,
        "resolved": resolved,
        "unchanged": unchanged,
        "errors": errors,
    }
