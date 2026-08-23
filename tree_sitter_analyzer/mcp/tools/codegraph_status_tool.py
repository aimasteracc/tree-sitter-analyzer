#!/usr/bin/env python3
"""
CodeGraph Status MCP Tool — INDEX HEALTH at-a-glance (CodeGraph parity).

Consolidates ast_cache + codegraph_autoindex + check_tools signals into a
single read-only call so agents know whether the index is ready, how stale
it is, and where to look. Replaces 3-4 separate tool calls.
"""

from __future__ import annotations

from typing import Any

from ...read_existing_access import (
    classify_index_access,
    validate_read_existing_access,
    validate_read_existing_schema_values,
)
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
                    "enum": ["json"],
                    "default": "json",
                    "description": "Output format (default: toon)",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        include_lag = arguments.get("include_lag", True)
        if not isinstance(include_lag, bool):
            raise ValueError("include_lag must be a boolean")
        validate_read_existing_access(arguments)
        validate_read_existing_schema_values(self, arguments)
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        output_format = arguments.get("output_format", "json")
        # Status is unconditionally read-only.  JSON Schema defaults are not
        # injected by every direct caller, so omission must be handled here.
        include_access_evidence = "access_mode" in arguments
        result = self._execute_read_existing(
            output_format,
            include_lag=arguments.get("include_lag", True),
            include_access_evidence=include_access_evidence,
        )
        if not include_access_evidence or "access_state" in result:
            return result
        # Preserve lightweight monkeypatch/test seams that return the older P0.1
        # payload even when the new keyword is accepted.
        return self._with_access_evidence(result, output_format)

    @staticmethod
    def _with_access_evidence(
        result: dict[str, Any], output_format: str
    ) -> dict[str, Any]:
        """Classify the P0.1 oracle without changing its action-specific fields."""
        # Production adds evidence inside the focused status boundary before
        # formatting. This fallback keeps older monkeypatch/test seams additive.
        evidence = classify_index_access(
            snapshot_id=result.get("snapshot_id"),
            source_generation=result.get("source_generation"),
            completeness=result.get("completeness"),
            reason=result.get("oracle_reason"),
        )
        enriched = {**result, **evidence}
        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(enriched, output_format)

    def _execute_read_existing(
        self,
        output_format: str,
        *,
        include_lag: bool,
        include_access_evidence: bool = False,
    ) -> dict[str, Any]:
        """Delegate response construction to the focused status boundary."""
        from ...index_status_response import build_index_status_response

        return build_index_status_response(
            self.project_root,
            output_format,
            include_lag=include_lag,
            include_access_evidence=include_access_evidence,
        )
