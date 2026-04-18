"""Resource Lifecycle Analyzer Tool — MCP Tool.

Detects resource management issues: missing context managers,
unclosed resources, and missing cleanup in error paths.
"""
from __future__ import annotations

from typing import Any

from ...analysis.resource_lifecycle import (
    ResourceLifecycleAnalyzer,
    ResourceLifecycleResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ResourceLifecycleTool(BaseMCPTool):
    """MCP tool for detecting resource lifecycle issues."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "resource_lifecycle",
            "description": (
                "Detect resource management issues: missing context managers, "
                "unclosed files/streams, and missing cleanup in error paths."
                "\n\n"
                "Checks resource acquisition patterns:\n"
                "- Python: open() without 'with' statement\n"
                "- Java: streams/connections without try-with-resources\n"
                "- TypeScript/JS: fs.open() without proper cleanup\n"
                "- C#: IDisposable without 'using' statement\n"
                "\n"
                "Risk Levels:\n"
                "- HIGH: resource acquired with no cleanup mechanism\n"
                "- MEDIUM: resource in try but no finally cleanup\n"
                "- LOW: resource has cleanup but could be safer\n"
                "\n"
                "WHEN TO USE:\n"
                "- Before deployment to catch resource leaks\n"
                "- During code review of file/DB/network operations\n"
                "- To audit legacy code for resource management issues"
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

        if not file_path:
            raise ValueError("file_path is required")

        resolved = self._resolve_path(file_path)
        analyzer = ResourceLifecycleAnalyzer()
        result = analyzer.analyze_file(resolved)

        if output_format == "toon":
            return self._format_toon(result)

        return self._format_json(result)

    def _resolve_path(self, file_path: str) -> str:
        if self.project_root:
            from pathlib import Path
            resolved = Path(self.project_root) / file_path
            if resolved.exists():
                return str(resolved)
        return file_path

    def _format_json(self, result: ResourceLifecycleResult) -> dict[str, Any]:
        return {
            "result": result.to_dict(),
        }

    def _format_toon(self, result: ResourceLifecycleResult) -> dict[str, Any]:
        from ...formatters.toon_encoder import ToonEncoder

        lines: list[str] = []
        lines.append("Resource Lifecycle Analysis")
        lines.append("=" * 40)
        lines.append(f"File: {result.file_path}")
        lines.append(
            f"Safety: {result.stats.safety_percentage:.1f}% "
            f"({result.stats.safe_acquisitions}/{result.stats.total_acquisitions} safe)"
        )
        lines.append("")

        if result.issues:
            lines.append(f"Issues ({len(result.issues)}):")
            for issue in result.issues:
                lines.append(
                    f"  [{issue.risk}] L{issue.line}: {issue.description}"
                )
            lines.append("")

            high = sum(1 for i in result.issues if i.risk == "HIGH")
            medium = sum(1 for i in result.issues if i.risk == "MEDIUM")
            low = sum(1 for i in result.issues if i.risk == "LOW")
            if high or medium:
                lines.append(f"Summary: {high} HIGH, {medium} MEDIUM, {low} LOW")
        else:
            lines.append("No resource lifecycle issues detected.")

        toon = ToonEncoder()
        content = "\n".join(lines)
        return {
            "content": [{"type": "text", "text": toon.encode(content)}],
            "summary": {
                "file_path": result.file_path,
                "safety_percentage": round(result.stats.safety_percentage, 1),
                "issue_count": len(result.issues),
                "high_risk_count": sum(1 for i in result.issues if i.risk == "HIGH"),
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path is required")
        fmt = arguments.get("format", "json")
        if fmt not in ("json", "toon"):
            raise ValueError(f"Invalid format: {fmt}")
        return True
