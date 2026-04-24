"""Query Method Mutation Tool — MCP Tool.

Detects methods whose names suggest read-only queries (get*, is*, has*,
check*, find*, can*, should*, validate*) but that modify object state,
violating the Command-Query Separation principle.
"""
from __future__ import annotations

from typing import Any

from ...analysis.query_mutation import (
    QueryMutationAnalyzer,
    QueryMutationResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class QueryMutationTool(BaseMCPTool):
    """MCP tool for detecting CQS violations in query-named methods."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "query_mutation",
            "description": (
                "Detect query-named methods that mutate object state "
                "(Command-Query Separation violations)."
                "\n\n"
                "Finds methods named get*, is*, has*, check*, find*, "
                "can*, should*, validate* that write to self/this fields."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- query_method_mutation: query-named method modifies "
                "object state\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find subtle bugs from hidden state changes\n"
                "- To enforce Command-Query Separation principle\n"
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

        analyzer = QueryMutationAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: QueryMutationResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_issues": result.total_issues,
            "issue_count": len(result.issues),
            "issues": [
                {
                    "line": i.line,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "method_name": i.method_name,
                    "field_name": i.field_name,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in result.issues
            ],
        }

    def _format_toon(self, result: QueryMutationResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Query Method Mutation Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} CQS violation(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.method_name} modifies {issue.field_name}"
                )
        else:
            lines.append("No query method mutations found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
