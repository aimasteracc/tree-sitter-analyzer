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


def _run_tool(
    args: Any,
    tool_cls: Callable[..., Any],
    tool_args: Mapping[str, Any],
    label: str,
    output_json_fn: Callable[[dict[str, Any]], None],
    output_error_fn: Callable[[str], None],
    output_format_fn: Callable[[], str],
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
        return 0 if result.get("success", False) else 1
    except Exception as e:
        output_error_fn(f"{label} failed: {e}")
        return 1
