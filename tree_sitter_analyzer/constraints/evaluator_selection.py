"""Bounded SQL candidate selection for constraint evaluation."""

from __future__ import annotations

import sqlite3

from .parser import _CompiledConstraint

_MAX_SQL_PREFIX_FILTERS = 256


def _build_select_query(
    db_conn: sqlite3.Connection,
    compiled: list[_CompiledConstraint],
) -> tuple[str, tuple[str, ...]]:
    """Build the parameterized SELECT over the unified ``edges`` table.

    CALLS edges now live in ``edges`` with every resolution scalar promoted to
    a real column (B1.3). The callee file prefers ``callee_resolved_file`` and
    falls back to the caller's ``file_path`` when the call was never cross-file
    resolved — preserving the legacy ``CASE WHEN callee_resolved_file != ''``
    behaviour.

    Rules with literal caller or callee prefixes cannot match rows outside
    those prefixes. Push both necessary conditions into SQLite so the Python
    hot loop only sees plausible candidates. ``instr`` is case-sensitive and
    treats glob-special characters literally, preserving the regex matcher's
    path semantics.

    If any rule has no literal prefix, the query must retain every CALLS row
    because that rule may match anywhere. The ``db_conn`` argument is retained
    for signature compatibility.
    """
    callee_expr = (
        "CASE WHEN callee_resolved_file != '' "
        "THEN callee_resolved_file "
        "ELSE file_path END"
    )
    select_sql = (
        "SELECT caller_name, file_path AS caller_file, "
        "caller_line, callee_name, "
        f"{callee_expr} AS callee_file "  # nosec B608 — callee_expr is constructed from internal constants only
        "FROM edges WHERE kind = 'calls'"
    )
    from_prefixes = tuple(dict.fromkeys(cc.from_prefix for cc in compiled))
    to_prefixes = tuple(dict.fromkeys(cc.to_prefix for cc in compiled))
    filters: list[str] = []
    params: list[str] = []
    if (
        from_prefixes
        and "" not in from_prefixes
        and len(from_prefixes) <= _MAX_SQL_PREFIX_FILTERS
    ):
        filters.append(" OR ".join("instr(file_path, ?) = 1" for _ in from_prefixes))
        params.extend(from_prefixes)
    if (
        to_prefixes
        and "" not in to_prefixes
        and len(to_prefixes) <= _MAX_SQL_PREFIX_FILTERS
    ):
        filters.append(" OR ".join(f"instr({callee_expr}, ?) = 1" for _ in to_prefixes))
        params.extend(to_prefixes)
    if not filters:
        return select_sql, ()
    return (
        f"{select_sql} AND " + " AND ".join(f"({item})" for item in filters),
        tuple(params),
    )
