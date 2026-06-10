"""Handlers for RFC-0014 nav facade special commands (--test-map, --co-change)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a circular import; only needed for annotations
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext


def _dispatch_test_map(
    args: Any,
    context: SpecialCommandContext,
    facade: Any,
    output_format: str,
) -> int:
    """Dispatch --test-map action."""
    tool_args: dict[str, Any] = {
        "action": "test_map",
        "symbol": getattr(args, "test_map", None),
        "output_format": output_format,
    }
    file_path = getattr(args, "test_map_file", None)
    if file_path:
        tool_args["file_path"] = file_path
    return _execute_nav_facade(facade, tool_args, output_format, "--test-map", context)


def _dispatch_co_change(
    args: Any,
    context: SpecialCommandContext,
    facade: Any,
    output_format: str,
) -> int:
    """Dispatch --co-change action."""
    tool_args = {
        "action": "co_change",
        "file_path": getattr(args, "co_change", None),
        "max_commits": getattr(args, "co_change_max_commits", 500),
        "output_format": output_format,
    }
    return _execute_nav_facade(facade, tool_args, output_format, "--co-change", context)


def _execute_nav_facade(
    facade: Any,
    tool_args: dict[str, Any],
    output_format: str,
    label: str,
    context: SpecialCommandContext,
) -> int:
    """Execute nav facade tool and handle output."""
    import asyncio

    try:
        result: dict[str, Any] = asyncio.run(facade.execute(tool_args))
        if output_format == "toon":
            import sys

            print(result.get("toon_content", ""), file=sys.stdout)
        else:
            context.output_json(result)
        return 0 if result.get("success", False) else 1
    except Exception as exc:  # noqa: BLE001
        context.output_error(f"{label} failed: {exc}")
        return 1


def handle_nav_actions(
    args: Any,
    context: SpecialCommandContext,
) -> int | None:
    """Dispatch RFC-0014 nav facade actions: --test-map and --co-change.

    Both are bespoke routes on the nav facade, never registered as legacy
    v1.x tool names -- they never go through the MCP_COMMAND_SPECS table.
    """
    test_map_symbol = getattr(args, "test_map", None)
    co_change_target = getattr(args, "co_change", None)

    if test_map_symbol is None and co_change_target is None:
        return None

    from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

    project_root = getattr(args, "project_root", None) or os.getcwd()
    output_format = getattr(args, "output_format", "json") or "json"
    facade = build_nav_facade(project_root=project_root)

    if test_map_symbol is not None:
        return _dispatch_test_map(args, context, facade, output_format)
    return _dispatch_co_change(args, context, facade, output_format)
