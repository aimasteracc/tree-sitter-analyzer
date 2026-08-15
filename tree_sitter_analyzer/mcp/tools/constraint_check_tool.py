#!/usr/bin/env python3
"""``check_constraints`` architectural-constraint DSL gate.

Evaluates cached call edges and optionally persists exact violations.
"""

from __future__ import annotations

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
from ...constraints.parser import ConstraintParseError
from ...read_existing_access import (
    READ_EXISTING_AUTHORITY_UNCERTIFIED,
    read_existing_unavailable,
    validate_optional_index_capability_pair,
    validate_read_existing_access,
    validate_read_existing_paths,
    validate_read_existing_schema_values,
)
from ...source_oracle import SourceOracleError
from ...wire_owner import EDIT_CONSTRAINTS_ACTION_VERSION
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool
from .constraint_check_live import (
    config_changed_response as _config_changed_response,
)
from .constraint_check_live import live_config_snapshot as _live_config_snapshot
from .constraint_check_live import load_live_constraints, path_is_in_scope
from .constraint_check_persistence import read_filtered_violations
from .constraint_check_schema import TOOL_SCHEMA

_path_is_in_scope = path_is_in_scope

logger = logging.getLogger(__name__)
# Exact verdict escalation: error > warn > info.
_BLOCKING_SEVERITIES: frozenset[str] = frozenset({"error"})
_WARNING_SEVERITIES: frozenset[str] = frozenset({"warn"})

_SEVERITY_ORDER: dict[str, int] = {"info": 0, "warn": 1, "error": 2}
_MAX_MATERIALIZED_VIOLATIONS = 10_000


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
        if not isinstance(severity_min, str) or severity_min not in _SEVERITY_ORDER:
            raise ValueError(
                f"severity_min must be one of {sorted(_SEVERITY_ORDER)}; "
                f"got {severity_min!r}"
            )
        from .constraint_check_snapshot import validate_snapshot_arguments

        validate_snapshot_arguments(arguments)
        read_existing = validate_read_existing_access(arguments)
        validate_optional_index_capability_pair(arguments)
        if read_existing and arguments.get("diff_snapshot_id") is None:
            raise ValueError(
                "diff_snapshot_id is required for access_mode=read_existing"
            )
        if read_existing:
            validate_read_existing_paths(self, arguments.get("scope_paths", []))
            validate_read_existing_schema_values(self, arguments)
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        if not self.project_root:
            return {
                "success": False,
                "error": "Project root not set. Call set_project_path first.",
                "action_version": EDIT_CONSTRAINTS_ACTION_VERSION,
            }

        access_arguments = arguments
        if "access_mode" in arguments and "output_format" not in arguments:
            access_arguments = {**arguments, "output_format": "json"}
        unavailable = read_existing_unavailable(
            access_arguments,
            reason=READ_EXISTING_AUTHORITY_UNCERTIFIED,
            action_version=EDIT_CONSTRAINTS_ACTION_VERSION,
        )
        if unavailable is not None:
            return apply_toon_format_to_response(
                unavailable, unavailable["output_format"]
            )

        if arguments.get("diff_snapshot_id") is not None:
            return self._execute_frozen(arguments)

        path_filter = arguments.get("path_filter", "") or ""
        severity_min = arguments.get("severity_min", "warn")
        output_format = arguments.get("output_format", "json")
        min_severity_rank = _SEVERITY_ORDER[severity_min]

        persist = arguments.get("persist", True)
        deadline = time.monotonic() + 10.0
        config_before = None
        try:
            if not persist:
                config_before, constraints = load_live_constraints(
                    self.project_root, deadline
                )
            else:
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
        except (OSError, RuntimeError, SourceOracleError) as exc:
            return self._snapshot_error(
                "CONSTRAINT_CONFIG_UNKNOWN", output_format, str(exc)
            )

        if not constraints and not persist:
            assert config_before is not None
            changed = _config_changed_response(
                self.project_root,
                config_before,
                deadline,
                output_format,
                self._snapshot_error,
                _live_config_snapshot,
            )
            if changed is not None:
                return changed
            return apply_toon_format_to_response(
                {
                    "success": True,
                    "verdict": "SAFE",
                    "action_version": EDIT_CONSTRAINTS_ACTION_VERSION,
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
                    "action_version": EDIT_CONSTRAINTS_ACTION_VERSION,
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
            try:
                _, evaluated_edges = self._run_and_persist(db_path, constraints)
                filtered_rows = self._read_filtered_violations(
                    db_path,
                    path_filter=path_filter,
                    min_severity_rank=min_severity_rank,
                )
            except RuntimeError as exc:
                if str(exc) != "CONSTRAINT_EVALUATION_CAPACITY":
                    raise
                return self._snapshot_error(
                    "CONSTRAINT_EVALUATION_CAPACITY", output_format, str(exc)
                )
        else:
            try:
                filtered_rows, evaluated_edges = self._run_read_only(
                    db_path,
                    constraints,
                    path_filter=path_filter,
                    min_severity_rank=min_severity_rank,
                    deadline=deadline,
                )
            except (
                sqlite3.DatabaseError,
                OSError,
                RuntimeError,
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:
                return self._snapshot_error(
                    "CONSTRAINT_INDEX_UNKNOWN", output_format, str(exc)
                )

        if not persist:
            assert config_before is not None
            changed = _config_changed_response(
                self.project_root,
                config_before,
                deadline,
                output_format,
                self._snapshot_error,
                _live_config_snapshot,
            )
            if changed is not None:
                return changed

        verdict = self._compute_verdict(filtered_rows)
        return apply_toon_format_to_response(
            {
                "success": True,
                "verdict": verdict,
                "action_version": EDIT_CONSTRAINTS_ACTION_VERSION,
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
        from .constraint_check_read_only import run_read_only

        return run_read_only(
            self,
            db_path,
            constraints,
            path_filter=path_filter,
            min_severity_rank=min_severity_rank,
            scope_paths=scope_paths,
            evaluator=evaluator,
            deadline=deadline,
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
        from .constraint_check_evaluation import evaluate_connection

        evaluator = evaluate if evaluator is None else evaluator
        return evaluate_connection(
            self,
            conn,
            constraints,
            path_filter=path_filter,
            min_severity_rank=min_severity_rank,
            scope_paths=scope_paths,
            evaluator=evaluator,
            deadline=deadline,
            capacity=_MAX_MATERIALIZED_VIOLATIONS,
        )

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
            except RuntimeError as exc:
                if str(exc) == "CONSTRAINT_EVALUATION_CAPACITY":
                    raise
                logger.warning("constraint evaluation failed: %s", exc)
                return [], edge_count
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
        return read_filtered_violations(
            db_path,
            path_filter=path_filter,
            min_severity_rank=min_severity_rank,
            severity_order=_SEVERITY_ORDER,
            ddl=self._violations_ddl(),
        )

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
