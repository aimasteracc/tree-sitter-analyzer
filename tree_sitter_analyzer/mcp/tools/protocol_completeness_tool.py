"""Protocol Completeness Tool — MCP Tool.

Detects classes that partially implement a known protocol,
missing required counterpart methods (__eq__ without __hash__, etc.).
"""
from __future__ import annotations

from typing import Any

from ...analysis.protocol_completeness import (
    ProtocolCompletenessAnalyzer,
    ProtocolCompletenessResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ProtocolCompletenessTool(BaseMCPTool):
    """MCP tool for detecting incomplete protocol implementations."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "protocol_completeness",
            "description": (
                "Detect incomplete protocol implementations: classes that "
                "define one method of a protocol pair but miss the other."
                "\n\n"
                "Examples: __eq__ without __hash__, equals() without "
                "hashCode(), __enter__ without __exit__."
                "\n\n"
                "Supported Languages:\n"
                "- Python (dunder protocols), Java (Object methods)\n"
                "\n"
                "Issue Types:\n"
                "- missing_hash: __eq__ defined, __hash__ missing\n"
                "- missing_exit: __enter__ defined, __exit__ missing\n"
                "- missing_next: __iter__ defined, __next__ missing\n"
                "- missing_set_or_delete: __get__ defined, __set__/__delete__ missing\n"
                "- missing_hashcode: equals() defined, hashCode() missing\n"
                "- missing_equals_for_compareto: compareTo() defined, equals() missing\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find silent runtime bugs from incomplete protocols\n"
                "- To ensure class implementations are consistent\n"
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

        analyzer = ProtocolCompletenessAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: ProtocolCompletenessResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "classes_checked": result.classes_checked,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: ProtocolCompletenessResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Protocol Completeness Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Classes checked: {result.classes_checked}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} incomplete protocol(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.class_name}: {issue.description}"
                )
        else:
            lines.append("All protocols are complete.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
