"""Speculative Generality Tool — MCP Tool.

Analyzes code for premature abstractions: abstract classes with few
implementations, unused type parameters, and overly broad interfaces.
"""
from __future__ import annotations

from typing import Any

from ...analysis.speculative_generality import (
    SpeculativeGeneralityAnalyzer,
    SpeculativeGeneralityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SpeculativeGeneralityTool(BaseMCPTool):
    """MCP tool for detecting speculative generality."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "speculative_generality",
            "description": (
                "Detect premature abstractions and over-engineering in code. "
                "\n\n"
                "Finds abstract classes with 0-1 implementations, unused type "
                "parameters, abstract methods never overridden, and overly "
                "broad interfaces."
                "\n\n"
                "Supported Languages:\n"
                "- Python: ABC classes, abstractmethod decorators\n"
                "- JavaScript/TypeScript: abstract classes, interfaces\n"
                "- Java: abstract classes, interfaces\n"
                "- Go: interfaces\n"
                "\n"
                "Issue Types:\n"
                "- speculative_abstract_class: abstract with 0-1 impls (high)\n"
                "- unused_type_parameter: generic param never used (medium)\n"
                "- unused_hook: abstract method never overridden (medium)\n"
                "- overly_broad_interface: interface with 5+ methods (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot premature abstractions\n"
                "- To find YAGNI violations (You Ain't Gonna Need It)\n"
                "- To simplify over-engineered codebases\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For inheritance quality (use inheritance_quality)\n"
                "- For lazy class detection (use lazy_class)\n"
                "- For god class detection (use god_class)"
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
                    "broad_threshold": {
                        "type": "integer",
                        "description": "Minimum abstract methods for overly_broad (default: 5)",
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
        broad_threshold = arguments.get("broad_threshold", 5)

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = SpeculativeGeneralityAnalyzer(broad_threshold=int(broad_threshold))
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: SpeculativeGeneralityResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_types": result.total_types,
            "issue_count": result.total_issues,
            "high_severity_count": result.high_severity_count,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: SpeculativeGeneralityResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Speculative Generality Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total types: {result.total_types}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: {i.name} "
                    f"[{i.issue_type}] [{i.severity}]"
                )
                lines.append(f"    {i.message}")
        else:
            lines.append("No speculative generality issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_types": result.total_types,
            "issue_count": result.total_issues,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
