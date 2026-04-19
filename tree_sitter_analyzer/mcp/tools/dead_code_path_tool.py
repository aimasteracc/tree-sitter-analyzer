"""Dead Code Path Tool — MCP Tool.

Analyzes functions for unreachable code paths. Detects
code after terminal statements (return/raise/break/continue)
and dead branches (if False, if True...else).
"""
from __future__ import annotations

from typing import Any

from ...analysis.dead_code_path import (
    DeadCodePathAnalyzer,
    DeadCodePathResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DeadCodePathTool(BaseMCPTool):
    """MCP tool for analyzing dead code paths."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "dead_code_path",
            "description": (
                "Analyze functions for unreachable code paths. "
                "\n\n"
                "Detects code after terminal statements (return, raise, break, "
                "continue, throw, panic) and dead branches (if False, if True...else). "
                "Complements dead_code which detects unused definitions."
                "\n\n"
                "Supported Languages:\n"
                "- Python: function definitions\n"
                "- JavaScript/TypeScript: function declarations\n"
                "- Java: method and constructor declarations\n"
                "- Go: function and method declarations\n"
                "\n"
                "Issue Types:\n"
                "- unreachable_code: statements after return/raise/break/continue\n"
                "- dead_branch: if False body, if True else branch\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find code that can never execute\n"
                "- To detect dead branches and redundant conditionals\n"
                "- As a complement to dead_code (unused definitions)\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For unused imports/variables (use dead_code)\n"
                "- For return path consistency (use return_path)\n"
                "- For code clone detection (use code_clones)"
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

        analyzer = DeadCodePathAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: DeadCodePathResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: DeadCodePathResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Dead Code Path Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total functions: {result.total_functions}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] [{i.severity}] "
                    f"{i.description}"
                )
        else:
            lines.append("No dead code path issues found.")

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
