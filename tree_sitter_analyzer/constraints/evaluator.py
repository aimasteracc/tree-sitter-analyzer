#!/usr/bin/env python3
"""Edge-stream evaluator for architectural constraints.

Given a list of loaded :class:`Constraint` rules and an open
``ast_call_edges`` SQLite connection, yields one :class:`Violation`
per offending edge.

Design contract:

* T1's ``callee_resolved_file`` column is preferred when present and
  populated, so we benefit from import-aware resolution. Edges where
  the column is empty or absent fall back to ``file_path`` (the legacy
  callee location column). Edges with no callee location at all are
  skipped — they would generate false positives on unresolved calls.

* Performance is load-bearing: this is called on every change_impact /
  safe_to_edit invocation. We compile globs once, batch the SELECT into
  a single streaming cursor, and do O(rules) regex matches per edge.

* The function is pure: it never writes to the DB. The MCP tool layer
  owns the write-through into ``ast_constraint_violations``.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Iterator

from .parser import _CompiledConstraint, compile_constraints
from .schema import Constraint, Violation

logger = logging.getLogger(__name__)


def evaluate(
    constraints: list[Constraint],
    db_conn: sqlite3.Connection,
) -> list[Violation]:
    """Evaluate constraints against the ``ast_call_edges`` table.

    Returns a list (materialised; downstream code wants a length-check
    and the row count is bounded by the rule × edge cross-product, which
    in practice is small even on large repos).

    Edge-skip rules:
        * No callee file at all → skip (unresolved cross-file call).
        * Exception list matches the caller → skip (whitelisted seam).

    Yields a :class:`Violation` for every (rule, edge) pair where the
    caller matches ``from_glob``, the callee file matches ``to_glob``,
    and no exception applies.
    """
    if not constraints:
        return []
    compiled = compile_constraints(constraints)
    if not compiled:
        return []
    detected_at = int(time.time())
    return list(_iter_violations(compiled, db_conn, detected_at))


def _iter_violations(
    compiled: list[_CompiledConstraint],
    db_conn: sqlite3.Connection,
    detected_at: int,
) -> Iterator[Violation]:
    """Stream edges from the DB and yield matching violations.

    Split out so the public ``evaluate()`` can wrap it in ``list(...)``
    without paying a generator-overhead penalty inside the hot loop.
    """
    select_sql = _build_select_sql(db_conn)
    cursor = db_conn.execute(select_sql)
    for row in cursor:
        caller_name, caller_file, caller_line, callee_name, callee_file = row
        if not callee_file:
            # Unresolved cross-file call — MVP skips it to avoid noisy
            # false positives on dynamic / external symbols.
            continue
        for cc in compiled:
            if cc.from_re.fullmatch(caller_file) is None:
                continue
            if cc.to_re.fullmatch(callee_file) is None:
                continue
            if _is_excepted(caller_file, cc):
                continue
            yield Violation(
                rule_id=cc.constraint.id,
                caller_file=caller_file,
                caller_name=caller_name or "",
                caller_line=int(caller_line or 0),
                callee_name=callee_name or "",
                callee_file=callee_file,
                severity=cc.constraint.severity,
                detected_at=detected_at,
            )


def _is_excepted(caller_file: str, compiled: _CompiledConstraint) -> bool:
    """Return True when the caller is on the rule's exception list.

    Exceptions are matched as full-path globs (same model as ``from``/
    ``to``), so they participate in ``**`` semantics for free.
    """
    for exc_re in compiled.exception_res:
        if exc_re.fullmatch(caller_file) is not None:
            return True
    return False


def _build_select_sql(db_conn: sqlite3.Connection) -> str:
    """Build the per-DB SELECT statement.

    Prefers ``callee_resolved_file`` when the column exists on
    ``ast_call_edges`` (T1's Synapse migration) and falls back to
    ``file_path`` when it does not (test-only minimal schema or
    pre-T1 caches that never indexed cross-file resolution).

    The COALESCE between the two columns is also defensive against a
    partially-migrated DB where the column exists but is empty for some
    rows (T1's resolver may not have run on legacy data yet).
    """
    callee_expr = "file_path"
    try:
        columns = {
            row[1]
            for row in db_conn.execute(
                "PRAGMA table_info(ast_call_edges)"
            ).fetchall()
        }
    except sqlite3.OperationalError:
        columns = set()

    if "callee_resolved_file" in columns:
        # Prefer the resolved column, but fall back to file_path so
        # legacy unresolved rows still contribute.
        callee_expr = (
            "CASE WHEN callee_resolved_file != '' "
            "THEN callee_resolved_file ELSE file_path END"
        )
    return (
        "SELECT caller_name, caller_file, caller_line, callee_name, "
        f"{callee_expr} AS callee_file "
        "FROM ast_call_edges"
    )
