"""i18n String Detector Tool — MCP Tool.

Detects user-visible strings in code that need internationalization.
Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.i18n_strings import (
    VIS_LIKELY,
    VIS_USER,
    I18nFileResult,
    I18nStringDetector,
    I18nSummary,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class I18nStringsTool(BaseMCPTool):
    """MCP tool for detecting strings needing internationalization."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "i18n_strings",
            "description": (
                "Detect user-visible strings that need internationalization. "
                "\n\n"
                "Finds hardcoded text in output functions (print, raise, "
                "console.log, alert, System.out, fmt.Print, etc.) and "
                "classifies them by visibility level."
                "\n\n"
                "Visibility Levels:\n"
                "- user_visible: Clear user-facing text (sentences, error messages)\n"
                "- likely_visible: Possibly user-facing (multi-word, mixed case)\n"
                "- internal: Technical strings (URLs, paths, identifiers, numbers)\n"
                "\n"
                "Supported Languages:\n"
                "- Python: print, raise, logging.error/warning/info, sys.stderr\n"
                "- JavaScript/TypeScript: console.log/warn/error, alert, throw new Error\n"
                "- Java: System.out.println, Logger.severe/warning/info, throw new Exception\n"
                "- Go: fmt.Print/Printf, log.Printf, errors.New, fmt.Errorf\n"
                "\n"
                "WHEN TO USE:\n"
                "- Before localization to find all translatable strings\n"
                "- During code review to flag hardcoded user-facing text\n"
                "- To audit i18n readiness of a codebase\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For hardcoded value detection (use magic_values)\n"
                "- For comment quality (use comment_quality)\n"
                "- For dead code detection (use dead_code)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file."
                        ),
                    },
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory for multi-file scan. "
                            "Ignored if file_path is provided."
                        ),
                    },
                    "min_length": {
                        "type": "integer",
                        "description": (
                            "Minimum string length to consider. Default: 2."
                        ),
                        "default": 2,
                    },
                    "visibility": {
                        "type": "string",
                        "description": (
                            "Filter by visibility: user_visible, likely_visible, "
                            "or all. Default: all."
                        ),
                        "enum": ["user_visible", "likely_visible", "all"],
                        "default": "all",
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
        project_root = arguments.get("project_root", "")
        min_length = arguments.get("min_length", 2)
        visibility = arguments.get("visibility", "all")
        output_format = arguments.get("format", "toon")

        vis_filter: set[str] | None = None
        if visibility == "user_visible":
            vis_filter = {VIS_USER}
        elif visibility == "likely_visible":
            vis_filter = {VIS_LIKELY, VIS_USER}

        detector = I18nStringDetector()

        if file_path:
            result = detector.analyze_file(
                file_path,
                min_length=min_length,
                visibility_filter=vis_filter,
            )
            if output_format == "json":
                return self._format_file_json(result)
            return self._format_file_toon(result)

        root = project_root or self.project_root
        if root:
            summary = detector.analyze_directory(
                root,
                min_length=min_length,
                visibility_filter=vis_filter,
            )
            if output_format == "json":
                return self._format_summary_json(summary)
            return self._format_summary_toon(summary)

        return {
            "error": "file_path or project_root must be provided",
            "format": output_format,
        }

    def _format_file_json(self, result: I18nFileResult) -> dict[str, Any]:
        return result.to_dict()

    def _format_file_toon(self, result: I18nFileResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("i18n String Detection")
        lines.append(f"File: {result.file_path}")
        lines.append(
            f"Strings: {len(result.strings)} "
            f"(user: {result.user_visible_count}, "
            f"likely: {result.likely_visible_count}, "
            f"internal: {result.internal_count})"
        )
        lines.append("")

        user_strings = [s for s in result.strings if s.visibility == VIS_USER]
        likely_strings = [s for s in result.strings if s.visibility == VIS_LIKELY]

        if user_strings:
            lines.append("User-visible strings:")
            for s in user_strings:
                lines.append(f"  L{s.line}: {s.function_name}() -> \"{s.text}\"")

        if likely_strings:
            lines.append("Likely visible strings:")
            for s in likely_strings:
                lines.append(f"  L{s.line}: {s.function_name}() -> \"{s.text}\"")

        if not user_strings and not likely_strings:
            lines.append("No user-visible strings found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_strings": len(result.strings),
            "user_visible_count": result.user_visible_count,
        }

    def _format_summary_json(
        self,
        summary: I18nSummary,
    ) -> dict[str, Any]:
        return summary.to_dict()

    def _format_summary_toon(
        self,
        summary: I18nSummary,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("i18n String Detection - Project Summary")
        lines.append(f"Files analyzed: {summary.total_files}")
        lines.append(f"Total strings: {summary.total_strings}")
        lines.append(
            f"User-visible: {summary.user_visible_count} | "
            f"Likely: {summary.likely_visible_count} | "
            f"Internal: {summary.internal_count}"
        )
        lines.append("")

        for fr in summary.file_results:
            user_count = fr.user_visible_count
            if user_count > 0:
                lines.append(f"  {fr.file_path}: {user_count} user-visible")
                for s in fr.strings:
                    if s.visibility == VIS_USER:
                        lines.append(f"    L{s.line}: \"{s.text}\"")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_files": summary.total_files,
            "total_strings": summary.total_strings,
            "user_visible_count": summary.user_visible_count,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        vis = arguments.get("visibility", "all")
        if vis not in ("user_visible", "likely_visible", "all"):
            raise ValueError("visibility must be 'user_visible', 'likely_visible', or 'all'")

        return True
