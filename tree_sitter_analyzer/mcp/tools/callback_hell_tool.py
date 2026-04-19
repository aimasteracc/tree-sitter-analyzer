"""Callback Hell Tool — MCP Tool.

Analyzes code for callback hell patterns. Detects deeply nested callbacks
and long promise chains that should be refactored.
"""
from __future__ import annotations

from typing import Any

from ...analysis.callback_hell import (
    CallbackHellAnalyzer,
    CallbackHellResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CallbackHellTool(BaseMCPTool):
    """MCP tool for analyzing callback hell patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "callback_hell",
            "description": (
                "Analyze code for callback hell patterns. "
                "\n\n"
                "Detects deeply nested callbacks and long promise chains "
                "that make code unreadable and unmaintainable."
                "\n\n"
                "Supported Languages:\n"
                "- Python: nested functions, lambdas\n"
                "- JavaScript/TypeScript: nested callbacks, .then() chains\n"
                "- Java: nested lambda expressions\n"
                "- Go: nested func literals\n"
                "\n"
                "Issue Types:\n"
                "- callback_hell: 4+ nested callbacks (critical)\n"
                "- deep_callback: 3 nested callbacks (warning)\n"
                "- promise_chain_hell: 4+ chained .then() calls (critical)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find callback hell in async code\n"
                "- To detect nested callbacks that need async/await refactoring\n"
                "- To find long .then() chains in JavaScript\n"
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

        analyzer = CallbackHellAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: CallbackHellResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_callbacks": result.total_callbacks,
            "max_depth": result.max_depth,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: CallbackHellResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Callback Hell Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total callbacks: {result.total_callbacks}")
        lines.append(f"Max nesting depth: {result.max_depth}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} callback hell issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}] depth={i.depth}"
                )
        else:
            lines.append("No callback hell issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_callbacks": result.total_callbacks,
            "max_depth": result.max_depth,
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
