"""Switch Smells Tool — MCP Tool.

Analyzes switch/match/select statements for code smells.
Detects complex switches that should use polymorphism.
"""
from __future__ import annotations

from typing import Any

from ...analysis.switch_smells import (
    SwitchSmellAnalyzer,
    SwitchSmellResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SwitchSmellsTool(BaseMCPTool):
    """MCP tool for analyzing switch statement smells."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "switch_smells",
            "description": (
                "Analyze switch/match/select statements for code smells. "
                "\n\n"
                "Detects complex switch statements that may indicate missed "
                "polymorphism opportunities. Counts cases, checks for "
                "defaults, and flags statements with too many branches."
                "\n\n"
                "Supported Languages:\n"
                "- Python: match statement\n"
                "- JavaScript/TypeScript: switch\n"
                "- Java: switch statement/expression\n"
                "- Go: switch/select/type-switch\n"
                "\n"
                "Smell Detection:\n"
                "- too_many_cases: 5+ cases (consider polymorphism)\n"
                "- missing_default: 4+ cases without default\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot complex switches\n"
                "- To identify polymorphism refactoring opportunities\n"
                "- As a design pattern complement to solid_principles\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a specific file to analyze.",
                    },
                    "threshold": {
                        "type": "integer",
                        "description": (
                            "Case count threshold. Switches at or above "
                            "this count are flagged. Default: 5."
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
        threshold = arguments.get("threshold", 5)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = SwitchSmellAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result, threshold)
        return self._format_toon(result, threshold)

    def _format_json(
        self, result: SwitchSmellResult, threshold: int
    ) -> dict[str, Any]:
        smelly = [
            s for s in result.switches if s.case_count >= threshold or s.smell_type != "none"
        ]
        return {
            "file": result.file_path,
            "total_switches": result.total_switches,
            "smelly_switches": result.smelly_switches,
            "switches": [
                {
                    "line": s.line_number,
                    "cases": s.case_count,
                    "has_default": s.has_default,
                    "smell": s.smell_type,
                    "type": s.statement_type,
                }
                for s in smelly
            ],
        }

    def _format_toon(
        self, result: SwitchSmellResult, threshold: int
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Switch Smell Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total: {result.total_switches}")
        lines.append(f"Smelly: {result.smelly_switches}")
        lines.append("")

        if result.smelly_switches > 0:
            for s in result.switches:
                if s.smell_type != "none":
                    lines.append(
                        f"  L{s.line_number}: {s.statement_type} "
                        f"({s.case_count} cases, {s.smell_type})"
                    )
        else:
            lines.append("No switch smells detected.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_switches": result.total_switches,
            "smelly_switches": result.smelly_switches,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")
        return True
