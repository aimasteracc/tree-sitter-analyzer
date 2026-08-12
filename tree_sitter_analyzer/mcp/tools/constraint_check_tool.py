#!/usr/bin/env python3
"""``check_constraints`` architectural-constraint DSL gate.

Evaluates cached call edges and optionally persists exact violations.
"""

from __future__ import annotations

import inspect
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from ...constraints import (
    Violation,
    evaluate,
    load_constraints,
)
from ...constraints.parser import ConstraintParseError, _compile_glob
from ...git_path_codec import path_to_wire
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .constraint_check_schema import TOOL_SCHEMA

logger = logging.getLogger(__name__)
# Exact verdict escalation: error > warn > info.
_BLOCKING_SEVERITIES: frozenset[str] = frozenset({"error"})
_WARNING_SEVERITIES: frozenset[str] = frozenset({"warn"})

_SEVERITY_ORDER: dict[str, int] = {"info": 0, "warn": 1, "error": 2}


class ConstraintCheckTool(BaseMCPTool):
    """MCP tool ``check_constraints`` — architectural rule evaluator."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "check_constraints",
            "description": (
                "Evaluate architectural-constraints.yml against the cached "
                "call graph. Returns violations + a UNSAFE/CAUTION/SAFE "
                "verdict that safe_to_edit and change_impact pick up. "
                "MUST call after schema/topology changes."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                # The legacy/default route writes the violation cache.  MCP
                # annotations describe the whole tool, not one argument shape;
                # persist=false is the explicitly read-only sub-route.
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        severity_min = arguments.get("severity_min", "warn")
        if severity_min not in _SEVERITY_ORDER:
            raise ValueError(
                f"severity_min must be one of {sorted(_SEVERITY_ORDER)}; "
                f"got {severity_min!r}"
            )
        persist = arguments.get("persist", True)
        if not isinstance(persist, bool):
            raise ValueError("persist must be a boolean")
        snapshot_id = arguments.get("diff_snapshot_id")
        scope_paths = arguments.get("scope_paths")
        if snapshot_id is not None:
            if not isinstance(snapshot_id, str) or not snapshot_id:
                raise ValueError("diff_snapshot_id must be a non-empty string")
            if persist:
                raise ValueError("diff_snapshot_id requires persist=false")
            if not isinstance(scope_paths, list) or any(
                not isinstance(path, str) for path in scope_paths
            ):
                raise ValueError("diff_snapshot_id requires scope_paths as strings")
            if arguments.get("path_filter"):
                raise ValueError("DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS")
        elif scope_paths is not None:
            raise ValueError("scope_paths requires diff_snapshot_id")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if not self.project_root:
            return {
                "success": False,
                "error": "Project root not set. Call set_project_path first.",
            }

        if arguments.get("diff_snapshot_id") is not None:
            return self._execute_frozen(arguments)

        path_filter = arguments.get("path_filter", "") or ""
        severity_min = arguments.get("severity_min", "warn")
        output_format = arguments.get("output_format", "json")
        min_severity_rank = _SEVERITY_ORDER[severity_min]

        try:
            constraints = load_constraints(self.project_root)
        except ConstraintParseError as exc:
            return apply_toon_format_to_response(
                {
                    "success": False,
                    "verdict": "CAUTION",
                    "error": f"constraint parse error: {exc}",
                    "violations": [],
                    "rule_count": 0,
                },
                output_format,
            )

        persist = arguments.get("persist", True)
        if not constraints and not persist:
            return apply_toon_format_to_response(
                {
                    "success": True,
                    "verdict": "SAFE",
                    "violations": [],
                    "rule_count": 0,
                    "evaluated_edge_count": 0,
                },
                output_format,
            )

        db_path = Path(self.project_root) / ".ast-cache" / "index.db"
        if persist and not db_path.is_file():
            return apply_toon_format_to_response(
                {
                    "success": True,
                    "verdict": "SAFE",
                    "violations": [],
                    "rule_count": len(constraints),
                    "evaluated_edge_count": 0,
                    "note": (
                        "No AST cache at .ast-cache/index.db; "
                        "run codegraph_autoindex first."
                    ),
                },
                output_format,
            )

        if persist:
            _, evaluated_edges = self._run_and_persist(db_path, constraints)
            filtered_rows = self._read_filtered_violations(
                db_path,
                path_filter=path_filter,
                min_severity_rank=min_severity_rank,
            )
        else:
            try:
                filtered_rows, evaluated_edges = self._run_read_only(
                    db_path,
                    constraints,
                    path_filter=path_filter,
                    min_severity_rank=min_severity_rank,
                    deadline=time.monotonic() + 10.0,
                )
            except (sqlite3.DatabaseError, RuntimeError, ValueError) as exc:
                return self._snapshot_error(
                    "CONSTRAINT_INDEX_UNKNOWN", output_format, str(exc)
                )

        verdict = self._compute_verdict(filtered_rows)
        return apply_toon_format_to_response(
            {
                "success": True,
                "verdict": verdict,
                "violations": filtered_rows,
                "rule_count": len(constraints),
                "evaluated_edge_count": evaluated_edges,
            },
            output_format,
        )

    def _execute_frozen(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Delegate the frozen capability path to its focused production module."""
        from .constraint_check_frozen import execute_frozen

        return execute_frozen(self, arguments)

    @staticmethod
    def severity_rank(severity: str) -> int:
        """Return the canonical ordering used by both live and frozen paths."""
        return _SEVERITY_ORDER[severity]

    @staticmethod
    def _snapshot_error(
        code: str, output_format: str, detail: str | None = None
    ) -> dict[str, Any]:
        return apply_toon_format_to_response(
            {
                "success": False,
                "verdict": "ERROR",
                "error_code": code,
                "error": detail or code,
            },
            output_format,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_read_only(
        self,
        db_path: Path,
        constraints: list[Any],
        *,
        path_filter: str,
        min_severity_rank: int,
        scope_paths: frozenset[str] | None = None,
        evaluator: Any = None,
        deadline: float | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Evaluate the registry-owned private snapshot; never trust a pathname URI."""
        from ...index_snapshot import acquire_index_snapshot, lease_existing_snapshot

        del (
            db_path
        )  # Compatibility-only argument; pathname evidence is never opened here.
        absolute_deadline = time.monotonic() + 10.0 if deadline is None else deadline
        if time.monotonic() >= absolute_deadline:
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
        lease_kwargs = (
            {"deadline": absolute_deadline}
            if "deadline" in inspect.signature(lease_existing_snapshot).parameters
            else {}
        )
        project_root = self.project_root
        if project_root is None:
            raise ValueError("MISSING_PROJECT_ROOT")
        with lease_existing_snapshot(project_root, **lease_kwargs) as index:
            if index.snapshot_id is None or index.completeness != "complete":
                raise ValueError(index.reason or "CONSTRAINT_INDEX_UNKNOWN")
            acquire_kwargs = (
                {"deadline": absolute_deadline}
                if "deadline" in inspect.signature(acquire_index_snapshot).parameters
                else {}
            )
            with acquire_index_snapshot(
                index.snapshot_id,
                project_root,
                index.source_generation,
                **acquire_kwargs,
            ) as (_, conn):
                return self._evaluate_connection(
                    conn,
                    constraints,
                    path_filter=path_filter,
                    min_severity_rank=min_severity_rank,
                    scope_paths=scope_paths,
                    evaluator=evaluator,
                    deadline=absolute_deadline,
                )

    def _evaluate_connection(
        self,
        conn: sqlite3.Connection,
        constraints: list[Any],
        *,
        path_filter: str = "",
        min_severity_rank: int,
        scope_paths: frozenset[str] | None = None,
        evaluator: Any = None,
        deadline: float | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Evaluate one caller-owned immutable index connection; fail closed."""
        evaluator = evaluate if evaluator is None else evaluator
        absolute_deadline = time.monotonic() + 10.0 if deadline is None else deadline

        def interrupted() -> int:
            return int(time.monotonic() >= absolute_deadline)

        if interrupted():
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
        owns_transaction = not conn.in_transaction
        conn.set_progress_handler(interrupted, 1_000)
        if owns_transaction:
            conn.execute("BEGIN")
        try:
            edge_count = self._count_edges(conn, fail_closed=True)
            if scope_paths is None:
                violations = evaluator(constraints, conn)
            else:

                def in_scope(caller: str, callee: str) -> bool:
                    return (
                        path_to_wire(caller) in scope_paths
                        or path_to_wire(callee) in scope_paths
                    )

                violations = evaluator(
                    constraints,
                    conn,
                    scope_predicate=in_scope,
                )
        finally:
            if owns_transaction:
                conn.rollback()
            conn.set_progress_handler(None, 0)
        if interrupted():
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
        path_re = _compile_glob(path_filter) if path_filter else None
        rows: list[dict[str, Any]] = []
        for violation in violations:
            if interrupted():
                raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
            caller = path_to_wire(violation.caller_file)
            callee = path_to_wire(violation.callee_file)
            # Keep a defensive output filter for injected/custom evaluators;
            # the production evaluator receives the same scope before dedup.
            if scope_paths is not None and not (
                caller in scope_paths or callee in scope_paths
            ):
                continue
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
        if interrupted():
            raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
        return rows, edge_count

    def _run_and_persist(
        self,
        db_path: Path,
        constraints: list[Any],
    ) -> tuple[list[Violation], int]:
        """Evaluate and persist, preserving cached rows when no CALLS exist."""
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(self._violations_ddl())
            edge_count = self._count_edges(conn)
            if edge_count == 0:
                # Nothing to evaluate; leave any previously-persisted
                # violations alone so cache-then-read still works.
                return [], 0

            try:
                violations = evaluate(constraints, conn)
            except Exception as exc:  # noqa: BLE001 — log + degrade
                logger.warning("constraint evaluation failed: %s", exc)
                return [], edge_count

            # Replace previous violation rows so stale rows don't linger
            # when a rule is fixed or removed.
            conn.execute("DELETE FROM ast_constraint_violations")
            now = int(time.time())
            conn.executemany(
                """
                INSERT OR IGNORE INTO ast_constraint_violations
                    (rule_id, caller_file, caller_name, caller_line,
                     callee_name, callee_file, severity, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
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

    @staticmethod
    def _count_edges(conn: sqlite3.Connection, *, fail_closed: bool = False) -> int:
        """Return the CALLS row count of the unified ``edges`` table, or 0."""
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE kind = 'calls'"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            if fail_closed:
                raise
            return 0

    def _read_filtered_violations(
        self,
        db_path: Path,
        *,
        path_filter: str,
        min_severity_rank: int,
    ) -> list[dict[str, Any]]:
        """Read violations with canonical Python glob filtering."""
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(self._violations_ddl())
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
                rank = _SEVERITY_ORDER.get(severity, 0)
                if rank < min_severity_rank:
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

    @staticmethod
    def _compute_verdict(rows: list[dict[str, Any]]) -> str:
        """Map (filtered) violations to the canonical verdict."""
        has_error = any(r["severity"] in _BLOCKING_SEVERITIES for r in rows)
        if has_error:
            return "UNSAFE"
        has_warn = any(r["severity"] in _WARNING_SEVERITIES for r in rows)
        if has_warn:
            return "CAUTION"
        return "SAFE"

    @staticmethod
    def _violations_ddl() -> str:
        """Return DDL kept in sync with the cache violation schema."""
        return """
        CREATE TABLE IF NOT EXISTS ast_constraint_violations (
            rule_id      TEXT NOT NULL,
            caller_file  TEXT NOT NULL,
            caller_name  TEXT NOT NULL,
            caller_line  INTEGER NOT NULL,
            callee_name  TEXT NOT NULL,
            callee_file  TEXT NOT NULL DEFAULT '',
            severity     TEXT NOT NULL,
            detected_at  INTEGER NOT NULL,
            PRIMARY KEY (rule_id, caller_file, caller_line, callee_name)
        )
        """
