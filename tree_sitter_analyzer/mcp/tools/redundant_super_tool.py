"""Redundant Super Call Tool — MCP Tool.

Analyzes code for unnecessary super() calls in constructors.
"""
from __future__ import annotations

from typing import Any

from ...analysis.redundant_super import (
    RedundantSuperAnalyzer,
    RedundantSuperResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class RedundantSuperTool(BaseMCPTool):
    """MCP tool for detecting redundant super() calls in constructors."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "redundant_super",
            "description": (
                "Analyze code for redundant super() calls in constructors. "
                "\n\n"
                "Detects constructors that only call super() without additional logic, "
                "or pass all parameters through to super() unchanged."
                "\n\n"
                "Supported Languages:\n"
                "- Python: super().__init__() in class __init__\n"
                "- JavaScript/TypeScript: super() in class constructor\n"
                "- Java: super() in constructor\n"
                "\n"
                "Issue Types:\n"
                "- redundant_super_init: constructor body is ONLY super() call (low)\n"
                "- passthrough_super_init: params passed to super() unchanged (info)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find unnecessary constructor boilerplate\n"
                "- To reduce code noise in class hierarchies\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a specific file to analyze.",
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default) or json",
                        "enum": ["toon", "json"],
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = RedundantSuperAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: RedundantSuperResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_constructors": result.total_constructors,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: RedundantSuperResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Redundant Super Call Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Constructors: {result.total_constructors}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} redundant super issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}] {i.function_name}"
                )
        else:
            lines.append("No redundant super issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_constructors": result.total_constructors,
            "issue_count": len(result.issues),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
