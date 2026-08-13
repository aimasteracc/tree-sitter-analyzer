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

* Import-reachability guard (#780): a resolved callee file is only flagged
  as a constraint violation when the caller actually imports the callee's
  module.  Without this guard, bare-name resolutions (e.g. ``update`` or
  ``execute``) can be matched to same-named methods in forbidden modules
  even when the caller has no import relationship to those modules.  When
  ``ast_imports`` is absent (e.g. test fixtures) the guard is skipped and
  the evaluator falls back to the pre-guard behaviour.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable, Iterator

from .evaluator_bounds import MAX_MATERIALIZED_ITEMS, materialize_bounded
from .evaluator_deduplication import claim_violation
from .evaluator_import_resolution import (
    _build_import_index,
    _callee_is_imported,
)
from .evaluator_selection import (
    _MAX_SQL_PREFIX_FILTERS as _MAX_SQL_PREFIX_FILTERS,
)
from .evaluator_selection import (
    _build_select_query,
)
from .parser import _CompiledConstraint, compile_constraints
from .schema import Constraint, Violation

logger = logging.getLogger(__name__)

_MAX_MATERIALIZED_ITEMS = MAX_MATERIALIZED_ITEMS


def evaluate(
    constraints: list[Constraint],
    db_conn: sqlite3.Connection,
    *,
    scope_predicate: Callable[[str, str], bool] | None = None,
    check_callback: Callable[[], None] | None = None,
    capacity: int = _MAX_MATERIALIZED_ITEMS,
) -> list[Violation]:
    """Evaluate constraints against the unified ``edges`` table (CALLS rows).

    Returns a list (materialised; downstream code wants a length-check
    and the row count is bounded by the rule × edge cross-product, which
    in practice is small even on large repos).

    Edge-skip rules:
        * No callee file at all → skip (unresolved cross-file call).
        * Exception list matches the caller → skip (whitelisted seam).
        * Callee not reachable via caller's imports → skip (phantom
          bare-name resolution; see #780).

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
    return materialize_bounded(
        _iter_violations(
            compiled,
            db_conn,
            detected_at,
            scope_predicate=scope_predicate,
            check_callback=check_callback,
            capacity=capacity,
        ),
        capacity,
        check_callback,
    )


def _iter_violations(
    compiled: list[_CompiledConstraint],
    db_conn: sqlite3.Connection,
    detected_at: int,
    *,
    scope_predicate: Callable[[str, str], bool] | None = None,
    check_callback: Callable[[], None] | None = None,
    capacity: int = _MAX_MATERIALIZED_ITEMS,
) -> Iterator[Violation]:
    """Stream edges from the DB and yield matching violations.

    Split out so the public ``evaluate()`` can wrap it in ``list(...)``
    without paying a generator-overhead penalty inside the hot loop.

    Deduplication: the ``edges`` table can contain multiple rows for the
    same logical call site (same caller_file + caller_line + callee_name)
    with different ``callee_resolved_file`` values — e.g., when a call is
    re-indexed by two resolution passes.  Both rows can match the same
    constraint and produce ``Violation`` objects with identical PRIMARY
    KEY ``(rule_id, caller_file, caller_line, callee_name)``.  Inserting
    both into ``ast_constraint_violations`` would crash with
    ``UNIQUE constraint failed`` (#544).

    We keep a ``seen`` set and skip any PK tuple already emitted.  The
    first occurrence wins (edge ordering from the DB is stable within a
    transaction; the choice of which ``callee_file`` survives is arbitrary
    but deterministic and the PK is the same violation regardless).
    """
    seen: set[tuple[str, str, int, str]] = set()
    import_index = _build_import_index(
        db_conn, check_callback=check_callback, capacity=capacity
    )
    select_sql, select_params = _build_select_query(db_conn, compiled)
    cursor = db_conn.execute(select_sql, select_params)
    for row in cursor:
        if check_callback is not None:
            check_callback()
        caller_name, caller_file, caller_line, callee_name, callee_file = row
        if not callee_file:
            # Unresolved cross-file call — MVP skips it to avoid noisy
            # false positives on dynamic / external symbols.
            continue
        if scope_predicate is not None and not scope_predicate(
            caller_file, callee_file
        ):
            # Scope is part of edge eligibility. Applying it before PK
            # deduplication prevents an out-of-scope resolution candidate from
            # hiding an in-scope candidate for the same logical call site.
            continue
        for cc in compiled:
            if check_callback is not None:
                check_callback()
            if cc.from_prefix and not caller_file.startswith(cc.from_prefix):
                continue
            if cc.from_re.fullmatch(caller_file) is None:
                continue
            if cc.to_prefix and not callee_file.startswith(cc.to_prefix):
                continue
            if cc.to_re.fullmatch(callee_file) is None:
                continue
            if _is_excepted(caller_file, cc):
                continue
            # Import-reachability guard (#780): skip phantom resolutions
            # where the callee lives in a forbidden module the caller never
            # actually imports. Same-file calls always pass this check.
            if (
                import_index is not None
                and caller_file != callee_file
                and not _callee_is_imported(caller_file, callee_file, import_index)
            ):
                continue
            if not claim_violation(
                seen,
                cc.constraint.id,
                caller_file,
                int(caller_line or 0),
                callee_name or "",
            ):
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
