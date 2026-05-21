#!/usr/bin/env python3
"""Helpers for MCP-equivalent CLI command dispatch."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpCommandSpec:
    """Declarative mapping from a CLI flag to an MCP-equivalent tool call.

    ``value_arg_name`` (M12): for flags that take a *value* on the command
    line (e.g. ``--symbol-lineage SYMBOL``), set this to the attribute
    holding the user-supplied value (typically the same as
    :attr:`flag_name`). When set, the command is considered *selected*
    whenever the value is not ``None`` — including empty strings — so
    ``--symbol-lineage ""`` routes into the dispatcher and emits a
    canonical validation envelope instead of falling through to the
    file-analysis path and dumping the argparse usage block.

    ``required_value_error`` (M12): error message used when
    ``value_arg_name`` is provided but evaluates to an empty / whitespace
    string. Surfaces as the canonical ``{success: False,
    error_type: "validation", ...}`` JSON envelope when the caller asked
    for ``--format json``.
    """

    flag_name: str
    tool_attr: str
    label: str
    build_tool_args: Callable[[Any, str], Mapping[str, Any]]
    required_file_error: str | None = None
    requires_file: Callable[[Any], bool] | None = None
    active_value: object = True
    value_arg_name: str | None = None
    required_value_error: str | None = None


def _spec_value(args: Any, spec: McpCommandSpec) -> Any:
    """Return the user-facing value associated with the spec's flag.

    For value-bearing flags (``value_arg_name`` set) we look up the
    actual argparse attribute; for boolean flags we keep the legacy
    ``flag_name`` lookup so the rest of the dispatcher is unchanged.
    """
    if spec.value_arg_name is not None:
        return getattr(args, spec.value_arg_name, None)
    return getattr(args, spec.flag_name, False)


def find_selected_mcp_command(
    args: Any,
    command_specs: tuple[McpCommandSpec, ...],
) -> McpCommandSpec | None:
    """Return the first MCP command selected by parsed CLI args.

    Selection rules:

    - Boolean flags (``active_value=True``): selected when the
      attribute is truthy.
    - Value-bearing flags (``value_arg_name`` set): selected whenever
      the attribute is not ``None`` — empty strings still count so the
      dispatcher (not argparse) emits the validation envelope.
    - Choice flags (``active_value != True``): selected when the
      attribute equals the configured ``active_value``.
    - ``dependencies``: legacy shape — selected on any truthy value.
    """
    for spec in command_specs:
        # Value-bearing flag (M12): empty string still counts as selected
        # so we can emit a canonical envelope instead of crashing.
        # Only ``str`` values qualify — tests that build a synthetic
        # ``Namespace`` with ``symbol_lineage=False`` to denote
        # "this flag was NOT provided" must not accidentally trigger
        # the empty-string envelope path.
        if spec.value_arg_name is not None:
            value = getattr(args, spec.value_arg_name, None)
            if isinstance(value, str):
                return spec
            continue

        value = getattr(args, spec.flag_name, False)
        if spec.active_value is True:
            if value:
                return spec
        elif value == spec.active_value:
            return spec
        elif spec.flag_name == "dependencies" and value:
            return spec
    return None


def validate_mcp_command_args(
    args: Any,
    spec: McpCommandSpec,
    output_error_fn: Callable[[str], None],
) -> bool:
    """Validate selected MCP command arguments.

    Two pre-execution checks:

    1. ``required_file_error``: command needs a positional ``file_path``
       but none was supplied.
    2. ``required_value_error`` (M12): a value-bearing flag was
       supplied but evaluates to an empty / whitespace-only string
       (e.g. ``--symbol-lineage ""``). Caught here so JSON callers get a
       canonical envelope and shell ``set -e`` pipelines see ``RC=1``.
    """
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
    if spec.value_arg_name is not None and spec.required_value_error:
        raw = getattr(args, spec.value_arg_name, None)
        if not (isinstance(raw, str) and raw.strip()):
            output_error_fn(spec.required_value_error)
            return False
    return True


def build_mcp_tool_args(
    args: Any, spec: McpCommandSpec, output_format: str
) -> dict[str, Any]:
    """Build concrete tool arguments for a selected MCP command."""
    return dict(spec.build_tool_args(args, output_format))
