"""Persistent constraint-violation row readers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ...constraints.parser import _compile_glob


def read_filtered_violations(
    db_path: Path,
    *,
    path_filter: str,
    min_severity_rank: int,
    severity_order: dict[str, int],
    ddl: str,
) -> list[dict[str, Any]]:
    """Read persisted violations with canonical Python glob filtering."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(ddl)
        cursor = conn.execute(
            """
            SELECT rule_id, caller_file, caller_name, caller_line,
                   callee_name, callee_file, severity, detected_at
            FROM ast_constraint_violations
            ORDER BY severity DESC, caller_file, caller_line
            """
        )
        path_re = _compile_glob(path_filter) if path_filter else None
        results: list[dict[str, Any]] = []
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
            if severity_order.get(severity, 0) < min_severity_rank:
                continue
            if path_re is not None and path_re.fullmatch(caller_file) is None:
                continue
            results.append(
                {
                    "rule_id": rule_id,
                    "caller_file": caller_file,
                    "caller_name": caller_name,
                    "caller_line": caller_line,
                    "callee_name": callee_name,
                    "callee_file": callee_file,
                    "severity": severity,
                    "detected_at": detected_at,
                }
            )
        return results
    finally:
        conn.close()
