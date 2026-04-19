"""Function Redefinition Tool — MCP Tool.

Detects functions defined multiple times in the same scope.
"""
from __future__ import annotations

from typing import Any

from ...analysis.function_redefinition import FunctionRedefinitionAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class FunctionRedefinitionTool(BaseMCPTool):
    """MCP tool for detecting function redefinitions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "function_redefinition",
            "description": (
                "Detect functions defined multiple times in the same "
                "scope, where the later definition silently replaces "
                "the earlier one."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript, TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- function_redefinition: same function name in same scope\n"
                "- method_redefinition: same method name in same class\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find accidentally duplicated function definitions\n"
                "- To catch copy-paste errors in method definitions\n"
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

        analyzer = FunctionRedefinitionAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Function Redefinition Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total functions: {result.total_functions}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} redefinition(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No function redefinitions found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
