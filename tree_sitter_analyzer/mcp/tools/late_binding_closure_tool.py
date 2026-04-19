"""Late-Binding Closure Tool — MCP Tool.

Detects closures inside loops that capture loop variables by reference,
causing the closure to always see the final loop value.
"""
from __future__ import annotations

from typing import Any

from ...analysis.late_binding_closure import LateBindingClosureAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class LateBindingClosureTool(BaseMCPTool):
    """MCP tool for detecting late-binding closure bugs."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "late_binding_closure",
            "description": (
                "Detect closures inside loops that capture loop variables "
                "by reference (lambda: i in loop, var + function in JS/TS)."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript, TypeScript, Java\n"
                "\n"
                "Issue Types:\n"
                "- late_binding_lambda: lambda in loop captures loop variable\n"
                "- late_binding_func: function expression in loop captures variable\n"
                "- late_binding_arrow: arrow function in loop captures variable\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find closures that always see the last loop value\n"
                "- To catch classic lambda-in-loop Python bug\n"
                "- To detect var-based closure issues in JavaScript\n"
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

        analyzer = LateBindingClosureAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_closures": result.total_closures,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Late-Binding Closure Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total closures in loops: {result.total_closures}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} late-binding closure(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No late-binding closure issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
