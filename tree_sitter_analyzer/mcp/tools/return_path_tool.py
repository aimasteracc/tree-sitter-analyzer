"""
Return Path Tool — MCP Tool.

Analyzes return paths of functions. Detects inconsistent returns where
some branches return a value while others fall through to implicit None.
Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.return_path import (
    ReturnPathAnalyzer,
    ReturnPathResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ReturnPathTool(BaseMCPTool):
    """MCP tool for analyzing return paths of functions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "return_path",
            "description": (
                "Analyze return paths of functions and methods. "
                "\n\n"
                "Detects functions where some code paths return a value "
                "while others fall through to implicit None, a common "
                "source of bugs in dynamically-typed languages."
                "\n\n"
                "Supported Languages:\n"
                "- Python: return/yield/raise in functions/methods\n"
                "- JavaScript/TypeScript: return/throw in functions/methods/arrow\n"
                "- Java: return/throw in methods/constructors\n"
                "- Go: return in func/methods\n"
                "\n"
                "Issue Types:\n"
                "- inconsistent_return: some paths return value, others don't\n"
                "- implicit_none: function can reach end without returning\n"
                "- empty_return: bare return while other paths return values\n"
                "- complex_return_path: more than 5 return points\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to catch inconsistent returns\n"
                "- To find potential None/undefined return bugs\n"
                "- To identify overly complex return logic\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For code smell detection (use code_smell_detector)\n"
                "- For function size analysis (use function_size)\n"
                "- For complexity scoring (use cognitive_complexity)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file."
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

        analyzer = ReturnPathAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: ReturnPathResult) -> dict[str, Any]:
        issue_fns = result.get_functions_with_issues()
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "functions_with_issues": result.functions_with_issues,
            "total_issues": result.total_issues,
            "issues": [
                {
                    "function": f.name,
                    "type": f.element_type,
                    "start_line": f.start_line,
                    "end_line": f.end_line,
                    "return_count": f.return_count,
                    "value_returns": f.value_returns,
                    "empty_returns": f.empty_returns,
                    "has_implicit_none": f.has_implicit_none,
                    "issues": [
                        {
                            "type": issue.issue_type,
                            "severity": issue.severity,
                            "line": issue.line_number,
                            "message": issue.message,
                        }
                        for issue in f.issues
                    ],
                }
                for f in issue_fns
            ],
            "all_functions": [
                {
                    "name": f.name,
                    "type": f.element_type,
                    "start_line": f.start_line,
                    "return_count": f.return_count,
                    "has_issues": len(f.issues) > 0,
                }
                for f in result.functions
            ],
        }

    def _format_toon(self, result: ReturnPathResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Return Path Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Functions: {result.total_functions}")
        lines.append(f"Functions with issues: {result.functions_with_issues}")
        lines.append(f"Total issues: {result.total_issues}")
        lines.append("")

        issue_fns = result.get_functions_with_issues()
        if issue_fns:
            lines.append("Issues found:")
            for f in issue_fns:
                lines.append(
                    f"  {f.name} ({f.element_type}, "
                    f"L{f.start_line}-L{f.end_line}):"
                )
                for issue in f.issues:
                    lines.append(
                        f"    [{issue.severity}] {issue.issue_type}: "
                        f"{issue.message}"
                    )
        else:
            lines.append("No return path issues detected.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "functions_with_issues": result.functions_with_issues,
            "total_issues": result.total_issues,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
