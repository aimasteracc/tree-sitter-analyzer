"""
Feature Envy Tool — MCP Tool.

Detects methods that access other objects' data more than their own class.
"""
from __future__ import annotations

from typing import Any

from ...analysis.feature_envy import (
    FeatureEnvyAnalyzer,
    FeatureEnvyResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class FeatureEnvyTool(BaseMCPTool):
    """MCP tool for analyzing feature envy in methods."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "feature_envy",
            "description": (
                "Analyze methods for feature envy and misplaced responsibilities. "
                "\n\n"
                "Detects methods that access foreign object data more than their "
                "own class, suggesting the method belongs elsewhere."
                "\n\n"
                "Supported Languages:\n"
                "- Python: self vs foreign object attribute access\n"
                "- JavaScript/TypeScript: this vs foreign object property access\n"
                "- Java: this vs foreign object field/method access\n"
                "- Go: receiver vs other struct field access\n"
                "\n"
                "Detection Patterns:\n"
                "- feature_envy: method accesses foreign data more than own (HIGH)\n"
                "- method_chain: excessive chained calls through foreign objects (MEDIUM)\n"
                "- inappropriate_intimacy: two classes access each other's internals (LOW)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to identify misplaced methods\n"
                "- When planning refactoring of class responsibilities\n"
                "- Before restructuring class hierarchies\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For coupling metrics (use coupling_metrics)\n"
                "- For design pattern detection (use design_patterns)\n"
                "- For architectural boundary analysis (use architectural_boundary)"
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

        analyzer = FeatureEnvyAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: FeatureEnvyResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "language": result.language,
            "total_issues": result.total_issues,
            "high_severity": result.high_severity,
            "medium_severity": result.medium_severity,
            "low_severity": result.low_severity,
            "issues": [
                {
                    "type": i.issue_type,
                    "line": i.line,
                    "severity": i.severity,
                    "class_name": i.class_name,
                    "method_name": i.method_name,
                    "foreign_object": i.foreign_object,
                    "self_accesses": i.self_accesses,
                    "foreign_accesses": i.foreign_accesses,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in result.issues
            ],
        }

    def _format_toon(self, result: FeatureEnvyResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Feature Envy Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Language: {result.language}")
        lines.append(f"Issues: {result.total_issues}")
        if result.high_severity > 0:
            lines.append(f"  HIGH: {result.high_severity}")
        if result.medium_severity > 0:
            lines.append(f"  MEDIUM: {result.medium_severity}")
        if result.low_severity > 0:
            lines.append(f"  LOW: {result.low_severity}")
        lines.append("")

        if result.issues:
            for i in result.issues:
                lines.append(
                    f"  [{i.severity.upper()}] {i.issue_type}: "
                    f"L{i.line} in {i.class_name}.{i.method_name}() "
                    f"- {i.description}"
                )
                lines.append(
                    f"    Foreign: {i.foreign_object} "
                    f"(self={i.self_accesses}, foreign={i.foreign_accesses})"
                )
                lines.append(f"    Suggestion: {i.suggestion}")
        else:
            lines.append("No feature envy issues detected.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_issues": result.total_issues,
            "high_severity": result.high_severity,
            "medium_severity": result.medium_severity,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
