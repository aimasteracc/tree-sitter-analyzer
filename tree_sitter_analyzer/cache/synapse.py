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


def _resolve_indexed_callee(
    conn: sqlite3.Connection, row: Any, ctx: Any, resolve: Any
) -> Any:
    """利用持久化定义行补足 self/cls 的类身份，不把同名调用者交给名字猜测。"""
    caller_file = row["caller_file"]
    name = row["callee_name"]
    if ctx.file_languages.get(caller_file) == "python" and row["callee_full"] in (
        f"self.{name}",
        f"cls.{name}",
    ):
        callers = conn.execute(
            "SELECT id FROM ast_symbol_rows WHERE file_path=? AND name=? AND line=? "
            "AND kind IN ('function','method') LIMIT 2",
            (caller_file, row["caller_name"], row["caller_line"]),
        ).fetchall()
        if len(callers) == 1:
            owners = [
                methods
                for methods in ctx.file_class_methods.get(caller_file, {}).values()
                if methods.get(row["caller_name"]) == callers[0][0]
            ]
            if len(owners) == 1:
                from ..synapse_resolver import ResolvedCallee

                target = owners[0].get(name)
                return (
                    ResolvedCallee(target, "local", caller_file)
                    if target is not None
                    else ResolvedCallee(None, "unknown", "")
                )
    return resolve(name, caller_file, ctx, row["callee_full"], row["caller_name"])


def resolve_call_edges_for_file(
    cache: Any,
    conn: sqlite3.Connection,
    rel_path: str,
) -> None:
    """Resolve Synapse call-edge columns for ``rel_path`` (skipped when disabled)."""
    try:
        from ..synapse_resolver import (
            build_resolver_context,
            is_enabled,
            resolve_callee,
        )
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
            "SELECT id, caller_name, caller_line, file_path AS caller_file, callee_name, "
            "callee_full FROM edges WHERE kind = 'calls' AND file_path = ?",
            (rel_path,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("call_edge select failed for %s: %s", rel_path, exc)
        return
    for row in rows:
        try:
            resolved = _resolve_indexed_callee(conn, row, ctx, resolve_callee)
        except Exception as exc:  # pragma: no cover
            logger.debug("resolve_callee crashed on %s: %s", row["callee_name"], exc)
            continue
        try:
            conn.execute(
                "UPDATE edges "
                "SET callee_symbol_id = ?, callee_resolution = ?, "
                "callee_resolved_file = ? WHERE id = ?",
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
    """Re-resolve unresolved call edges; return None only on indeterminate failure."""
    empty_stats = {"total": 0, "resolved": 0, "unchanged": 0, "errors": 0}
    try:
        from ..synapse_resolver import (
            build_resolver_context,
            is_enabled,
            resolve_callee,
        )
    except Exception as exc:
        logger.debug("synapse_resolver import failed: %s", exc)
        return None
    if not is_enabled():
        return empty_stats
    try:
        # Re-scan only edges that are still genuinely unresolved. ``external``
        # and ``stdlib`` are *terminal* resolutions (target lives outside the
        # project, no resolved_file by design) — re-selecting them on every
        # backfill is the unknown-> rescan loop B3 is meant to break.
        rows = conn.execute(
            "SELECT id, caller_name, caller_line, file_path AS caller_file, callee_name, "
            "callee_full FROM edges "
            "WHERE kind = 'calls' AND ("
            "callee_resolution = 'unknown' "
            "OR (callee_resolved_file = '' "
            "    AND callee_resolution NOT IN ('external', 'stdlib')))"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("synapse backfill select failed: %s", exc)
        return None
    if not rows:
        return empty_stats
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
            result = _resolve_indexed_callee(conn, row, ctx, resolve_callee)
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
                "UPDATE edges "
                "SET callee_symbol_id = ?, callee_resolution = ?, "
                "callee_resolved_file = ? WHERE id = ?",
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
