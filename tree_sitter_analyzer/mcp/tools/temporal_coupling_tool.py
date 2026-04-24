"""Temporal Coupling Tool — MCP Tool.

Detects hidden method ordering dependencies within classes.
"""
from __future__ import annotations

from typing import Any

from ...analysis.temporal_coupling import (
    TemporalCouplingAnalyzer,
    TemporalCouplingResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class TemporalCouplingTool(BaseMCPTool):
    """MCP tool for detecting temporal coupling between methods."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "temporal_coupling",
            "description": (
                "Detect temporal coupling: methods that read instance "
                "variables written only by other methods."
                "\n\n"
                "Identifies hidden ordering dependencies: if method A reads "
                "self.x and only method B writes self.x, then A must be "
                "called after B — a temporal coupling invisible in the type system."
                "\n\n"
                "Supported Languages:\n"
                "- Python: self.X access in methods\n"
                "- JavaScript/TypeScript: this.X access in methods\n"
                "- Java: this.X access in methods\n"
                "- Go: receiver.X access in methods\n"
                "\n"
                "Issue Types:\n"
                "- temporal_coupling: reader method depends on writer method (medium)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find hidden ordering dependencies\n"
                "- To identify methods that must be called in a specific order\n"
                "- To improve class design for testability\n"
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

        analyzer = TemporalCouplingAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: TemporalCouplingResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_classes": result.total_classes,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: TemporalCouplingResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Temporal Coupling Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Classes analyzed: {result.total_classes}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} temporal coupling issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  {issue.reader_method} reads .{issue.variable_name} "
                    f"(written only by {issue.writer_method})"
                )
        else:
            lines.append("No temporal coupling issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_classes": result.total_classes,
            "issue_count": len(result.issues),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
