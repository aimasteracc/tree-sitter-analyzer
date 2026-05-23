#!/usr/bin/env python3
"""CLI dispatchers for the cache/index trio: autoindex, full-index, metrics.

These three commands all wrap MCP tools (``codegraph_autoindex``,
``codegraph_full_index``, ``codegraph_metrics``). They live in a single
module because they share the same execution shape — instantiate tool,
build a kwargs dict, ``await tool.execute(...)``, print JSON or TOON.

Keeping them out of :mod:`tree_sitter_analyzer.cli.commands.mcp_commands`
avoids growing the already-large MCP_COMMAND_SPECS table and matches the
pattern set by ``constraint_check_command``: each new "named" command
gets its own dispatcher with explicit kwargs assembly.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any

OutputJsonFn = Callable[[dict[str, Any]], None]
OutputErrorFn = Callable[[str], None]


def _project_root(args: Any) -> str:
    return getattr(args, "project_root", None) or os.getcwd()


def _output_format(args: Any) -> str:
    """Map argparse-visible output format to MCP tool format."""
    fmt = getattr(args, "format", None) or getattr(args, "output_format", "json")
    return "toon" if fmt in {"toon", "text"} else "json"


def _print(result: dict[str, Any], output_format: str) -> None:
    """Write the MCP tool response to stdout in the requested shape."""
    if output_format == "toon":
        print(result.get("toon_content", ""))
    else:
        print(json.dumps(result, indent=2, default=str))


def _exit_code_for(result: dict[str, Any]) -> int:
    return 0 if result.get("success", False) else 1


def run_autoindex(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--autoindex`` → ``codegraph_autoindex`` MCP tool."""
    try:
        from ...mcp.tools.auto_index_tool import CodeGraphAutoIndexTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--autoindex failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphAutoIndexTool(project_root=_project_root(args))
    try:
        result = asyncio.run(
            tool.execute(
                {
                    "mode": getattr(args, "autoindex_mode", "status") or "status",
                    "max_files": int(getattr(args, "autoindex_max_files", 5000)),
                    "output_format": output_format,
                }
            )
        )
    except Exception as exc:  # noqa: BLE001
        output_error(f"--autoindex failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)


def run_full_index(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--full-index`` → ``codegraph_full_index`` MCP tool."""
    try:
        from ...mcp.tools.full_index_tool import CodeGraphFullIndexTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--full-index failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphFullIndexTool(project_root=_project_root(args))
    try:
        result = asyncio.run(
            tool.execute(
                {
                    "mode": getattr(args, "full_index_mode", "rebuild") or "rebuild",
                    "max_files": int(getattr(args, "full_index_max_files", 5000)),
                    "output_format": output_format,
                }
            )
        )
    except Exception as exc:  # noqa: BLE001
        output_error(f"--full-index failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)


def run_incremental_sync(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--incremental-sync`` → ``codegraph_incremental_sync`` MCP tool."""
    try:
        from ...mcp.tools.incremental_sync_tool import CodeGraphIncrementalSyncTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--incremental-sync failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphIncrementalSyncTool(project_root=_project_root(args))
    try:
        result = asyncio.run(
            tool.execute(
                {
                    "mode": getattr(args, "incremental_sync_mode", "sync") or "sync",
                    "max_files": int(getattr(args, "incremental_sync_max_files", 5000)),
                    "output_format": output_format,
                }
            )
        )
    except Exception as exc:  # noqa: BLE001
        output_error(f"--incremental-sync failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)


def run_codegraph_metrics(args: Any, output_error: OutputErrorFn) -> int:
    """Dispatch ``--codegraph-metrics`` → ``codegraph_metrics`` MCP tool."""
    try:
        from ...mcp.tools.codegraph_metrics_tool import CodeGraphMetricsTool
    except Exception as exc:  # noqa: BLE001
        output_error(f"--codegraph-metrics failed to import tool: {exc}")
        return 1

    output_format = _output_format(args)
    tool = CodeGraphMetricsTool(project_root=_project_root(args))
    payload: dict[str, Any] = {"output_format": output_format}
    sections = getattr(args, "codegraph_metrics_sections", None)
    if sections:
        payload["sections"] = list(sections)
    try:
        result = asyncio.run(tool.execute(payload))
    except Exception as exc:  # noqa: BLE001
        output_error(f"--codegraph-metrics failed: {exc}")
        return 1

    _print(result, output_format)
    return _exit_code_for(result)
