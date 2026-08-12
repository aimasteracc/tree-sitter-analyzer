#!/usr/bin/env python3
"""``check_constraints`` MCP tool — architectural-constraint DSL gate.

Reads architectural-constraints.yml from project root, evaluates rules
against the cached call-edge index, writes the result into
``ast_constraint_violations``, and returns the verdict.

Verdict mapping (Feature 3 spec):
    error severity present → UNSAFE
    only warn severity     → CAUTION
    no violations          → SAFE

This is the ONLY tool in MVP that emits the UNSAFE verdict; safe_to_edit
and analyze_change_impact read it through the violations table.
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
from ...constraints.parser import (
    ConstraintParseError,
    _compile_glob,
    load_constraints_bytes,
)
from ...git_path_codec import path_to_wire
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = logging.getLogger(__name__)

# Severities that block (verdict UNSAFE) vs warn (verdict CAUTION) vs
# silent (no verdict impact). Order in the lists determines the verdict
# escalation precedence — error > warn > info — and is asserted by tests.
_BLOCKING_SEVERITIES: frozenset[str] = frozenset({"error"})
_WARNING_SEVERITIES: frozenset[str] = frozenset({"warn"})

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path_filter": {
            "type": "string",
            "default": "",
            "description": (
                "Optional fnmatch-style glob applied to caller_file. "
                "Use to narrow results to a queue scope, e.g. 'mcp/**'."
            ),
        },
        "severity_min": {
            "type": "string",
            "enum": ["error", "warn", "info"],
            "default": "warn",
            "description": (
                "Minimum severity to include in the response. "
                "Default 'warn' suppresses info-level rules from agent output."
            ),
        },
        "persist": {
            "type": "boolean",
            "default": True,
            "description": (
                "Write evaluated violations through to the cache. Set false for "
                "RFC-0022 read-only evaluation; no database or file is created."
            ),
        },
        "diff_snapshot_id": {
            "type": "string",
            "description": "RFC-0022 frozen diff snapshot to evaluate against.",
        },
        "scope_paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Primitive-issued assessed_scope_paths. With diff_snapshot_id the "
                "list must exactly match the frozen snapshot scope."
            ),
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "json",
            "description": "Response format.",
        },
    },
    "additionalProperties": False,
}


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

        db_path = Path(self.project_root) / ".ast-cache" / "index.db"
        if not db_path.is_file():
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

        if arguments.get("persist", True):
            _, evaluated_edges = self._run_and_persist(db_path, constraints)
            filtered_rows = self._read_filtered_violations(
                db_path,
                path_filter=path_filter,
                min_severity_rank=min_severity_rank,
            )
        else:
            filtered_rows, evaluated_edges = self._run_read_only(
                db_path,
                constraints,
                path_filter=path_filter,
                min_severity_rank=min_severity_rank,
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
        """Evaluate frozen config and DB capabilities bound to one generation."""
        from ...diff_snapshot_registry import REGISTRY as DIFF_REGISTRY
        from ...index_snapshot import lease_existing_snapshot
        from ...source_oracle import SourceOracleError, safe_workspace_path

        output_format = arguments.get("output_format", "json")
        snapshot_id = str(arguments["diff_snapshot_id"])
        project_root = self.project_root
        if project_root is None:
            return self._snapshot_error("MISSING_PROJECT_ROOT", output_format)
        consumer, error = DIFF_REGISTRY.acquire(snapshot_id, project_root)
        if error:
            return self._snapshot_error(error, output_format)
        assert consumer is not None
        try:
            diff = consumer.snapshot
            frozen_scope = [path_to_wire(path) for path in diff.assessed_scope_paths]
            if arguments["scope_paths"] != frozen_scope:
                return self._snapshot_error(
                    "DIFF_SNAPSHOT_SCOPE_MISMATCH", output_format
                )
            try:
                with lease_existing_snapshot(project_root) as index:
                    if (
                        index.snapshot_id is None
                        or index.completeness != "complete"
                        or index.source_generation != diff.source_generation
                    ):
                        return self._snapshot_error(
                            index.reason or "SOURCE_GENERATION_MISMATCH", output_format
                        )
                    # Configuration discovery and bytes are owned by impact's
                    # immutable registry entry, not reread as initial evidence.
                    config_name = diff.constraint_config_path
                    config_data = diff.constraint_config_data
                    if config_name is None:
                        response: dict[str, Any] = {
                            "success": True,
                            "state": "not_applicable",
                            "reason": "NO_CONFIG",
                            "verdict": "INFO",
                            "violations": [],
                            "rule_count": 0,
                            "evaluated_edge_count": 0,
                        }
                    else:
                        try:
                            constraints = load_constraints_bytes(
                                config_data or b"", config_name
                            )
                        except ConstraintParseError as exc:
                            return self._snapshot_error(
                                "CONSTRAINT_CONFIG_INVALID", output_format, str(exc)
                            )
                        try:
                            from ...index_snapshot import acquire_index_snapshot

                            with acquire_index_snapshot(
                                index.snapshot_id,
                                project_root,
                                diff.source_generation,
                            ) as (_, conn):
                                rows, edge_count = self._evaluate_connection(
                                    conn,
                                    constraints,
                                    min_severity_rank=_SEVERITY_ORDER[
                                        arguments.get("severity_min", "warn")
                                    ],
                                    scope_paths=frozenset(frozen_scope),
                                )
                        except (sqlite3.DatabaseError, ValueError) as exc:
                            return self._snapshot_error(
                                "CONSTRAINT_INDEX_UNKNOWN", output_format, str(exc)
                            )
                        response = {
                            "success": True,
                            "state": "applicable",
                            "verdict": self._compute_verdict(rows),
                            "violations": rows,
                            "rule_count": len(constraints),
                            "evaluated_edge_count": edge_count,
                        }
                    # Revalidate current discovery against impact-owned bytes and
                    # descriptor identities before publishing.
                    rechecked = None
                    rechecked_name = None
                    for candidate in (
                        "architectural-constraints.yml",
                        ".tree-sitter-analyzer/constraints.yml",
                    ):
                        probe = safe_workspace_path(
                            index.canonical_root or project_root,
                            candidate,
                            deadline=time.monotonic() + 10.0,
                            limit=1024 * 1024,
                        )
                        rechecked = probe
                        if probe.kind != "missing":
                            rechecked_name = candidate
                            break
                    if (
                        rechecked is None
                        or config_name != rechecked_name
                        or config_data != rechecked.data
                        or diff.constraint_config_metadata != rechecked.metadata
                    ):
                        return self._snapshot_error(
                            "CONSTRAINT_CONFIG_CHANGED", output_format
                        )

                    response.update(
                        diff_snapshot_id=diff.snapshot_id,
                        snapshot_id=index.snapshot_id,
                        source_generation=diff.source_generation,
                        index_fingerprint=index.index_fingerprint,
                        assessed_scope_paths=frozen_scope,
                    )
            except (
                OSError,
                RuntimeError,
                SourceOracleError,
                sqlite3.DatabaseError,
            ) as exc:
                return self._snapshot_error(
                    "CONSTRAINT_CAPTURE_UNKNOWN", output_format, str(exc)
                )
            error = DIFF_REGISTRY.validate_publish(consumer)
            if error:
                return self._snapshot_error(error, output_format)
            return apply_toon_format_to_response(response, output_format)
        finally:
            consumer.release()

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
    ) -> tuple[list[dict[str, Any]], int]:
        """Evaluate through a SQLite read-only connection and write nothing."""
        conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            return self._evaluate_connection(
                conn,
                constraints,
                path_filter=path_filter,
                min_severity_rank=min_severity_rank,
                scope_paths=scope_paths,
            )
        finally:
            conn.close()

    def _evaluate_connection(
        self,
        conn: sqlite3.Connection,
        constraints: list[Any],
        *,
        path_filter: str = "",
        min_severity_rank: int,
        scope_paths: frozenset[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Evaluate one caller-owned immutable index connection; fail closed."""
        edge_count = self._count_edges(conn, fail_closed=True)
        violations = evaluate(constraints, conn)
        path_re = _compile_glob(path_filter) if path_filter else None
        rows: list[dict[str, Any]] = []
        for violation in violations:
            caller = path_to_wire(violation.caller_file)
            callee = path_to_wire(violation.callee_file)
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
        return rows, edge_count

    def _run_and_persist(
        self,
        db_path: Path,
        constraints: list[Any],
    ) -> tuple[list[Violation], int]:
        """Run the evaluator and write-through into ``ast_constraint_violations``.

        Returns (violations, edge_count) for diagnostics. The
        ``evaluated_edge_count`` is best-effort — we count whatever the
        evaluator sees, which is a useful sanity signal even if it
        doesn't perfectly match the rule-count cross-product.

        Cache-then-read contract: if there are no CALLS rows in the unified
        ``edges`` table we DO NOT touch the existing violations table.
        That preserves rows that were seeded by another producer (the
        ``analyze_change_impact`` indexer, an earlier full run, or — in
        tests — directly by a fixture). Without this guard we'd wipe out
        legitimate cached state every time an agent ran the tool against
        a fresh repo.
        """
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
        """Read violations from the table with severity + path filters applied.

        The path filter is applied in Python (not SQL) because SQLite's
        GLOB is glob-but-not-globstar — we want our ``**`` semantics,
        which means re-using the same ``_compile_glob`` the evaluator
        uses.
        """
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
        """Self-healing DDL — keeps the tool usable even if the global
        migration hasn't run yet (e.g. a test that builds a fresh DB).

        The DDL must stay in sync with ``ast_cache._SCHEMA_V6_VIOLATIONS``.
        """
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
