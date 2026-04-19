"""Double Negation Tool — MCP Tool.

Analyzes code for unnecessary double negation patterns.
"""
from __future__ import annotations

from typing import Any

from ...analysis.double_negation import (
    DoubleNegationAnalyzer,
    DoubleNegationResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DoubleNegationTool(BaseMCPTool):
    """MCP tool for detecting double negation patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "double_negation",
            "description": (
                "Analyze code for unnecessary double negation patterns."
                "\n\n"
                "Detects:\n"
                "- double_not: 'not not x' (Python) — use bool(x)\n"
                "- double_bang: '!!x' (JS/TS/Java) — use Boolean(x)\n"
                "- not_not_parens: 'not (not x)' (Python) — use bool(x)\n"
                "\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find confusing double negation patterns\n"
                "- To improve boolean expression readability\n"
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

        analyzer = DoubleNegationAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: DoubleNegationResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_unary_ops": result.total_unary_ops,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: DoubleNegationResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Double Negation Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total unary operators: {result.total_unary_ops}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} double negation issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: [{i.issue_type}] {i.description}"
                )
        else:
            lines.append("No double negation issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_unary_ops": result.total_unary_ops,
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
