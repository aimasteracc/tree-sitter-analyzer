"""Import Shadowing Tool — MCP Tool.

Detects when imported names are shadowed by subsequent assignments,
which silently replaces module references with arbitrary values.
"""
from __future__ import annotations

from typing import Any

from ...analysis.import_shadowing import (
    ImportShadowingAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ImportShadowingTool(BaseMCPTool):
    """MCP tool for detecting import shadowing."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "import_shadowing",
            "description": (
                "Detect import shadowing: imported names reassigned "
                "later in the same file."
                "\n\n"
                "Shadowed imports silently replace module references, "
                "causing confusing runtime errors."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- shadowed_import: import x; x = something\n"
                "- shadowed_from_import: from y import x; x = something\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find accidental import shadowing\n"
                "- To catch naming conflicts between imports and variables\n"
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

        analyzer = ImportShadowingAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_imports": result.total_imports,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Import Shadowing Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total imports: {result.total_imports}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} shadowed import(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No import shadowing found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
