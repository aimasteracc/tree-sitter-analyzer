#!/usr/bin/env python3
"""
Unreachable Code MCP Tool — Statement-level dead code detection.

Detects code within live functions that can never execute:
- Statements after return/raise/break/continue
- if-False branches (always-skipped code)
- else branches of if-True (always-skipped code)
- Code after terminal calls (sys.exit, os._exit, etc.)

Unlike codegraph_dead_code (function-level reachability), this detects
**intra-function** unreachable statements via AST-level control flow.

Modes:
  - file: Analyze a single file for unreachable code paths
  - project: Scan entire project for unreachable code paths
"""

from __future__ import annotations

from typing import Any

from ...unreachable_code import (
    UnreachableCodeResult,
    analyze_file_unreachable,
    analyze_project_unreachable,
)
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class UnreachableCodeTool(BaseMCPTool):
    """MCP Tool for statement-level unreachable code detection."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "unreachable_code",
            "description": (
                "Unreachable code detection: finds statements inside live functions "
                "that can never execute. Detects code after return/raise/break/continue, "
                "if-False branches, else of if-True, and code after terminal calls "
                "(sys.exit, os._exit). Statement-level analysis, not function-level "
                "dead code (use codegraph_dead_code for that). "
                "Modes: file (single file), project (entire project scan)."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["file", "project"],
                    "default": "file",
                    "description": (
                        "Analysis mode: 'file' for single file analysis, "
                        "'project' for full project scan"
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": ("File path to analyze (required for 'file' mode)"),
                },
                "include_test_files": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include test files in project scan",
                },
                "max_files": {
                    "type": "integer",
                    "default": 500,
                    "description": "Max files to scan in project mode",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def get_tool_name(self) -> str:
        return "unreachable_code"

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        mode = arguments.get("mode", "file")
        if mode not in ("file", "project"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'file' or 'project'.")
        if mode == "file" and not arguments.get("file_path"):
            raise ValueError("file_path is required for 'file' mode.")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        mode = arguments.get("mode", "file")
        output_format = arguments.get("output_format", "toon")

        if mode == "file":
            return self._execute_file_mode(arguments, output_format)
        else:
            return self._execute_project_mode(arguments, output_format)

    def _execute_file_mode(
        self, arguments: dict[str, Any], output_format: str
    ) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        if not file_path:
            return {"error": "file_path is required for file mode"}

        resolved = self._resolve_path(file_path)
        if resolved is None:
            return {"error": f"File not found: {file_path}"}

        try:
            result = analyze_file_unreachable(resolved)
        except Exception as exc:
            logger.error("unreachable_code file analysis failed: %s", exc)
            return {"error": str(exc)}

        response = self._build_file_response(result, output_format)
        return response

    def _execute_project_mode(
        self, arguments: dict[str, Any], output_format: str
    ) -> dict[str, Any]:
        if not self.project_root:
            return {"error": "Project root not set for project mode."}

        include_tests = arguments.get("include_test_files", False)
        max_files = arguments.get("max_files", 500)

        try:
            results = analyze_project_unreachable(
                self.project_root,
                include_test_files=include_tests,
                max_files=max_files,
            )
        except Exception as exc:
            logger.error("unreachable_code project analysis failed: %s", exc)
            return {"error": str(exc)}

        response = self._build_project_response(results, output_format)
        return response

    @staticmethod
    def _format_block_line(block: Any) -> str:
        """Format a single unreachable block as a TOON line."""
        return (
            f"- L{block.start_line}-{block.end_line} in "
            f"`{block.function_name}`: {block.reason} "
            f"[{block.severity}]"
        )

    def _build_file_response(
        self, result: UnreachableCodeResult, output_format: str
    ) -> dict[str, Any]:
        if output_format == "toon":
            lines = []
            lines.append(f"## Unreachable Code: {result.file_path}")
            lines.append(f"Language: {result.language}")
            lines.append(f"Functions analyzed: {result.functions_analyzed}")
            lines.append(f"Unreachable blocks: {len(result.unreachable_blocks)}")

            if result.unreachable_blocks:
                lines.append("")
                lines.extend(
                    self._format_block_line(b) for b in result.unreachable_blocks
                )
            else:
                lines.append("")
                lines.append("No unreachable code detected.")

            if result.errors:
                lines.append(f"\nParse errors: {result.errors}")

            return apply_toon_format_to_response(
                {"content": "\n".join(lines)},
                output_format="toon",
            )

        return result.to_dict()

    def _format_file_blocks_toon(self, r: UnreachableCodeResult) -> list[str]:
        """Format a single file's unreachable blocks as TOON lines."""
        if not r.unreachable_blocks:
            return []
        lines = [f"### {r.file_path} ({r.language})"]
        for block in r.unreachable_blocks:
            lines.append(
                f"- L{block.start_line}-{block.end_line} in "
                f"`{block.function_name}`: {block.reason}"
            )
        return lines

    def _build_project_response(
        self, results: list[UnreachableCodeResult], output_format: str
    ) -> dict[str, Any]:
        total_blocks = sum(len(r.unreachable_blocks) for r in results)
        total_functions = sum(r.functions_analyzed for r in results)
        files_with_issues = sum(1 for r in results if r.unreachable_blocks)

        if output_format == "toon":
            lines: list[str] = []
            lines.append("## Unreachable Code: Project Scan")
            lines.append(f"Files with issues: {files_with_issues}")
            lines.append(f"Functions analyzed: {total_functions}")
            lines.append(f"Total unreachable blocks: {total_blocks}")

            if results:
                lines.append("")
                for r in results:
                    lines.extend(self._format_file_blocks_toon(r))

            return apply_toon_format_to_response(
                {"content": "\n".join(lines)},
                output_format="toon",
            )

        return {
            "files_with_issues": files_with_issues,
            "total_functions_analyzed": total_functions,
            "total_unreachable_blocks": total_blocks,
            "results": [r.to_dict() for r in results],
        }

    def _resolve_path(self, file_path: str) -> str | None:
        import os

        if os.path.isfile(file_path):
            return file_path
        if self.project_root:
            full = os.path.join(self.project_root, file_path)
            if os.path.isfile(full):
                return full
        return None
