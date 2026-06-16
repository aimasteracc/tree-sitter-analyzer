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
    return list(_iter_violations(compiled, db_conn, detected_at))


def _iter_violations(
    compiled: list[_CompiledConstraint],
    db_conn: sqlite3.Connection,
    detected_at: int,
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
    import_index = _build_import_index(db_conn)
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
            # Import-reachability guard (#780): skip phantom resolutions
            # where the callee lives in a forbidden module the caller never
            # actually imports. Same-file calls always pass this check.
            if (
                import_index is not None
                and caller_file != callee_file
                and not _callee_is_imported(caller_file, callee_file, import_index)
            ):
                continue
            pk = (
                cc.constraint.id,
                caller_file,
                int(caller_line or 0),
                callee_name or "",
            )
            if pk in seen:
                continue
            seen.add(pk)
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


def _build_import_index(
    db_conn: sqlite3.Connection,
) -> dict[str, set[str]] | None:
    """Build a lookup of {file_path: set(module_path_suffixes)} from ast_imports.

    Returns ``None`` when the ``ast_imports`` table is absent (e.g. in
    test fixtures that only populate the ``edges`` table) so callers can
    skip the import-reachability guard and fall back to pre-guard behaviour.

    The set stored per file is the union of the raw module_path and its
    terminal component (the basename after the last ``.`` or ``/``).
    This handles both absolute imports (``tree_sitter_analyzer.mcp.x``)
    and relative imports (``.x``) with a single membership test.
    """
    try:
        cursor = db_conn.execute("SELECT file_path, module_path FROM ast_imports")
    except sqlite3.OperationalError:
        # Table absent (test fixture, fresh DB) — degrade gracefully.
        return None

    index: dict[str, set[str]] = {}
    for file_path, module_path in cursor:
        if not file_path or not module_path:
            continue
        entry = index.setdefault(file_path, set())
        # Store full module_path (handles absolute imports).
        entry.add(module_path)
        # Also store the terminal component so relative imports like
        # '.file_health_blocks' and absolute ones both match via the
        # basename 'file_health_blocks'.
        terminal = module_path.lstrip(".").rsplit(".", 1)[-1]
        if terminal:
            entry.add(terminal)
    return index


def _callee_is_imported(
    caller_file: str,
    callee_file: str,
    import_index: dict[str, set[str]],
) -> bool:
    """Return True when the caller's import set covers the callee's module.

    Converts ``callee_file`` (a relative project path like
    ``tree_sitter_analyzer/mcp/tools/utils/file_health_blocks.py``) to:

    * A full dotted module path: ``tree_sitter_analyzer.mcp.tools.utils.file_health_blocks``
    * A terminal component: ``file_health_blocks``

    Then checks whether any entry in the caller's import set matches
    either form — covering both absolute and relative imports.

    Returns ``True`` (caller imports callee) when the import_index has no
    entry for the caller, so that files not recorded in ast_imports (e.g.
    languages not yet extracted) do not produce false negatives.
    """
    caller_imports = import_index.get(caller_file)
    if caller_imports is None:
        # No import data for caller → assume reachable to avoid false negatives.
        return True

    # Derive module identifiers from the callee's file path.
    without_ext = callee_file.removesuffix(".py")
    full_module = without_ext.replace("/", ".")
    terminal = without_ext.rsplit("/", 1)[-1]

    return full_module in caller_imports or terminal in caller_imports


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
