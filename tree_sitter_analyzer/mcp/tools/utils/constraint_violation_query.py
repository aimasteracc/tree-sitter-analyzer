#!/usr/bin/env python3
"""Read-side helper for ``ast_constraint_violations``.

Both ``safe_to_edit`` and ``analyze_change_impact`` need to query the
persisted violations table without re-running the evaluator. This
module owns the SQL so the two call sites can't drift apart.

Design choices:
    * All queries are read-only and short-circuit when the cache DB
      doesn't exist — both gate tools must remain usable on fresh repos.
    * Exception swallowing is intentional: a stale or partially-migrated
      DB should NOT take down the gate tool. We log at debug and return
      an empty list; the existing risk-scoring path still produces a
      valid response.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_BLOCKING_SEVERITIES: frozenset[str] = frozenset({"error"})
_WARNING_SEVERITIES: frozenset[str] = frozenset({"warn"})


def violations_for_files(
    project_root: str | None,
    file_paths: Iterable[str],
) -> list[dict[str, Any]]:
    """Return violation rows touching any of the given files.

    A row matches if its ``caller_file`` OR ``callee_file`` is in the
    provided iterable. Returns an empty list (never raises) when the
    cache DB or table is absent.

    Each row is a dict mirroring the table columns plus a ``factor``
    key set to ``constraint_violation`` for risk_factors compat — the
    safe_to_edit risk_factor list expects ``factor`` plus ``severity``,
    so callers can splice rows in directly.
    """
    if not project_root:
        return []
    db_path = Path(project_root) / ".ast-cache" / "index.db"
    if not db_path.is_file():
        return []

    files = list(dict.fromkeys(file_paths))  # dedupe, preserve order
    if not files:
        return []

    placeholders = ",".join(["?"] * len(files))
    sql = (
        "SELECT rule_id, caller_file, caller_name, caller_line, "
        "       callee_name, callee_file, severity, detected_at "
        "FROM ast_constraint_violations "
        f"WHERE caller_file IN ({placeholders}) "
        f"   OR callee_file IN ({placeholders}) "
        "ORDER BY severity DESC, caller_file, caller_line"
    )

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(sql, files + files)
        rows: list[dict[str, Any]] = []
        for row in cursor:
            (
                rule_id,
                caller_file,
                caller_name,
                caller_line,
                callee_name,
                callee_file,
                severity,
                detected_at,
            ) = row
            rows.append(
                {
                    "rule_id": rule_id,
                    "caller_file": caller_file,
                    "caller_name": caller_name,
                    "caller_line": caller_line,
                    "callee_name": callee_name,
                    "callee_file": callee_file,
                    "severity": severity,
                    "detected_at": detected_at,
                    # risk_factors shape (per Coder-T3 spec gap #3):
                    # safe_to_edit's existing risk_factors entries use
                    # the ``factor`` key. We splice rows in directly,
                    # so embed it here.
                    "factor": "constraint_violation",
                }
            )
        return rows
    except sqlite3.OperationalError as exc:
        # Table missing / cache schema mismatch. Log + degrade.
        logger.debug("constraint violation query failed: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def verdict_from_violations(rows: list[dict[str, Any]]) -> str | None:
    """Return the verdict implied by a violations list.

    Returns ``None`` when the rows do not imply any verdict escalation
    (no rows, or only info-severity). Callers should fall back to the
    existing verdict when this returns None.
    """
    if any(r.get("severity") in _BLOCKING_SEVERITIES for r in rows):
        return "UNSAFE"
    if any(r.get("severity") in _WARNING_SEVERITIES for r in rows):
        return "CAUTION"
    return None


def constraint_risk_factor(row: dict[str, Any]) -> dict[str, str]:
    """Render one violation row as a safe_to_edit risk_factor entry.

    Shape contract: must include the ``factor`` key set to
    ``constraint_violation`` so existing risk_factors consumers don't
    branch on shape, plus ``severity``, ``rule_id``, and a concise
    ``detail`` field for the agent.
    """
    return {
        "factor": "constraint_violation",
        "severity": str(row.get("severity", "")),
        "rule_id": str(row.get("rule_id", "")),
        "detail": (
            f"{row.get('caller_file', '')}:{row.get('caller_line', 0)} "
            f"-> {row.get('callee_file', '') or row.get('callee_name', '')} "
            f"violates {row.get('rule_id', '')}"
        ),
    }
