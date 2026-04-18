"""Exception Handling Quality Tool — MCP Tool.

Analyzes exception handling quality in production code: detects broad catches,
swallowed exceptions, and missing error context.
"""
from __future__ import annotations

from typing import Any

from ...analysis.exception_quality import (
    ExceptionQualityAnalyzer,
    ExceptionQualityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ExceptionQualityTool(BaseMCPTool):
    """MCP tool for analyzing exception handling quality."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "exception_quality",
            "description": (
                "Analyze exception handling quality: detect broad catches, "
                "swallowed exceptions, and missing error context."
                "\n\n"
                "Fills the gap between logging_patterns (log-level detection) "
                "and error_handling (recovery patterns) by examining WHAT "
                "exception handlers actually do."
                "\n\n"
                "Quality Issues Detected:\n"
                "- broad_catch: catches overly wide exception type (MEDIUM)\n"
                "- swallowed_exception: empty handler, silently swallowing (HIGH)\n"
                "- missing_context: raises without preserving original (MEDIUM)\n"
                "- generic_error_message: hardcoded error string (LOW)\n"
                "\n"
                "Supported Languages:\n"
                "- Python: try/except\n"
                "- JavaScript/TypeScript: try/catch\n"
                "- Java: try/catch/finally\n"
                "- Go: defer/recover\n"
                "\n"
                "WHEN TO USE:\n"
                "- After logging_patterns to find unhandled error paths\n"
                "- During code review to find silent failures\n"
                "- After error_handling to verify quality of handlers\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For recovery pattern detection (use error_handling)\n"
                "- For logging quality (use logging_patterns)\n"
                "- For test assertion quality (use assertion_quality)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a source file to analyze for "
                            "exception handling quality."
                        ),
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "json", "toon"],
                        "description": "Output format (default: text)",
                        "default": "text",
                    },
                },
                "required": ["file_path"],
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        output_format = arguments.get("format", "text")

        analyzer = ExceptionQualityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return {"result": self._to_json(result)}
        if output_format == "toon":
            return {"content": [{"type": "text", "text": self._to_toon(result)}]}
        return {"content": [{"type": "text", "text": self._to_text(result)}]}

    def _to_text(self, result: ExceptionQualityResult) -> str:
        lines: list[str] = [
            f"Exception Quality Analysis: {result.file_path}",
            f"Try blocks: {result.total_try_blocks} | Issues: {result.total_issues} | Score: {result.quality_score:.0f}/100",
            "",
        ]

        if result.issue_counts:
            lines.append("Issue Summary:")
            for issue_type, count in sorted(result.issue_counts.items()):
                lines.append(f"  {issue_type}: {count}")
            lines.append("")

        for block in result.try_blocks:
            lines.append(
                f"  try block (L{block.start_line}-{block.end_line}): "
                f"{block.handler_count} handlers"
            )
            for issue in block.issues:
                lines.append(
                    f"    [{issue.severity.upper()}] L{issue.line}: {issue.issue_type}"
                )
                lines.append(f"      {issue.description}")
                lines.append(f"      Suggestion: {issue.suggestion}")

        return "\n".join(lines)

    def _to_json(self, result: ExceptionQualityResult) -> dict[str, Any]:
        return {
            "file_path": result.file_path,
            "total_try_blocks": result.total_try_blocks,
            "total_issues": result.total_issues,
            "quality_score": result.quality_score,
            "issue_counts": result.issue_counts,
            "try_blocks": [
                {
                    "start_line": b.start_line,
                    "end_line": b.end_line,
                    "handler_count": b.handler_count,
                    "issues": [
                        {
                            "type": i.issue_type,
                            "line": i.line,
                            "severity": i.severity,
                            "description": i.description,
                            "suggestion": i.suggestion,
                        }
                        for i in b.issues
                    ],
                }
                for b in result.try_blocks
            ],
        }

    def _to_toon(self, result: ExceptionQualityResult) -> str:
        encoder = ToonEncoder()
        data = self._to_json(result)
        return encoder.encode(data)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "text")
        if fmt not in ("text", "json", "toon"):
            raise ValueError(f"Invalid output format: {fmt}")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path is required")
        return True
