"""Configuration Drift Detector Tool — MCP Tool.

Detects hardcoded configuration values that should be externalized
via environment variables.
"""
from __future__ import annotations

from typing import Any

from ...analysis.config_drift import (
    ConfigDriftAnalyzer,
    ConfigDriftResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ConfigDriftTool(BaseMCPTool):
    """MCP tool for detecting configuration drift in code."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "config_drift",
            "description": (
                "Detect hardcoded configuration values that should be externalized. "
                "\n\n"
                "Finds module-level assignments where variable names match "
                "configuration patterns (host, port, url, timeout, api_key, etc.) "
                "but are assigned literal values instead of environment variables. "
                "Cross-references with env var usage in the same file to boost "
                "confidence."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Confidence Levels:\n"
                "- high: same file also uses env vars (os.getenv, process.env, etc.)\n"
                "- low: no env var usage detected in file\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find configuration that should be externalized\n"
                "- To audit deployment-readiness of configuration\n"
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

        analyzer = ConfigDriftAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: ConfigDriftResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_assignments": result.total_assignments,
            "issue_count": result.issue_count,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: ConfigDriftResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append(f"# Config Drift Analysis: {result.file_path}")
        lines.append(f"Total assignments scanned: {result.total_assignments}")
        lines.append(f"Config drift issues: {result.issue_count}")
        lines.append("")

        if not result.issues:
            lines.append("No hardcoded configuration detected.")
        else:
            for issue in result.issues:
                lines.append(f"## Line {issue.line_number}: {issue.variable_name}")
                lines.append(f"  Value: {issue.literal_value}")
                lines.append(f"  Confidence: {issue.confidence}")
                lines.append(f"  {issue.description}")
                lines.append(f"  Suggestion: {issue.suggestion}")
                lines.append("")

        return {
            "format": "toon",
            "content": "\n".join(lines),
        }
