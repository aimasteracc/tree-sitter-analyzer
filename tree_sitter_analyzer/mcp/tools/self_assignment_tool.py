"""Self-Assignment Tool — MCP Tool.

Detects self-assignments where a variable or member is assigned to itself
(e.g., x = x, self.x = self.x), which is always a no-op or a typo.
"""
from __future__ import annotations

from typing import Any

from ...analysis.self_assignment import (
    SelfAssignmentAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SelfAssignmentTool(BaseMCPTool):
    """MCP tool for detecting self-assignments."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "self_assignment",
            "description": (
                "Detect self-assignments: variable assigned to itself "
                "(x = x, self.x = self.x, this.x = this.x)."
                "\n\n"
                "Self-assignments are always dead code and often "
                "indicate copy-paste errors or incomplete refactoring."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Go\n"
                "\n"
                "Issue Types:\n"
                "- self_assign: x = x\n"
                "- self_assign_member: self.x = self.x / this.x = this.x\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find accidental self-assignments\n"
                "- To catch copy-paste errors in assignments\n"
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

        analyzer = SelfAssignmentAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_assignments": result.total_assignments,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Self-Assignment Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total assignments: {result.total_assignments}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} self-assignment(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No self-assignments found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
