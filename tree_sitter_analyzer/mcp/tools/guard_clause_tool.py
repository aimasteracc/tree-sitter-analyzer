"""Guard Clause Opportunity Tool — MCP Tool.

Analyzes code for if/else blocks where the else branch only exits while the
if branch does substantial work. These are guard clause refactoring candidates.
"""
from __future__ import annotations

from typing import Any

from ...analysis.guard_clause import (
    GuardClauseAnalyzer,
    GuardClauseResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class GuardClauseTool(BaseMCPTool):
    """MCP tool for detecting guard clause refactoring opportunities."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "guard_clause",
            "description": (
                "Analyze code for guard clause refactoring opportunities. "
                "\n\n"
                "Detects if/else blocks where the else branch only contains "
                "a return/raise/throw/break/continue while the if branch "
                "has substantial work. Inverting the condition and returning "
                "early flattens the code."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- guard_clause_opportunity: inverted control flow that could "
                "be simplified with early return (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find code that could be flattened with guard clauses\n"
                "- To improve readability by reducing unnecessary nesting\n"
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
                "required": ["file_path"],
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

        analyzer = GuardClauseAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: GuardClauseResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_ifs": result.total_ifs,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: GuardClauseResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append(f"# Guard Clause Analysis: {result.file_path}")
        lines.append(f"Total if statements: {result.total_ifs}")
        lines.append(f"Opportunities found: {len(result.issues)}")
        lines.append("")

        if not result.issues:
            lines.append("No guard clause opportunities detected.")
        else:
            for issue in result.issues:
                lines.append(f"## Line {issue.line_number}: {issue.issue_type}")
                lines.append(f"  Description: {issue.description}")
                lines.append(f"  If-body statements: {issue.if_body_lines}")
                lines.append(f"  Suggestion: {issue.suggestion}")
                lines.append("")

        return {
            "format": "toon",
            "content": "\n".join(lines),
        }
