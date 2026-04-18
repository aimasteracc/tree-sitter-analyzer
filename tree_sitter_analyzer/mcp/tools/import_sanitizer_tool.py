"""
Import Sanitizer Tool — MCP Tool

Detects unused imports, circular import dependencies, and import sort
order violations across Python, JavaScript/TypeScript, Java, and Go.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.import_sanitizer import (
    ImportAnalysisResult,
    ImportSanitizer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ImportSanitizerTool(BaseMCPTool):
    """
    MCP tool for analyzing import quality.

    Detects unused imports, circular dependencies, and sort order violations.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", "")
        return bool(file_path or project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "import_sanitizer",
            "description": (
                "Analyze import quality: detect unused imports, circular "
                "dependencies, and sort order violations. "
                "\n\n"
                "Supported Languages:\n"
                "- Python: import, from...import, star imports\n"
                "- JavaScript/TypeScript: import { }, import x, import * as\n"
                "- Java: import, static imports\n"
                "- Go: import, aliased imports\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to find unused imports\n"
                "- To detect circular import dependencies\n"
                "- To enforce import ordering conventions\n"
                "- Before merging to clean up import hygiene\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For dependency graph visualization (use dependency_query)\n"
                "- For security scanning (use security_scan)"
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
                            "Project root directory. "
                            "If provided without file_path, scans entire project."
                        ),
                    },
                    "check_unused": {
                        "type": "boolean",
                        "description": "Check for unused imports. Default: true.",
                    },
                    "check_circular": {
                        "type": "boolean",
                        "description": (
                            "Check for circular dependencies "
                            "(project-level only). Default: true."
                        ),
                    },
                    "check_sort": {
                        "type": "boolean",
                        "description": "Check import sort order. Default: true.",
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
        project_root = arguments.get(
            "project_root", self.project_root or ""
        )
        check_unused = arguments.get("check_unused", True)
        check_circular = arguments.get("check_circular", True)
        check_sort = arguments.get("check_sort", True)
        output_format = arguments.get("format", "toon")

        if not file_path and not project_root:
            return {
                "error": "Either file_path or project_root must be provided",
                "format": output_format,
            }

        root = project_root or str(Path(file_path).parent)
        sanitizer = ImportSanitizer(root)

        if file_path:
            result = ImportAnalysisResult()
            analysis = sanitizer.analyze_file(file_path)
            result.files.append(analysis)
            result.total_imports = len(analysis.imports)
            result.total_unused = len(analysis.unused_imports)
            result.total_sort_violations = len(analysis.sort_violations)
        else:
            result = sanitizer.analyze_directory(project_root)

        if output_format == "json":
            return self._format_json(result, check_unused, check_circular, check_sort)
        return self._format_toon(result, check_unused, check_circular, check_sort)

    def _format_json(
        self,
        result: ImportAnalysisResult,
        check_unused: bool,
        check_circular: bool,
        check_sort: bool,
    ) -> dict[str, Any]:
        output: dict[str, Any] = {
            "total_imports": result.total_imports,
            "files_analyzed": len(result.files),
        }
        if check_unused:
            output["total_unused"] = result.total_unused
        if check_circular:
            output["circular_imports"] = [c.display for c in result.circular_imports]
        if check_sort:
            output["total_sort_violations"] = result.total_sort_violations

        file_results: list[dict[str, Any]] = []
        for f in result.files:
            entry: dict[str, Any] = {"path": f.file_path}
            if check_unused:
                entry["unused"] = [i.display_name for i in f.unused_imports]
            if check_sort:
                entry["sort_violations"] = [v.message for v in f.sort_violations]
            file_results.append(entry)
        output["files"] = file_results
        return output

    def _format_toon(
        self,
        result: ImportAnalysisResult,
        check_unused: bool,
        check_circular: bool,
        check_sort: bool,
    ) -> dict[str, Any]:
        encoder = ToonEncoder()
        sections: list[str] = []

        sections.append(
            f"Import Analysis: {result.total_imports} imports "
            f"across {len(result.files)} files"
        )

        if check_unused and result.total_unused > 0:
            sections.append(f"\nUnused Imports ({result.total_unused}):")
            for f in result.files:
                for imp in f.unused_imports:
                    sections.append(
                        f"  {f.file_path}:{imp.line} — {imp.display_name}"
                    )

        if check_circular and result.circular_imports:
            sections.append(f"\nCircular Dependencies ({len(result.circular_imports)}):")
            for c in result.circular_imports:
                sections.append(f"  {c.display}")

        if check_sort and result.total_sort_violations > 0:
            sections.append(f"\nSort Violations ({result.total_sort_violations}):")
            for f in result.files:
                for v in f.sort_violations:
                    sections.append(f"  {f.file_path}:{v.import_info.line} — {v.message}")

        if (
            (not check_unused or result.total_unused == 0)
            and (not check_circular or not result.circular_imports)
            and (not check_sort or result.total_sort_violations == 0)
        ):
            sections.append("\nAll imports are clean.")

        toon_text = encoder.encode("\n".join(sections))
        return {"format": "toon", "content": toon_text}
