#!/usr/bin/env python3
"""Helpers for MCP-equivalent CLI command dispatch."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpCommandSpec:
    """Declarative mapping from a CLI flag to an MCP-equivalent tool call."""

    flag_name: str
    tool_attr: str
    label: str
    build_tool_args: Callable[[Any, str], Mapping[str, Any]]
    required_file_error: str | None = None
    requires_file: Callable[[Any], bool] | None = None
    active_value: object = True


def find_selected_mcp_command(
    args: Any,
    command_specs: tuple[McpCommandSpec, ...],
) -> McpCommandSpec | None:
    """Return the first MCP command selected by parsed CLI args."""
    for spec in command_specs:
        value = getattr(args, spec.flag_name, False)
        if spec.active_value is True:
            if value:
                return spec
        elif value == spec.active_value:
            return spec
        elif spec.flag_name == "dependencies" and value:
            return spec
    if getattr(args, "watch", False):
        for spec in command_specs:
            if spec.flag_name == "ast_cache":
                return spec
    return None


def validate_mcp_command_args(
    args: Any,
    spec: McpCommandSpec,
    output_error_fn: Callable[[str], None],
) -> bool:
    """Validate selected MCP command arguments."""
    requires_file = bool(spec.required_file_error)
    if spec.requires_file is not None:
        requires_file = spec.requires_file(args)
    if (
        requires_file
        and spec.required_file_error
        and not getattr(args, "file_path", None)
    ):
        output_error_fn(spec.required_file_error)
        return False
    return True


def build_mcp_tool_args(
    args: Any, spec: McpCommandSpec, output_format: str
) -> dict[str, Any]:
    """Build concrete tool arguments for a selected MCP command."""
    return dict(spec.build_tool_args(args, output_format))
