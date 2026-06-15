"""Shared runtime helpers for MCP-bridged CLI commands."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from typing import Any


def _classify_error_type(exc: BaseException) -> str:
    """Classify an exception into the canonical error_type vocabulary.

    The CLI envelope contract distinguishes ``validation`` (caller
    misuse — bad args) from ``runtime`` (anything else). The mapping is
    deliberately coarse so machine-parsing the envelope stays simple.
    """
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return "validation"
    return "runtime"


def _build_error_envelope(
    flag_name: str,
    label: str,
    exc: BaseException,
    echo_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical error envelope for MCP-bridged CLI commands.

    r37ah (re-added during PL-D long-tail cleanup): error responses
    must mirror ``agent_summary.verdict`` upward to the top level so
    the CLI envelope gate (``test_cli_envelope_contract``) accepts
    them. Without this, callers see ``verdict=None`` while
    ``agent_summary.verdict='ERROR'`` — the very drift the gate exists
    to catch.

    Shape (locked by ``test_mcp_command_error_envelope_has_top_verdict``):
        - ``success`` ``False``
        - ``error_type`` per ``_classify_error_type``
        - ``error`` — the human-readable message
        - ``summary_line`` — one-line headline
        - ``verdict`` ``"ERROR"`` (canonical vocabulary)
        - ``agent_summary.verdict`` ``"ERROR"`` (mirrored)
    """
    message = str(exc) or type(exc).__name__
    summary_line = f"{flag_name}: error — {message}"
    envelope: dict[str, Any] = {
        "success": False,
        "error_type": _classify_error_type(exc),
        "error": message,
        "summary_line": summary_line,
        # r37ah contract: top-level verdict mirror so the CLI envelope
        # gate accepts MCP-bridged error responses.
        "verdict": "ERROR",
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": summary_line,
            "next_step": "Fix the input and retry.",
            "label": label,
        },
    }
    if echo_fields:
        for key, value in echo_fields.items():
            envelope.setdefault(key, value)
    return envelope


# Verdict severity order — INFO is lowest, UNSAFE is highest.
# Must match _JOURNAL_VERDICT_RANK in change_impact_tool.py:
# INFO=0 < CAUTION=1 < REVIEW=2 < WARN=3 < UNSAFE=5
_VERDICT_ORDER = ("INFO", "CAUTION", "REVIEW", "WARN", "UNSAFE")


def _verdict_exit_code(result: dict[str, Any], threshold: str) -> int:
    """Return 1 if result verdict >= threshold in severity, else 0."""
    verdict = (result.get("verdict") or "INFO").upper()
    threshold = threshold.upper()
    try:
        verdict_idx = _VERDICT_ORDER.index(verdict)
    except ValueError:
        verdict_idx = 0
    try:
        threshold_idx = _VERDICT_ORDER.index(threshold)
    except ValueError:
        threshold_idx = 0
    return 1 if verdict_idx >= threshold_idx else 0


def _run_tool(
    args: Any,
    tool_cls: Callable[..., Any],
    tool_args: Mapping[str, Any],
    label: str,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
    fail_on_verdict_worse_than: str | None = None,
) -> int:
    """Helper: instantiate tool, run execute(), print output."""
    try:
        project_root = getattr(args, "project_root", None) or os.getcwd()
        tool = tool_cls(project_root=project_root)
        result: dict[str, Any] = asyncio.run(tool.execute(dict(tool_args)))
        fmt = output_format_fn()
        if fmt == "toon":
            print(result.get("toon_content", ""))
        else:
            output_json_fn(result)
        if not result.get("success", False):
            return 1
        if fail_on_verdict_worse_than is not None:
            return _verdict_exit_code(result, fail_on_verdict_worse_than)
        return 0
    except Exception as e:
        output_error_fn(f"{label} failed: {e}")
        return 1
