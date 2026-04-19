"""Mutable Default Arguments Tool — MCP Tool.

Detects Python functions with mutable default arguments, one of the most
common Python bugs. Mutable objects as default values are shared across
all calls, causing unexpected behavior.
"""
from __future__ import annotations

from typing import Any

from ...analysis.mutable_default_args import (
    MutableDefaultArgsAnalyzer,
    MutableDefaultArgsResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MutableDefaultArgsTool(BaseMCPTool):
    """MCP tool for detecting mutable default arguments in Python."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "mutable_default_args",
            "description": (
                "Detect mutable default arguments in Python functions. "
                "\n\n"
                "Finds parameters with mutable default values (list, dict, "
                "set, etc.) that cause shared state across function calls — "
                "one of the most common Python bugs."
                "\n\n"
                "Detects:\n"
                "- List literals: def foo(x=[])\n"
                "- Dict literals: def foo(x={})\n"
                "- Set literals: def foo(x=set())\n"
                "- Comprehensions: def foo(x=[i for i in range(10)])\n"
                "- Variable references: def foo(x=some_mutable)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During Python code review\n"
                "- To catch the #1 Python anti-pattern\n"
                "- Before merging Python code\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For non-Python files\n"
                "- For general code quality (use code_smells)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a Python file to analyze.",
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

        analyzer = MutableDefaultArgsAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: MutableDefaultArgsResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "violation_count": result.violation_count,
            "is_clean": result.is_clean,
            "violations": [
                {
                    "line": v.line_number,
                    "function": v.function_name,
                    "parameter": v.parameter_name,
                    "default_type": v.default_type,
                    "severity": v.severity,
                }
                for v in result.violations
            ],
        }

    def _format_toon(self, result: MutableDefaultArgsResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Mutable Default Arguments Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total functions/classes: {result.total_functions}")
        lines.append(f"Violations: {result.violation_count}")
        lines.append("")

        if result.violations:
            lines.append("Mutable default arguments found:")
            for v in result.violations:
                lines.append(
                    f"  L{v.line_number} [{v.severity.upper()}] "
                    f"{v.function_name}({v.parameter_name}={v.default_type})"
                )
        else:
            lines.append("No mutable default arguments detected.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "violation_count": result.violation_count,
            "is_clean": result.is_clean,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")
        return True
