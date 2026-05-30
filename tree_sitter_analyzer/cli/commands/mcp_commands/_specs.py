"""MCP_COMMAND_SPECS: combines core and extended spec tuples into one registry."""

from __future__ import annotations

from tree_sitter_analyzer.cli.commands.mcp_command_helpers import McpCommandSpec

from ._specs_core import _CORE_SPECS
from ._specs_extended import _EXTENDED_SPECS

MCP_COMMAND_SPECS: tuple[McpCommandSpec, ...] = _CORE_SPECS + _EXTENDED_SPECS
