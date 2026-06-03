#!/usr/bin/env python3
"""Edge-stream evaluator for architectural constraints.

Given a list of loaded :class:`Constraint` rules and an open SQLite
connection holding the unified ``edges`` table, yields one
:class:`Violation` per offending CALLS edge.

Design contract:

* The callee's resolved file (``metadata.callee_resolved_file`` on the
  ``edges`` row) is preferred when present and populated, so we benefit
  from import-aware resolution. Edges where it is empty fall back to
  ``file_path`` (the caller's file). Edges with no callee location at all
  are skipped — they would generate false positives on unresolved calls.

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
from collections.abc import Iterator

from .parser import _CompiledConstraint, compile_constraints
from .schema import Constraint, Violation

logger = logging.getLogger(__name__)


def evaluate(
    constraints: list[Constraint],
    db_conn: sqlite3.Connection,
) -> list[Violation]:
    """Evaluate constraints against the unified ``edges`` table (CALLS rows).

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
    """Build the per-DB SELECT statement over the unified ``edges`` table.

    CALLS edges now live in ``edges`` with every resolution scalar promoted to
    a real column (B1.3). The callee file prefers ``callee_resolved_file`` and
    falls back to the caller's ``file_path`` when the call was never cross-file
    resolved — preserving the legacy ``CASE WHEN callee_resolved_file != ''``
    behaviour.

    The ``db_conn`` argument is retained for signature compatibility.
    """
    callee_expr = (
        "CASE WHEN callee_resolved_file != '' "
        "THEN callee_resolved_file "
        "ELSE file_path END"
    )
    return (
        "SELECT caller_name, file_path AS caller_file, "
        "caller_line, callee_name, "
        f"{callee_expr} AS callee_file "  # nosec B608 — callee_expr is constructed from internal constants only
        "FROM edges WHERE kind = 'calls'"
    )
