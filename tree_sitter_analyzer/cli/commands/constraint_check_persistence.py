"""SQLite write-through for the CLI architectural-constraint command."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def run_and_persist(
    db_path: Path,
    constraints: list[Any],
    *,
    persist: bool,
    evaluator: Callable[[list[Any], sqlite3.Connection], list[Any]],
    violations_ddl: Callable[[], str],
) -> tuple[list[Any], int]:
    """Evaluate one index and atomically replace persisted violations."""
    target = str(db_path) if persist else f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(target, uri=not persist)
    try:
        if persist:
            conn.execute(violations_ddl())
        try:
            edge_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM edges WHERE kind = 'calls'"
                ).fetchone()[0]
            )
        except sqlite3.OperationalError:
            if not persist:
                raise
            edge_count = 0
        if edge_count == 0:
            return [], 0
        try:
            violations = evaluator(constraints, conn)
        except RuntimeError as exc:
            if not persist or str(exc) == "CONSTRAINT_EVALUATION_CAPACITY":
                raise
            return [], edge_count
        except Exception:
            if not persist:
                raise
            return [], edge_count
        if not persist:
            return violations, edge_count
        conn.execute("DELETE FROM ast_constraint_violations")
        now = int(time.time())
        conn.executemany(
            """INSERT OR IGNORE INTO ast_constraint_violations
               (rule_id, caller_file, caller_name, caller_line,
                callee_name, callee_file, severity, detected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    v.rule_id,
                    v.caller_file,
                    v.caller_name,
                    v.caller_line,
                    v.callee_name,
                    v.callee_file,
                    v.severity,
                    v.detected_at or now,
                )
                for v in violations
            ],
        )
        conn.commit()
        return violations, edge_count
    finally:
        conn.close()
