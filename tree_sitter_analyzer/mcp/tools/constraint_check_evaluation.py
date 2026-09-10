"""Deadline- and capacity-bounded constraint connection evaluation."""

from __future__ import annotations

import inspect
import sqlite3
import time
from typing import Any

from ...constraints import evaluate
from ...constraints.parser import _compile_glob
from ...git_path_codec import path_to_wire
from .constraint_check_live import path_is_in_scope as _path_is_in_scope

_SEVERITY_ORDER = {"info": 0, "warn": 1, "error": 2}
_MAX_MATERIALIZED_VIOLATIONS = 10_000


def evaluate_connection(
    tool: Any,
    conn: sqlite3.Connection,
    constraints: list[Any],
    *,
    path_filter: str = "",
    min_severity_rank: int,
    scope_paths: frozenset[str] | None = None,
    evaluator: Any = None,
    deadline: float | None = None,
    capacity: int = _MAX_MATERIALIZED_VIOLATIONS,
) -> tuple[list[dict[str, Any]], int]:
    """Evaluate one caller-owned immutable index connection; fail closed."""
    evaluator = evaluate if evaluator is None else evaluator
    absolute_deadline = time.monotonic() + 10.0 if deadline is None else deadline

    def interrupted() -> int:
        return int(time.monotonic() >= absolute_deadline)

    def check_deadline() -> None:
        if interrupted():
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")

    check_deadline()
    owns_transaction = not conn.in_transaction
    conn.set_progress_handler(interrupted, 1_000)
    if owns_transaction:
        conn.execute("BEGIN")
    try:
        edge_count = tool._count_edges(conn, fail_closed=True)
        evaluator_kwargs: dict[str, Any] = {}
        evaluator_parameters = inspect.signature(evaluator).parameters
        if "check_callback" in evaluator_parameters:
            evaluator_kwargs["check_callback"] = check_deadline
        if "capacity" in evaluator_parameters:
            evaluator_kwargs["capacity"] = capacity
        if scope_paths is not None:

            def in_scope(caller: str, callee: str) -> bool:
                return _path_is_in_scope(caller, scope_paths) or _path_is_in_scope(
                    callee, scope_paths
                )

            evaluator_kwargs["scope_predicate"] = in_scope
        violations = evaluator(constraints, conn, **evaluator_kwargs)
    finally:
        if owns_transaction:
            conn.rollback()
        conn.set_progress_handler(None, 0)
    check_deadline()
    path_re = _compile_glob(path_filter) if path_filter else None
    rows: list[dict[str, Any]] = []
    for violation_number, violation in enumerate(violations, start=1):
        check_deadline()
        if violation_number > capacity:
            raise RuntimeError("CONSTRAINT_EVALUATION_CAPACITY")
        # Keep raw endpoints until the defensive scope check. Wire values
        # beginning with git-path-b64: are escaped by path_to_wire(), so feeding
        # an already-wired endpoint back into _path_is_in_scope() double-encodes it.
        caller_raw = violation.caller_file
        callee_raw = violation.callee_file
        if scope_paths is not None and not (
            _path_is_in_scope(caller_raw, scope_paths)
            or _path_is_in_scope(callee_raw, scope_paths)
        ):
            continue
        caller = path_to_wire(caller_raw)
        callee = path_to_wire(callee_raw)
        if _SEVERITY_ORDER.get(violation.severity, 0) < min_severity_rank:
            continue
        if path_re is not None and path_re.fullmatch(caller) is None:
            continue
        rows.append(
            {
                "rule_id": violation.rule_id,
                "caller_file": caller,
                "caller_name": violation.caller_name,
                "caller_line": violation.caller_line,
                "callee_name": violation.callee_name,
                "callee_file": callee,
                "severity": violation.severity,
                "detected_at": violation.detected_at,
            }
        )
    rows.sort(
        key=lambda row: (
            -_SEVERITY_ORDER.get(str(row["severity"]), 0),
            str(row["caller_file"]),
            int(row["caller_line"]),
            str(row["rule_id"]),
        )
    )
    check_deadline()
    return rows, edge_count
