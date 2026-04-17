#!/usr/bin/env python3
"""
Refactoring Suggestions Tool — MCP Tool

Provides actionable, step-by-step guidance to fix code quality issues.
Generates specific refactoring suggestions with before/after examples.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.refactoring_suggestions import (
    RefactoringAdvisor,
    RefactoringReport,
)
from ...language_detector import detect_language_from_file
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class RefactoringSuggestionsTool(BaseMCPTool):
    """
    MCP tool for generating refactoring suggestions.

    Provides actionable, step-by-step guidance to fix code quality issues
    detected by code_smell_detector. Instead of just reporting problems,
    it generates specific refactoring steps with before/after examples.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.advisor = RefactoringAdvisor()

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "refactoring_suggestions",
            "description": (
                "Generate actionable refactoring suggestions for code quality issues. "
                "\n\n"
                "Provides step-by-step guidance to fix code smells with before/after examples. "
                "Instead of just reporting problems, it generates specific refactoring steps.\n\n"
                "Refactoring Patterns:\n"
                "- Extract Method: Break down long methods into smaller, focused functions\n"
                "- Guard Clauses: Reduce nesting by returning early for edge cases\n"
                "- Extract Constant: Replace magic numbers with named constants\n"
                "- Extract Class: Split large classes with too many responsibilities\n"
                "- Convert to Arrow Function: Modernize JavaScript with arrow syntax\n"
                "- Extract Interface: Improve polymorphism in Java/Go/C#\n"
                "- Modernize Async: Fix async/await patterns in C#\n\n"
                "Supported Languages:\n"
                "- Python: functions, classes, methods\n"
                "- JavaScript/TypeScript: functions, classes, arrow functions\n"
                "- Java: classes, methods, interfaces\n"
                "- Go: functions, structs, interfaces\n"
                "- C#: classes, methods, async/await\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the source file to analyze",
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "File content (optional, will read from file_path if not provided)"
                        ),
                    },
                    "language": {
                        "type": "string",
                        "description": (
                            "Programming language (auto-detected from file_path if not provided)"
                        ),
                        "enum": [
                            "python",
                            "javascript",
                            "typescript",
                            "java",
                            "go",
                            "csharp",
                            "ruby",
                            "rust",
                            "kotlin",
                        ],
                    },
                    "min_severity": {
                        "type": "string",
                        "description": "Minimum severity level to include",
                        "enum": ["info", "low", "medium", "high", "critical"],
                        "default": "low",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["toon", "json", "summary"],
                        "description": "Output format: toon (emoji), json (structured), or summary (text)",
                        "default": "toon",
                    },
                },
                "required": ["file_path"],
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        language = arguments.get("language")
        if language is not None:
            valid_languages = {
                "python",
                "javascript",
                "typescript",
                "java",
                "go",
                "csharp",
                "ruby",
                "rust",
                "kotlin",
            }
            if language not in valid_languages:
                raise ValueError(
                    f"language must be one of {valid_languages}, got '{language}'"
                )

        min_severity = arguments.get("min_severity")
        if min_severity is not None:
            valid_severities = {"info", "low", "medium", "high", "critical"}
            if min_severity not in valid_severities:
                raise ValueError(
                    f"min_severity must be one of {valid_severities}, got '{min_severity}'"
                )

        output_format = arguments.get("output_format")
        if output_format is not None:
            valid_formats = {"toon", "json", "summary"}
            if output_format not in valid_formats:
                raise ValueError(
                    f"output_format must be one of {valid_formats}, got '{output_format}'"
                )

        return True

    @handle_mcp_errors("refactoring_suggestions")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the refactoring suggestions tool.

        Args:
            arguments: Tool arguments from the MCP protocol

        Returns:
            Formatted refactoring suggestions
        """
        file_path = arguments.get("file_path", "")
        content = arguments.get("content")
        language = arguments.get("language")
        min_severity = arguments.get("min_severity", "low")
        output_format = arguments.get("output_format", "toon")

        # Resolve file path
        resolved_path = self.resolve_and_validate_file_path(file_path)

        # Read file content if not provided
        if content is None:
            try:
                path = Path(resolved_path)
                content = path.read_text(encoding="utf-8")
            except Exception as e:
                return {
                    "error": f"Error reading file: {e}",
                    "file_path": file_path,
                }

        # Detect language if not provided
        if language is None:
            language = detect_language_from_file(resolved_path)

        # Generate suggestions
        report: RefactoringReport = self.advisor.suggest_fixes(
            file_path=resolved_path,
            content=content,
            language=language,
        )

        # Filter by severity if specified
        if min_severity != "info":
            severity_order = ["info", "low", "medium", "high", "critical"]
            min_index = severity_order.index(min_severity)
            report.suggestions = [
                s for s in report.suggestions
                if severity_order.index(s.severity.value) >= min_index
            ]
            report.total_suggestions = len(report.suggestions)

        # Format output
        if output_format == "json":
            return {
                "format": "json",
                "file_path": file_path,
                "language": language,
                "suggestions": report.to_dict(),
            }
        elif output_format == "summary":
            return {
                "format": "summary",
                "file_path": file_path,
                "language": language,
                "suggestions": self._format_summary(report),
            }
        else:  # toon
            return {
                "format": "toon",
                "file_path": file_path,
                "language": language,
                "suggestions": self._format_toon(report, language),
            }

    def _format_summary(self, report: RefactoringReport) -> str:
        """Format report as text summary."""
        lines = [
            f"# Refactoring Suggestions: {report.file_path}",
            f"Total suggestions: {report.total_suggestions}",
            f"Critical: {report.critical_count}, High: {report.high_count}, Medium: {report.medium_count}",
            "",
        ]

        if report.total_suggestions == 0:
            lines.append("✅ No refactoring suggestions - code looks good!")
            return "\n".join(lines)

        lines.append("## Suggestions")
        lines.append("")

        for i, suggestion in enumerate(report.suggestions, 1):
            lines.append(f"{i}. **{suggestion.title}** ({suggestion.severity.value})")
            lines.append(f"   {suggestion.description}")
            lines.append(f"   Lines: {suggestion.line_start}-{suggestion.line_end}")
            lines.append(f"   Effort: {suggestion.estimated_effort}")
            lines.append("")

        return "\n".join(lines)

    def _format_toon(self, report: RefactoringReport, language: str) -> str:
        """Format report as TOON."""
        lines = [
            "🔧 Refactoring Suggestions",
            f"📄 {report.file_path}",
            f"🔤 {language}",
            "",
            "📊 Summary",
            f"  Total: {report.total_suggestions}",
            f"  Critical: {report.critical_count} 🔴",
            f"  High: {report.high_count} 🟠",
            f"  Medium: {report.medium_count} 🟡",
            "",
        ]

        if report.total_suggestions == 0:
            lines.append("✅ No refactoring suggestions - code looks good!")
            return "\n".join(lines)

        lines.append("💡 Suggestions")
        lines.append("")

        for i, suggestion in enumerate(report.suggestions, 1):
            emoji = self._severity_emoji(suggestion.severity.value)
            lines.append(f"{i}. {emoji} **{suggestion.title}**")
            lines.append(f"   {suggestion.description}")
            lines.append(f"   📍 Lines: {suggestion.line_start}-{suggestion.line_end}")
            lines.append(f"   ⏱️  Effort: {suggestion.estimated_effort}")

            if suggestion.code_diff:
                lines.append(f"   ```{language}")
                lines.append("   # Before")
                before_lines = suggestion.code_diff.before.split("\n")[:3]
                lines.extend(f"   {line}" for line in before_lines)
                lines.append("   # After")
                after_lines = suggestion.code_diff.after.split("\n")[:3]
                lines.extend(f"   {line}" for line in after_lines)
                lines.append("   ```")

            lines.append("")

        return "\n".join(lines)

    def _severity_emoji(self, severity: str) -> str:
        """Get emoji for severity level."""
        emoji_map = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }
        return emoji_map.get(severity, "⚪")
