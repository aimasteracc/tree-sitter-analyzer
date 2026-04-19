"""Hardcoded IP Tool — MCP Tool.

Analyzes code for hardcoded IP addresses and port numbers that should be
externalized to configuration files or environment variables.
"""
from __future__ import annotations

from typing import Any

from ...analysis.hardcoded_ip import (
    HardcodedIPAnalyzer,
    HardcodedIPResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class HardcodedIPTool(BaseMCPTool):
    """MCP tool for detecting hardcoded IP addresses and port numbers."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "hardcoded_ip",
            "description": (
                "Analyze code for hardcoded IP addresses and port numbers. "
                "\n\n"
                "Detects network configuration values that should be "
                "externalized to config files, environment variables, or DNS."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- hardcoded_ip: IP address literal in source code (medium)\n"
                "- hardcoded_port: Port number in port-like variable (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find hardcoded IPs before deployment\n"
                "- To audit configuration externalization\n"
                "- To catch environment-specific values in code\n"
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

        analyzer = HardcodedIPAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: HardcodedIPResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_ips": result.total_ips,
            "total_ports": result.total_ports,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: HardcodedIPResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Hardcoded IP Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"IPs found: {result.total_ips}")
        lines.append(f"Ports found: {result.total_ports}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} hardcoded config issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}] '{i.value}'"
                )
        else:
            lines.append("No hardcoded IP/port issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_ips": result.total_ips,
            "total_ports": result.total_ports,
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
