"""Debug Statement Tool — MCP Tool.

Analyzes code for leftover debug output statements that should be removed
before production deployment.
"""
from __future__ import annotations

from typing import Any

from ...analysis.debug_statement import (
    DebugStatementDetector,
    DebugStatementResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DebugStatementTool(BaseMCPTool):
    """MCP tool for detecting leftover debug statements."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "debug_statement",
            "description": (
                "Analyze code for leftover debug output statements. "
                "\n\n"
                "Detects print(), console.log(), System.out.println(), "
                "fmt.Println() and similar debug output that should be "
                "removed before production."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- debug_print: print/pprint/breakpoint calls (Python)\n"
                "- debug_log: console.* calls, debugger statements (JS/TS)\n"
                "- debug_println: System.out/err.println, printStackTrace (Java)\n"
                "- debug_formatter: fmt.Print*, log.Println (Go)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find forgotten debug output before release\n"
                "- To audit code for debug statements in production paths\n"
                "- To catch print statements that may leak sensitive data\n"
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

        analyzer = DebugStatementDetector()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: DebugStatementResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_count": result.total_count,
            "by_type": result.by_type,
            "statements": [s.to_dict() for s in result.statements],
        }

    def _format_toon(self, result: DebugStatementResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Debug Statement Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Debug statements: {result.total_count}")
        lines.append("")

        if result.statements:
            lines.append(f"Found {result.total_count} debug statement(s):")
            for stmt in result.statements:
                lines.append(
                    f"  L{stmt.line}: [{stmt.severity}] "
                    f"{stmt.function_name}() — {stmt.message}"
                )
        else:
            lines.append("No debug statements found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_count": result.total_count,
        }
