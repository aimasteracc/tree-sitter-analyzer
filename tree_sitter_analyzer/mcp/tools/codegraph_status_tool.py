#!/usr/bin/env python3
"""
CodeGraph Status MCP Tool — INDEX HEALTH at-a-glance (CodeGraph parity).

Consolidates ast_cache + codegraph_autoindex + check_tools signals into a
single read-only call so agents know whether the index is ready, how stale
it is, and where to look. Replaces 3-4 separate tool calls.
"""

from __future__ import annotations

from typing import Any

from .base_tool import BaseMCPTool


class CodeGraphStatusTool(BaseMCPTool):
    """MCP Tool for index health at-a-glance (CodeGraph parity)."""

    def __init__(
        self, project_root: str | None = None, *, read_existing_default: bool = False
    ) -> None:
        self._read_existing_default = read_existing_default
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_status",
            "description": (
                "INDEX HEALTH at-a-glance (CodeGraph parity). "
                "One call returns: indexed yes/no, total files, total symbols, "
                "schema version, FTS5 availability, cache lag vs newest source. "
                "Use BEFORE any codegraph_* navigation call to decide whether to "
                "warm the cache first. Replaces ast_cache + codegraph_autoindex "
                "+ check_tools triangulation."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_lag": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Compare cache timestamp against newest source file mtime "
                        "to estimate index lag"
                    ),
                },
                "access_mode": {
                    "type": "string",
                    "enum": ["read_existing"],
                    "default": "read_existing",
                    "description": "Open only an existing compatible index, without writes",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format (default: toon)",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        include_lag = arguments.get("include_lag", True)
        if not isinstance(include_lag, bool):
            raise ValueError("include_lag must be a boolean")
        access_mode = arguments.get("access_mode")
        if access_mode not in (None, "read_existing"):
            raise ValueError("access_mode must be read_existing")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "toon")
        # Status is unconditionally read-only.  JSON Schema defaults are not
        # injected by every direct caller, so omission must be handled here.
        return self._execute_read_existing(
            output_format, include_lag=arguments.get("include_lag", True)
        )

    def _execute_read_existing(
        self, output_format: str, *, include_lag: bool
    ) -> dict[str, Any]:
        """Delegate response construction to the focused status boundary."""
        from ...index_status_response import build_index_status_response

        return build_index_status_response(
            self.project_root, output_format, include_lag=include_lag
        )
