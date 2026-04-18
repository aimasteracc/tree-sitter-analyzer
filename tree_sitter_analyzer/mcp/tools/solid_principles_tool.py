"""SOLID Principles Analyzer Tool — MCP Tool.

Detects violations of the 5 SOLID design principles in source code.
Provides a per-principle score and actionable fix suggestions.
"""
from __future__ import annotations

from typing import Any

from ...analysis.solid_principles import (
    SOLIDPrinciplesAnalyzer,
    SOLIDResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SOLIDPrinciplesTool(BaseMCPTool):
    """MCP tool for analyzing SOLID principle violations."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "solid_principles",
            "description": (
                "Detect violations of the 5 SOLID design principles."
                "\n\n"
                "SOLID principles are the foundation of maintainable OOP code. "
                "This tool scans source files and flags specific violations "
                "with actionable fix suggestions."
                "\n\n"
                "Principles Checked:\n"
                "- SRP (Single Responsibility): classes with too many methods/lines\n"
                "- OCP (Open/Closed): isinstance/type-checking dispatch (HIGH)\n"
                "- LSP (Liskov Substitution): NotImplementedError in overrides\n"
                "- ISP (Interface Segregation): fat interfaces with too many methods\n"
                "- DIP (Dependency Inversion): imports of concrete implementations\n"
                "\n"
                "Supported Languages:\n"
                "- Python: all 5 principles\n"
                "- JavaScript/TypeScript: SRP, OCP, DIP\n"
                "- Java: SRP, OCP, ISP, DIP\n"
                "- Go: SRP, OCP, ISP\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to enforce OOP best practices\n"
                "- To identify refactoring targets in legacy code\n"
                "- To audit codebase health before major changes"
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

        analyzer = SOLIDPrinciplesAnalyzer()
        result = analyzer.analyze_file(resolved)

        if output_format == "toon":
            return self._format_toon(result)

        return self._format_json(result)

    def _format_json(self, result: SOLIDResult) -> dict[str, Any]:
        return {
            "result": result.to_dict(),
        }

    def _format_toon(self, result: SOLIDResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("SOLID Principles Analysis")
        lines.append("=" * 40)
        lines.append(f"File: {result.file_path}")
        lines.append(f"Language: {result.language}")
        lines.append(f"Overall Score: {result.overall_score:.1f}/100")
        lines.append("")

        lines.append("Principle Scores:")
        for s in result.principle_scores:
            status = "OK" if s.score == 100.0 else "VIOLATIONS"
            lines.append(f"  {s.principle}: {s.score:.1f} ({status})")
        lines.append("")

        if result.violations:
            lines.append(f"Violations ({len(result.violations)}):")
            for v in result.violations:
                lines.append(
                    f"  [{v.severity.upper()}] L{v.line_number}: "
                    f"{v.principle} - {v.element_name}"
                )
                lines.append(f"    {v.message}")
                lines.append(f"    Suggestion: {v.suggestion}")
        else:
            lines.append("No SOLID violations found.")

        from ...formatters.toon_encoder import ToonEncoder

        toon = ToonEncoder()
        content = "\n".join(lines)

        return {
            "content": [{"type": "text", "text": toon.encode(content)}],
            "summary": {
                "file_path": result.file_path,
                "language": result.language,
                "overall_score": round(result.overall_score, 1),
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
