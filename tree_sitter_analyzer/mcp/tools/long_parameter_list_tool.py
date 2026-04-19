"""Long Parameter List Tool — MCP Tool.

Detects functions/methods with too many parameters.
"""
from __future__ import annotations

from typing import Any

from ...analysis.long_parameter_list import (
    DEFAULT_THRESHOLD,
    LongParameterListAnalyzer,
    LongParameterResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class LongParameterListTool(BaseMCPTool):
    """MCP tool for detecting functions with too many parameters."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "long_parameter_list",
            "description": (
                "Detect functions/methods with too many parameters. "
                "Default threshold: 5 params, excessive: 8+."
                "\n\n"
                "Long parameter lists are a classic code smell from "
                "Fowler's catalog — they suggest the function does too "
                "much or should use a parameter object."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- many_params: 5-7 parameters\n"
                "- excessive_params: 8+ parameters\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find functions that need refactoring\n"
                "- To enforce parameter count limits\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a specific file to analyze.",
                    },
                    "threshold": {
                        "type": "integer",
                        "description": f"Minimum parameter count to flag (default: {DEFAULT_THRESHOLD})",
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
        threshold = arguments.get("threshold", DEFAULT_THRESHOLD)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = LongParameterListAnalyzer(threshold=threshold)
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: LongParameterResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "max_params": result.max_params,
            "avg_params": round(result.avg_params, 2),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: LongParameterResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Long Parameter List Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total functions: {result.total_functions}")
        lines.append(f"Max params: {result.max_params}, Avg: {result.avg_params:.1f}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} function(s) with too many parameters:")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: {issue.function_name}() — "
                    f"{issue.param_count} params [{issue.severity}]"
                )
        else:
            lines.append("No functions with excessive parameters found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
