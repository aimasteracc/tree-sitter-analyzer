"""Await-in-Loop Tool — MCP Tool.

Detects `await` expressions inside for/while loop bodies.
Serial async operations should use asyncio.gather() / Promise.all().
"""
from __future__ import annotations

from typing import Any

from ...analysis.await_in_loop import (
    AwaitInLoopAnalyzer,
    AwaitInLoopResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class AwaitInLoopTool(BaseMCPTool):
    """MCP tool for detecting await-in-loop anti-patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "await_in_loop",
            "description": (
                "Detect await expressions inside for/while loops — "
                "serial async that should run in parallel."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript\n"
                "\n"
                "Issue Types:\n"
                "- await_in_for_loop: `for x in items: await f(x)` "
                "(use asyncio.gather / Promise.all)\n"
                "- await_in_while_loop: `while cond: await f()` "
                "(consider concurrent design)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find async performance bottlenecks\n"
                "- To identify serial async that could be parallelized\n"
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

        analyzer = AwaitInLoopAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: AwaitInLoopResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_loops": result.total_loops,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: AwaitInLoopResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Await-in-Loop Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total loops: {result.total_loops}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context[:80]}"
                )
        else:
            lines.append("No await-in-loop issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
