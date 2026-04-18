"""Variable Mutability Tool — MCP Tool.

Analyzes variable mutability issues: shadow variables, unused assignments,
constant reassignments, and iteration mutations.
"""
from __future__ import annotations

from typing import Any

from ...analysis.variable_mutability import (
    MutabilityResult,
    VariableMutabilityAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class VariableMutabilityTool(BaseMCPTool):
    """MCP tool for analyzing variable mutability issues."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "variable_mutability",
            "description": (
                "Analyze variable mutability issues: detect shadow variables, "
                "unused assignments, constant reassignments, and loop mutations."
                "\n\n"
                "Fills the gap between naming_convention (naming style) and "
                "coupling_metrics (module-level) by analyzing variable-level "
                "behavior within functions."
                "\n\n"
                "Issues Detected:\n"
                "- shadow_variable: inner scope redeclares outer variable (MEDIUM)\n"
                "- unused_assignment: variable assigned but never used (LOW)\n"
                "- reassigned_constant: UPPER_SNAKE variable reassigned (HIGH)\n"
                "- mutation_in_iteration: loop modifies outer-scope variable (MEDIUM)\n"
                "\n"
                "Supported Languages:\n"
                "- Python: assignments, for/while loops\n"
                "- JavaScript/TypeScript: var/let/const, for/while loops\n"
                "- Java: local variables, for/while loops\n"
                "- Go: short var declarations, for loops\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to find hidden mutation bugs\n"
                "- After naming_convention to verify variable behavior\n"
                "- To find dead code (unused assignments)\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For naming style checks (use naming_convention)\n"
                "- For module coupling analysis (use coupling_metrics)\n"
                "- For test assertion quality (use assertion_quality)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a source file to analyze for "
                            "variable mutability issues."
                        ),
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "json", "toon"],
                        "description": "Output format (default: text)",
                        "default": "text",
                    },
                },
                "required": ["file_path"],
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        output_format = arguments.get("format", "text")

        analyzer = VariableMutabilityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return {"result": self._to_json(result)}
        if output_format == "toon":
            return {"content": [{"type": "text", "text": self._to_toon(result)}]}
        return {"content": [{"type": "text", "text": self._to_text(result)}]}

    def _to_text(self, result: MutabilityResult) -> str:
        lines: list[str] = [
            f"Variable Mutability Analysis: {result.file_path}",
            f"Issues: {result.total_issues} | Score: {result.quality_score:.0f}/100",
            "",
        ]

        if result.issue_counts:
            lines.append("Issue Summary:")
            for issue_type, count in sorted(result.issue_counts.items()):
                lines.append(f"  {issue_type}: {count}")
            lines.append("")

        for issue in result.issues:
            lines.append(
                f"  [{issue.severity.upper()}] L{issue.line}: {issue.issue_type} "
                f"({issue.variable_name})"
            )
            lines.append(f"    {issue.description}")
            lines.append(f"    Suggestion: {issue.suggestion}")

        return "\n".join(lines)

    def _to_json(self, result: MutabilityResult) -> dict[str, Any]:
        return {
            "file_path": result.file_path,
            "total_issues": result.total_issues,
            "quality_score": result.quality_score,
            "issue_counts": result.issue_counts,
            "issues": [
                {
                    "type": i.issue_type,
                    "line": i.line,
                    "column": i.column,
                    "variable_name": i.variable_name,
                    "severity": i.severity,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in result.issues
            ],
        }

    def _to_toon(self, result: MutabilityResult) -> str:
        encoder = ToonEncoder()
        data = self._to_json(result)
        return encoder.encode(data)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "text")
        if fmt not in ("text", "json", "toon"):
            raise ValueError(f"Invalid output format: {fmt}")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path is required")
        return True
