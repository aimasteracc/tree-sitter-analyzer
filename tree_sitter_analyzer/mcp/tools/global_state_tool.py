"""Global State Tool — MCP Tool.

Analyzes code for module-level mutable state, global/nonlocal keyword
usage, static mutable fields, and package-level variables.
"""
from __future__ import annotations

from typing import Any

from ...analysis.global_state import GlobalStateAnalyzer, GlobalStateResult
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class GlobalStateTool(BaseMCPTool):
    """MCP tool for analyzing global/module-level mutable state."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "global_state",
            "description": (
                "Analyze code for global/module-level mutable state. "
                "\n\n"
                "Detects module-level mutable variables, global/nonlocal keyword usage, "
                "static non-final fields (Java), and package-level variables (Go). "
                "These patterns create hidden coupling and testability issues."
                "\n\n"
                "Supported Languages:\n"
                "- Python: module-level assignments, global, nonlocal\n"
                "- JavaScript/TypeScript: top-level var/let, assignments outside function\n"
                "- Java: static non-final fields\n"
                "- Go: package-level variables (not constants)\n"
                "\n"
                "Issue Types:\n"
                "- global_state: Module-level mutable variable (medium)\n"
                "- global_keyword: `global` statement in function (high)\n"
                "- nonlocal_keyword: `nonlocal` statement in function (high)\n"
                "- static_mutable: Static non-final field (medium)\n"
                "- package_var: Package-level variable (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find hidden mutable state that makes testing difficult\n"
                "- To audit code for global state anti-patterns\n"
                "- Before refactoring to understand state dependencies\n"
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

        analyzer = GlobalStateAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: GlobalStateResult) -> dict[str, Any]:
        return result.to_dict()

    def _format_toon(self, result: GlobalStateResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Global State Analysis")
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
            lines.append("No global state issues found.")

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
