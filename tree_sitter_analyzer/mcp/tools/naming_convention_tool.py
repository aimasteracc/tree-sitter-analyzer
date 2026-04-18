"""Naming Convention Analyzer Tool — MCP Tool.

Detects identifiers that violate language naming conventions.
Provides a naming quality score and actionable rename suggestions.
"""
from __future__ import annotations

from typing import Any

from ...analysis.naming_convention import (
    NamingConventionAnalyzer,
    NamingResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class NamingConventionTool(BaseMCPTool):
    """MCP tool for analyzing naming conventions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "naming_conventions",
            "description": (
                "Detect identifiers that violate language naming conventions."
                "\n\n"
                "Naming is the #1 readability factor in code. This tool checks "
                "that identifiers follow language-specific conventions and "
                "provides actionable rename suggestions."
                "\n\n"
                "Violations Detected:\n"
                "- single_letter_var: single-letter variable (except i/j/k) "
                "(MEDIUM)\n"
                "- language_violation: violates language convention (HIGH)\n"
                "- inconsistent_style: mixed naming styles in same file "
                "(MEDIUM)\n"
                "- upper_snake_not_const: UPPER_SNAKE for non-constant (LOW)\n"
                "\n"
                "Supported Languages:\n"
                "- Python: snake_case functions/vars, PascalCase classes\n"
                "- JavaScript/TypeScript: camelCase vars, PascalCase classes\n"
                "- Java: camelCase methods/vars, PascalCase classes\n"
                "- Go: PascalCase exported, camelCase unexported\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to enforce naming standards\n"
                "- To improve code readability before refactoring\n"
                "- To audit naming consistency across a project\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the source file to analyze",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "toon"],
                        "description": "Output format (default: json)",
                    },
                },
                "required": ["file_path"],
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        output_format = arguments.get("format", "json")

        resolved = self.resolve_and_validate_file_path(file_path)

        analyzer = NamingConventionAnalyzer()
        result = analyzer.analyze_file(resolved)

        if output_format == "toon":
            return self._format_toon(result)

        return self._format_json(result)

    def _format_json(self, result: NamingResult) -> dict[str, Any]:
        return {
            "result": result.to_dict(),
        }

    def _format_toon(self, result: NamingResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Naming Convention Analysis")
        lines.append("=" * 40)
        lines.append(f"File: {result.file_path}")
        lines.append(f"Language: {result.language}")
        lines.append(f"Total identifiers: {result.total_identifiers}")
        lines.append(f"Naming score: {result.naming_score:.1f}/100")
        lines.append("")

        if result.style_distribution:
            lines.append("Style Distribution:")
            for s in result.style_distribution:
                lines.append(f"  {s.style}: {s.count} ({s.percentage:.1f}%)")
            lines.append("")

        if result.violations:
            lines.append(f"Violations ({len(result.violations)}):")
            for v in result.violations:
                suggestion = f" -> {v.suggestion}" if v.suggestion else ""
                lines.append(
                    f"  [{v.severity.upper()}] L{v.line_number}: "
                    f"{v.name} ({v.violation_type}, "
                    f"{v.current_style} != {v.expected_style})"
                    f"{suggestion}"
                )
        else:
            lines.append("No naming violations found.")

        from ...formatters.toon_encoder import ToonEncoder

        toon = ToonEncoder()
        content = "\n".join(lines)

        return {
            "content": [{"type": "text", "text": toon.encode(content)}],
            "summary": {
                "file_path": result.file_path,
                "language": result.language,
                "naming_score": round(result.naming_score, 1),
                "violation_count": len(result.violations),
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "json")
        if fmt not in ("json", "toon"):
            raise ValueError(f"Invalid format: {fmt}")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path is required")
        return True
