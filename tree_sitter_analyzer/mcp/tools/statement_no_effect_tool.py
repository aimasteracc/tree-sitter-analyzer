"""Statement-with-No-Effect Tool — MCP Tool.

Detects expression statements that have no effect: comparisons used as
statements (x == 5;), discarded arithmetic, standalone literals.
"""
from __future__ import annotations

from typing import Any

from ...analysis.statement_no_effect import StatementNoEffectAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class StatementNoEffectTool(BaseMCPTool):
    """MCP tool for detecting no-effect expression statements."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "statement_no_effect",
            "description": (
                "Detect expression statements that have no effect: "
                "comparisons as statements (x == 5;), discarded arithmetic, "
                "standalone literals."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript, TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- comparison_as_statement: x == 5; (likely meant x = 5;)\n"
                "- arithmetic_as_statement: a + b; (result discarded)\n"
                "- literal_as_statement: standalone literal with no effect\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find accidental == instead of = in statements\n"
                "- To catch discarded expression results\n"
                "- To detect useless literal statements\n"
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

        analyzer = StatementNoEffectAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_statements": result.total_statements,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Statement No-Effect Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total expression statements: {result.total_statements}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} no-effect statement(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No no-effect statements found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
