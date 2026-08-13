#!/usr/bin/env python3
"""CLI command for ``--check-constraints`` (MCP parity for ``check_constraints``).

Wraps :class:`ConstraintCheckTool` so the CLI gets the same architectural
constraint evaluation that MCP clients invoke. Adds two CLI-only
conveniences on top of the MCP tool surface:

* ``--constraint-file PATH``: override default discovery of
  ``architectural-constraints.yml`` under the project root.
* exit code semantics (1 / 2 / 0) for shell-pipeline use, mirroring
  ``--change-impact`` and ``--safe-to-edit``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from ...constraints import evaluate, load_constraints
from ...constraints.parser import (
    ConstraintParseError,
    _compile_glob,
    load_constraints_bytes,
)
from ...mcp.tools.constraint_check_tool import ConstraintCheckTool
from .constraint_check_execution import (
    explicit_config_evidence,
)
from .constraint_check_persistence import run_and_persist

_SEVERITY_ORDER: dict[str, int] = {"info": 0, "warn": 1, "error": 2}
_BLOCKING_SEVERITIES: frozenset[str] = frozenset({"error"})
_WARNING_SEVERITIES: frozenset[str] = frozenset({"warn"})
_EXPLICIT_CONFIG_BYTE_LIMIT = 1024 * 1024
_EXPLICIT_CONFIG_READ_SECONDS = 10.0

# Exit-code contract for CI/CD wrappers. UNSAFE blocks (exit 1) so a
# `--check-constraints` step in a Makefile/Husky hook fails the pipeline
# the same way pytest does. CAUTION returns 2 so callers that *only*
# want to gate on hard failures can keep their `|| true` guard.
_EXIT_UNSAFE = 1
_EXIT_CAUTION = 2
_EXIT_SAFE = 0


def run_check_constraints(args: Any, project_root: str) -> int:
    """Run the constraint check and print the verdict to stdout.

    Args:
        args: argparse namespace with the constraint flags applied
            (``severity_min``, ``constraint_path_filter``,
            ``constraint_file``, ``output_format`` / ``format``).
        project_root: project root for default constraint discovery and
            cache lookup.

    Returns:
        Exit code: 1 if error-severity violations present, 2 if warn-only,
        0 if SAFE. Errors during loading return 1 as well so a malformed
        YAML doesn't silently pass.
    """
    output_format = _resolve_output_format(args)
    severity_min = getattr(args, "severity_min", None) or "warn"
    path_filter = getattr(args, "constraint_path_filter", "") or ""
    constraint_file = getattr(args, "constraint_file", None)
    read_only = bool(getattr(args, "constraints_read_only", False))

    if constraint_file:
        # CLI-only path: explicit constraint file, evaluate directly so
        # we don't have to hide a load_constraints override behind the
        # MCP tool's project-root contract.
        result = _evaluate_with_explicit_file(
            project_root=project_root,
            constraint_file=constraint_file,
            severity_min=severity_min,
            path_filter=path_filter,
            output_format=output_format,
            persist=not read_only,
        )
    else:
        # Default path: delegate to the MCP tool so CLI and MCP share a
        # single evaluator and the same persisted-violations write-through.
        result = asyncio.run(
            _run_tool(
                project_root=project_root,
                severity_min=severity_min,
                path_filter=path_filter,
                output_format=output_format,
                persist=not read_only,
            )
        )

    _print_result(result, output_format)
    return _exit_code_for(result)


def _run_tool(
    project_root: str,
    severity_min: str,
    path_filter: str,
    output_format: str,
    persist: bool = True,
) -> Any:
    """Await the MCP ConstraintCheckTool with CLI-supplied arguments."""
    tool = ConstraintCheckTool(project_root=project_root)
    tool_arguments: dict[str, Any] = {
        "path_filter": path_filter,
        "severity_min": severity_min,
        "output_format": output_format,
    }
    if not persist:
        tool_arguments["persist"] = False
    return tool.execute(tool_arguments)


def _explicit_config_evidence(
    config_path: Path, deadline: float
) -> tuple[bytes, os.stat_result]:
    return explicit_config_evidence(config_path, deadline)


def _read_explicit_config(config_path: Path, deadline: float) -> bytes:
    return _explicit_config_evidence(config_path, deadline)[0]


def _explicit_config_changed(
    config_path: Path, before: tuple[bytes, os.stat_result], deadline: float
) -> bool:
    try:
        return _explicit_config_evidence(config_path, deadline) != before
    except (OSError, RuntimeError):
        return True


def _evaluate_with_explicit_file(
    *,
    project_root: str,
    constraint_file: str,
    severity_min: str,
    path_filter: str,
    output_format: str,
    persist: bool = True,
) -> dict[str, Any]:
    """Evaluate against an explicit constraint file (CLI-only override).

    The MCP tool deliberately doesn't expose this — the MCP contract is
    "project root, find the canonical YAML, use it". The CLI exposes it
    because shell users sometimes want to dry-run a candidate constraint
    file before checking it in.
    """
    config_path = Path(constraint_file)
    if not config_path.is_file():
        return _failure_envelope(
            f"constraint file not found: {constraint_file}", output_format
        )

    config_deadline = time.monotonic() + _EXPLICIT_CONFIG_READ_SECONDS
    config_before: tuple[bytes, os.stat_result] | None = None
    try:
        if not persist:
            config_before = _explicit_config_evidence(config_path, config_deadline)
            constraints = load_constraints_bytes(config_before[0], config_path)
        else:
            constraints = _load_explicit(config_path)
    except (ConstraintParseError, OSError, RuntimeError) as exc:
        return _failure_envelope(f"constraint parse error: {exc}", output_format)

    if not constraints and not persist:
        assert config_before is not None
        if _explicit_config_changed(config_path, config_before, config_deadline):
            return _config_changed_envelope(0, output_format)
        return _format_response(
            {
                "success": True,
                "verdict": "SAFE",
                "violations": [],
                "rule_count": 0,
                "evaluated_edge_count": 0,
                "constraint_file": str(config_path),
            },
            output_format,
        )

    db_path = Path(project_root) / ".ast-cache" / "index.db"
    if persist and not db_path.is_file():
        return _format_response(
            {
                "success": True,
                "verdict": "SAFE",
                "violations": [],
                "rule_count": len(constraints),
                "evaluated_edge_count": 0,
                "note": (
                    "No AST cache at .ast-cache/index.db; run "
                    "codegraph_autoindex first."
                ),
            },
            output_format,
        )

    min_severity_rank = _SEVERITY_ORDER.get(severity_min, 1)
    try:
        if persist:
            violations, edge_count = _run_and_persist(
                db_path, constraints, persist=True
            )
            filtered = _filter_violations(
                violations,
                path_filter=path_filter,
                min_severity_rank=min_severity_rank,
            )
        else:
            filtered, edge_count = ConstraintCheckTool(
                project_root=project_root
            )._run_read_only(
                db_path,
                constraints,
                path_filter=path_filter,
                min_severity_rank=min_severity_rank,
                evaluator=evaluate,
                deadline=time.monotonic() + 10.0,
            )
    except (
        sqlite3.DatabaseError,
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        error_code = (
            "CONSTRAINT_EVALUATION_CAPACITY"
            if str(exc) == "CONSTRAINT_EVALUATION_CAPACITY"
            else "CONSTRAINT_INDEX_UNKNOWN"
        )
        return _format_response(
            {
                "success": False,
                "verdict": "ERROR",
                "error_code": error_code,
                "error": str(exc),
                "violations": [],
                "rule_count": len(constraints),
            },
            output_format,
        )
    if not persist:
        assert config_before is not None
        if _explicit_config_changed(config_path, config_before, config_deadline):
            return _config_changed_envelope(len(constraints), output_format)
    verdict = _compute_verdict(filtered)
    return _format_response(
        {
            "success": True,
            "verdict": verdict,
            "violations": filtered,
            "rule_count": len(constraints),
            "evaluated_edge_count": edge_count,
            "constraint_file": str(config_path),
        },
        output_format,
    )


def _load_explicit(config_path: Path) -> list[Any]:
    """Load constraints from an explicit file by reusing ``load_constraints``.

    ``load_constraints(project_root)`` looks for the canonical filename
    under project_root. To support an arbitrary ``--constraint-file`` we
    stage the YAML into a tempdir under the canonical name and call the
    public loader against that staging root — keeping all parsing rules
    intact without touching the constraints package internals.
    """
    import shutil
    import tempfile

    if config_path.name == "architectural-constraints.yml":
        return load_constraints(str(config_path.parent))

    # Different filename → stage into a tempdir under the canonical name
    # so the public loader applies the same parsing rules.
    with tempfile.TemporaryDirectory(prefix="tsa-constraints-") as tmp:
        staged = Path(tmp) / "architectural-constraints.yml"
        shutil.copyfile(config_path, staged)
        return load_constraints(tmp)


def _run_and_persist(
    db_path: Path,
    constraints: list[Any],
    *,
    persist: bool = True,
) -> tuple[list[Any], int]:
    return run_and_persist(
        db_path,
        constraints,
        persist=persist,
        evaluator=evaluate,
        violations_ddl=_violations_ddl,
    )


def _filter_violations(
    violations: list[Any],
    *,
    path_filter: str,
    min_severity_rank: int,
) -> list[dict[str, Any]]:
    """Apply severity floor + path-glob filters; return dict rows."""
    path_re = _compile_glob(path_filter) if path_filter else None
    rows: list[dict[str, Any]] = []
    for v in violations:
        rank = _SEVERITY_ORDER.get(v.severity, 0)
        if rank < min_severity_rank:
            continue
        if path_re is not None and path_re.fullmatch(v.caller_file) is None:
            continue
        rows.append(
            {
                "rule_id": v.rule_id,
                "caller_file": v.caller_file,
                "caller_name": v.caller_name,
                "caller_line": v.caller_line,
                "callee_name": v.callee_name,
                "callee_file": v.callee_file,
                "severity": v.severity,
                "detected_at": v.detected_at,
            }
        )
    return rows


def _compute_verdict(rows: list[dict[str, Any]]) -> str:
    """Map (filtered) violations to the canonical verdict."""
    has_error = any(r["severity"] in _BLOCKING_SEVERITIES for r in rows)
    if has_error:
        return "UNSAFE"
    has_warn = any(r["severity"] in _WARNING_SEVERITIES for r in rows)
    if has_warn:
        return "CAUTION"
    return "SAFE"


def _violations_ddl() -> str:
    """Self-healing DDL — mirrors constraint_check_tool._violations_ddl."""
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


def _format_response(payload: dict[str, Any], output_format: str) -> dict[str, Any]:
    """Apply TOON formatting when requested, identical to MCP tool helper."""
    from ...mcp.utils.format_helper import apply_toon_format_to_response

    return apply_toon_format_to_response(payload, output_format)


def _config_changed_envelope(rule_count: int, output_format: str) -> dict[str, Any]:
    payload = {
        "success": False,
        "verdict": "ERROR",
        "violations": [],
        "error_code": "CONSTRAINT_CONFIG_CHANGED",
        "error": "CONSTRAINT_CONFIG_CHANGED",
        "rule_count": rule_count,
    }
    return _format_response(payload, output_format)


def _failure_envelope(message: str, output_format: str) -> dict[str, Any]:
    """Build a CAUTION-verdict failure response that obeys the envelope."""
    return _format_response(
        {
            "success": False,
            "verdict": "CAUTION",
            "error": message,
            "violations": [],
            "rule_count": 0,
        },
        output_format,
    )


def _resolve_output_format(args: Any) -> str:
    """Return ``json`` or ``toon`` based on argparse-visible format flags.

    Delegates to :func:`tree_sitter_analyzer.cli.output_format.resolve_mcp_tool_format`
    so the args→tool-format mapping has one source of truth (r37an).
    """
    from tree_sitter_analyzer.cli.output_format import resolve_mcp_tool_format

    return resolve_mcp_tool_format(args)


def _print_result(result: dict[str, Any], output_format: str) -> None:
    """Write the response to stdout in the requested format."""
    if output_format == "toon":
        print(result.get("toon_content", ""))
    else:
        print(json.dumps(result, indent=2, default=str))


def _exit_code_for(result: dict[str, Any]) -> int:
    """Map verdict to shell exit code."""
    if not result.get("success", False):
        return _EXIT_UNSAFE
    verdict = result.get("verdict", "SAFE")
    if verdict == "UNSAFE":
        return _EXIT_UNSAFE
    if verdict == "CAUTION":
        return _EXIT_CAUTION
    return _EXIT_SAFE


def get_default_project_root(args: Any) -> str:
    """Return ``--project-root`` if set, else CWD."""
    return getattr(args, "project_root", None) or os.getcwd()
