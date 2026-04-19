"""Dead Store Tool — MCP Tool.

Analyzes code for dead store issues. Detects variables that are assigned
but whose value is never read before reassignment or scope exit.
"""
from __future__ import annotations

from typing import Any

from ...analysis.dead_store import (
    DeadStoreAnalyzer,
    DeadStoreResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DeadStoreTool(BaseMCPTool):
    """MCP tool for analyzing dead stores."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "dead_store",
            "description": (
                "Analyze code for dead store issues. "
                "\n\n"
                "Detects variables that are assigned but whose value is "
                "never read, indicating dead code, incomplete refactoring, "
                "or hidden bugs."
                "\n\n"
                "Supported Languages:\n"
                "- Python: functions, lambdas\n"
                "- JavaScript/TypeScript: functions, arrow functions, methods\n"
                "- Java: methods, constructors, lambdas\n"
                "- Go: functions, methods, func literals\n"
                "\n"
                "Issue Types:\n"
                "- dead_store: value assigned but never read (medium)\n"
                "- self_assignment: variable assigned to itself (high)\n"
                "- immediate_reassignment: variable reassigned before first read (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find dead code from incomplete refactoring\n"
                "- To catch self-assignment bugs (x = x)\n"
                "- To detect redundant assignments that waste computation\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze."
                        ),
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

        analyzer = DeadStoreAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: DeadStoreResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: DeadStoreResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Dead Store Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total functions: {result.total_functions}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} dead store issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}] '{i.variable_name}'"
                )
        else:
            lines.append("No dead store issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
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
