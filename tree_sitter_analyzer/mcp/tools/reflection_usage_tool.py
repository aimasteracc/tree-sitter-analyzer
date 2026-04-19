"""Reflection Usage Tool — MCP Tool.

Detects reflection and dynamic code execution patterns that make code
hard to audit, test, and secure.
"""
from __future__ import annotations

from typing import Any

from ...analysis.reflection_usage import (
    ReflectionResult,
    ReflectionUsageAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ReflectionUsageTool(BaseMCPTool):
    """MCP tool for detecting reflection and dynamic code execution patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "reflection_usage",
            "description": (
                "Detect reflection and dynamic code execution patterns. "
                "\n\n"
                "Finds eval/exec/getattr/compile in Python, eval/Function in JS/TS, "
                "Class.forName/Method.invoke in Java, reflect.* in Go. "
                "These patterns make code hard to audit, test, and secure."
                "\n\n"
                "Supported Languages:\n"
                "- Python: eval, exec, compile, getattr, setattr, delattr, hasattr, __import__\n"
                "- JavaScript/TypeScript: eval, new Function\n"
                "- Java: Class.forName, newInstance, invoke, getDeclaredMethod, setAccessible\n"
                "- Go: reflect.DeepEqual, reflect.ValueOf, reflect.TypeOf, etc.\n"
                "\n"
                "Issue Types:\n"
                "- dynamic_execution: eval/exec/compile (high)\n"
                "- dynamic_access: getattr/setattr/delattr/hasattr (medium)\n"
                "- reflection: Class.forName/invoke/reflect.* (medium/high)\n"
                "\n"
                "WHEN TO USE:\n"
                "- Security audits to find dangerous dynamic code execution\n"
                "- To identify reflection patterns that hinder testability\n"
                "- Before refactoring to understand dynamic dependencies\n"
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
            return {"error": "file_path must be provided", "format": output_format}

        analyzer = ReflectionUsageAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: ReflectionResult) -> dict[str, Any]:
        return result.to_dict()

    def _format_toon(self, result: ReflectionResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Reflection Usage Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total findings: {len(result.findings)}")
        lines.append("")

        if result.findings:
            for f in result.findings:
                lines.append(
                    f"  L{f.line}: [{f.issue_type}] [{f.severity}] "
                    f"{f.name} — {f.description}"
                )
        else:
            lines.append("No reflection/dynamic code patterns found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_findings": len(result.findings),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
