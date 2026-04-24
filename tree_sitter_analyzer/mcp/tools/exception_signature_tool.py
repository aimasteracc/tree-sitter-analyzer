"""Exception Signature Tool — MCP Tool.

Analyzes functions to extract exception signatures and check documentation.
"""
from __future__ import annotations

from typing import Any

from ...analysis.exception_signature import (
    ExceptionSignatureAnalyzer,
    ExceptionSignatureResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ExceptionSignatureTool(BaseMCPTool):
    """MCP tool for extracting function exception signatures and checking docs."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "exception_signature",
            "description": (
                "Analyze functions to extract exception signatures and check "
                "documentation consistency."
                "\n\n"
                "For each function, identifies exceptions that can escape "
                "(not caught internally) and checks whether they are documented "
                "in docstrings (:raises), JSDoc (@throws), or Javadoc (@throws)."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go (partial)\n"
                "\n"
                "Finding Types:\n"
                "- exception_signature (info): complete list of exceptions a "
                "function can throw\n"
                "- undocumented_exception (medium): function throws exception "
                "but it is not documented\n"
                "\n"
                "WHEN TO USE:\n"
                "- To understand what exceptions a function can throw\n"
                "- To find undocumented exceptions that callers should handle\n"
                "- To help LLMs understand the hidden contract between caller "
                "and callee\n"
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
                "required": ["file_path"],
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

        analyzer = ExceptionSignatureAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: ExceptionSignatureResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "functions_scanned": result.functions_scanned,
            "total_findings": result.total_findings,
            "by_type": dict(result.by_type),
            "issues": [
                {
                    "finding_type": i.finding_type,
                    "severity": i.severity,
                    "message": i.message,
                    "line_number": i.line_number,
                    "function_name": i.function_name,
                    "exception_types": list(i.exception_types),
                }
                for i in result.issues
            ],
        }

    def _format_toon(self, result: ExceptionSignatureResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append(f"# Exception Signature Analysis: {result.file_path}")
        lines.append(f"Functions scanned: {result.functions_scanned}")
        lines.append(f"Findings: {result.total_findings}")
        lines.append("")

        if not result.issues:
            lines.append("No exception signature issues detected.")
        else:
            for issue in result.issues:
                lines.append(
                    f"## L{issue.line_number}: {issue.function_name}"
                    f" [{issue.finding_type}]"
                )
                lines.append(f"  {issue.message}")
                if issue.exception_types:
                    lines.append(
                        f"  Exceptions: {', '.join(issue.exception_types)}"
                    )
                if issue.suggestion:
                    lines.append(f"  Suggestion: {issue.suggestion}")
                lines.append("")

        return {
            "format": "toon",
            "content": "\n".join(lines),
        }
