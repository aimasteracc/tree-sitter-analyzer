#!/usr/bin/env python3
"""
Documentation Coverage Tool — MCP Tool

Analyzes documentation coverage across codebases to help developers
ensure code documentation completeness.

Supports: Python (docstrings), JavaScript/TypeScript (JSDoc), Java (JavaDoc), Go (doc comments)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.doc_coverage import (
    DocCoverageAnalyzer,
    DocCoverageResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DocCoverageTool(BaseMCPTool):
    """
    MCP tool for analyzing documentation coverage.

    Detects undocumented functions, classes, and methods across
    Python, JavaScript/TypeScript, Java, and Go codebases.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "doc_coverage",
            "description": (
                "Analyze documentation coverage across your codebase. "
                "\n\n"
                "Supported Languages:\n"
                "- Python: docstrings for functions, classes, methods\n"
                "- JavaScript/TypeScript: JSDoc comments\n"
                "- Java: JavaDoc comments\n"
                "- Go: doc comments\n"
                "\n"
                "WHEN TO USE:\n"
                "- Before code review to check documentation completeness\n"
                "- During onboarding to identify poorly documented code\n"
                "- As part of CI/CD quality gates\n"
                "- To track documentation coverage over time\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For code quality scoring (use health_score)\n"
                "- For detecting code smells (use code_smell_detector)"
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
                    "element_types": {
                        "type": "string",
                        "description": (
                            "Comma-separated element types to check: "
                            "function, class, method, interface, type, module. "
                            "Default: all types."
                        ),
                    },
                    "min_coverage": {
                        "type": "number",
                        "description": (
                            "Minimum acceptable coverage percentage (0-100). "
                            "Elements below this will be highlighted. Default: 0."
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
        project_root = arguments.get(
            "project_root", self.project_root or ""
        )
        element_types_str = arguments.get("element_types", "")
        min_coverage = arguments.get("min_coverage", 0.0)
        output_format = arguments.get("format", "toon")

        if not file_path and not project_root:
            return {
                "error": "Either file_path or project_root must be provided",
                "format": output_format,
            }

        element_types: set[str] | None = None
        if element_types_str:
            element_types = {t.strip() for t in element_types_str.split(",")}

        analyzer = DocCoverageAnalyzer()

        if file_path:
            result = analyzer.analyze_file(file_path)
        else:
            result = analyzer.analyze_directory(project_root)

        if element_types:
            filtered = tuple(
                e for e in result.elements if e.element_type in element_types
            )
            total = len(filtered)
            documented = sum(1 for e in filtered if e.has_doc)
            pct = (documented / total * 100.0) if total > 0 else 100.0
            result = DocCoverageResult(
                elements=filtered,
                total_elements=total,
                documented_count=documented,
                coverage_percent=round(pct, 2),
            )

        if output_format == "json":
            return self._format_json(result, min_coverage)
        return self._format_toon(result, min_coverage)

    def _format_json(
        self,
        result: DocCoverageResult,
        min_coverage: float,
    ) -> dict[str, Any]:
        missing = result.get_missing_docs()
        return {
            "total_elements": result.total_elements,
            "documented_count": result.documented_count,
            "coverage_percent": result.coverage_percent,
            "meets_threshold": result.coverage_percent >= min_coverage,
            "missing_docs": [
                {
                    "name": e.name,
                    "type": e.element_type,
                    "file": e.file_path,
                    "line": e.line_number,
                }
                for e in missing
            ],
            "elements": [
                {
                    "name": e.name,
                    "type": e.element_type,
                    "file": e.file_path,
                    "line": e.line_number,
                    "has_doc": e.has_doc,
                }
                for e in result.elements
            ],
        }

    def _format_toon(
        self,
        result: DocCoverageResult,
        min_coverage: float,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Documentation Coverage Analysis")
        lines.append(f"Total elements: {result.total_elements}")
        lines.append(f"Documented: {result.documented_count}")
        lines.append(f"Coverage: {result.coverage_percent:.1f}%")

        if min_coverage > 0:
            status = "PASS" if result.coverage_percent >= min_coverage else "FAIL"
            lines.append(f"Threshold ({min_coverage:.0f}%): {status}")

        lines.append("")

        missing = result.get_missing_docs()
        if missing:
            lines.append("Undocumented Elements:")
            for e in missing:
                lines.append(
                    f"  [{e.element_type}] {e.name} "
                    f"({Path(e.file_path).name}:{e.line_number})"
                )
        else:
            lines.append("All elements are documented.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_elements": result.total_elements,
            "documented_count": result.documented_count,
            "coverage_percent": result.coverage_percent,
            "meets_threshold": result.coverage_percent >= min_coverage,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", "")
        if not file_path and not project_root:
            raise ValueError("Either file_path or project_root must be provided")

        return True
