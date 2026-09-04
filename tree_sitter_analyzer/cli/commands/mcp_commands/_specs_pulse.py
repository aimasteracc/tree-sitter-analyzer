"""MCP command specs: Pulse API / TQL / semantic — nervous-system PR facade parity.

These 6 capabilities were briefly registered as brand-new top-level MCP tools
(``pulse`` / ``pulse_batch`` / ``get_project_schema`` / ``tql_schema`` /
``tql_execute`` / ``semantic_neighbors``) before being re-wired as actions on
the existing ``nav`` / ``index`` / ``search`` facades. This module gives each
one its CLI-parity twin via the same ``McpCommandSpec`` pattern used for
``--symbol-lineage`` etc.
"""

from __future__ import annotations

import json

from tree_sitter_analyzer.cli.commands.mcp_command_helpers import McpCommandSpec

_PULSE_SPECS: tuple[McpCommandSpec, ...] = (
    McpCommandSpec(
        flag_name="pulse",
        tool_attr="PulseTool",
        label="Pulse: 1-query complete symbol context (nav action=pulse)",
        value_arg_name="pulse",
        required_value_error="--pulse requires a symbol name",
        required_file_error="--pulse requires a file path",
        build_tool_args=lambda args, output_format: {
            "file": args.file_path,
            "symbol": getattr(args, "pulse", "") or "",
        },
    ),
    McpCommandSpec(
        flag_name="pulse_batch",
        tool_attr="PulseBatchTool",
        label="Pulse batch: context for multiple symbols (nav action=pulse_batch)",
        value_arg_name="pulse_batch",
        required_value_error="--pulse-batch requires a JSON targets array",
        build_tool_args=lambda args, output_format: {
            "targets": json.loads(getattr(args, "pulse_batch", "") or "[]")
        },
    ),
    McpCommandSpec(
        flag_name="project_schema",
        tool_attr="GetProjectSchemaTool",
        label="Project schema: index statistics (index action=schema)",
        build_tool_args=lambda args, output_format: {},
    ),
    McpCommandSpec(
        flag_name="tql_schema",
        tool_attr="TqlSchemaTool",
        label="TQL DSL reference (search action=tql_schema)",
        build_tool_args=lambda args, output_format: {},
    ),
    McpCommandSpec(
        flag_name="tql",
        tool_attr="TqlExecuteTool",
        label="TQL selector execution (search action=tql_execute)",
        value_arg_name="tql",
        required_value_error="--tql requires a selector string",
        build_tool_args=lambda args, output_format: {
            "selector": getattr(args, "tql", "") or ""
        },
    ),
    McpCommandSpec(
        flag_name="semantic_neighbors",
        tool_attr="SemanticNeighborsTool",
        label="Semantic neighbor search (search action=semantic)",
        value_arg_name="semantic_neighbors",
        required_value_error="--semantic-neighbors requires a query string",
        build_tool_args=lambda args, output_format: {
            "query": getattr(args, "semantic_neighbors", "") or ""
        },
    ),
)

__all__ = ["_PULSE_SPECS"]
