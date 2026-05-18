#!/usr/bin/env python3
"""
Markdown Formatter

Provides specialized formatting for Markdown files, focusing on document structure
rather than programming constructs like classes and methods.
"""

from typing import Any

from ._markdown_formatter_helpers import (
    build_advanced_result,
    build_structure_result,
    build_summary_result,
    calculate_document_complexity,
    collect_images,
    compute_robust_counts_from_file,
    format_advanced_text,
    format_compact_output,
    format_csv_output,
    format_json_output,
)
from .base_formatter import BaseFormatter
from .markdown_full_formatter import format_full


class MarkdownFormatter(BaseFormatter):
    """Formatter specialized for Markdown documents"""

    def __init__(self) -> None:
        self.language = "markdown"

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary for Markdown files"""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])
        result = build_summary_result(
            file_path,
            elements,
            self._collect_images(elements),
            self._compute_robust_counts_from_file(file_path),
        )
        return self._format_json_output("Summary Results", result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis for Markdown files"""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])
        result = build_structure_result(
            analysis_result,
            self._collect_images(elements),
            self._compute_robust_counts_from_file(file_path),
        )
        return self._format_json_output("Structure Analysis Results", result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis for Markdown files"""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])
        advanced_data = build_advanced_result(
            analysis_result,
            self._collect_images(elements),
            self._compute_robust_counts_from_file(file_path),
        )

        if output_format == "text":
            return self._format_advanced_text(advanced_data)
        return self._format_json_output("Advanced Analysis Results", advanced_data)

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "full"
    ) -> str:
        """Format AnalysisResult directly for Markdown files"""
        data = self._convert_analysis_result_to_format(analysis_result)
        return self.format_table(data, table_type)

    def _convert_analysis_result_to_format(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        """Convert AnalysisResult to format expected by format_table"""
        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "elements": [
                {
                    "name": getattr(element, "name", ""),
                    "type": getattr(element, "type", ""),
                    "text": getattr(element, "text", ""),
                    "level": getattr(element, "level", 1),
                    "url": getattr(element, "url", ""),
                    "alt": getattr(element, "alt", ""),
                    "language": getattr(element, "language", ""),
                    "line_count": getattr(element, "line_count", 0),
                    "list_type": getattr(element, "list_type", ""),
                    "item_count": getattr(element, "item_count", 0),
                    "column_count": getattr(element, "column_count", 0),
                    "row_count": getattr(element, "row_count", 0),
                    "line_range": {
                        "start": getattr(element, "start_line", 0),
                        "end": getattr(element, "end_line", 0),
                    },
                }
                for element in analysis_result.elements
            ],
            "analysis_metadata": {
                "analysis_time": getattr(analysis_result, "analysis_time", 0.0),
                "language": analysis_result.language,
                "file_path": analysis_result.file_path,
                "analyzer_version": "2.0.0",
            },
        }

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for Markdown files"""
        if table_type == "compact":
            return self._format_compact(analysis_result)
        if table_type == "csv":
            return self._format_csv(analysis_result)
        return self._format_full(analysis_result)

    def _format_full(self, analysis_result: dict[str, Any]) -> str:
        """Format full table output for Markdown files"""
        return format_full(analysis_result, self._collect_images)

    def _collect_images(self, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Collect images including reference definitions that point to images."""
        return collect_images(elements)

    def _format_advanced_text(self, data: dict[str, Any]) -> str:
        """Format advanced analysis in text format"""
        return format_advanced_text(data)

    def _calculate_document_complexity(
        self,
        headers: list[dict],
        links: list[dict],
        code_blocks: list[dict],
        tables: list[dict],
    ) -> str:
        """Calculate document complexity based on structure and content"""
        return calculate_document_complexity(headers, links, code_blocks, tables)

    def _format_json_output(self, title: str, data: dict[str, Any]) -> str:
        """Format JSON output with title"""
        return format_json_output(title, data)

    def _compute_robust_counts_from_file(self, file_path: str) -> dict[str, int]:
        """Compute robust counts for links and images directly from file content."""
        return compute_robust_counts_from_file(file_path)

    def _format_compact(self, analysis_result: dict[str, Any]) -> str:
        """Format compact table output for Markdown files"""
        return format_compact_output(
            analysis_result, self._collect_images(analysis_result.get("elements", []))
        )

    def _format_csv(self, analysis_result: dict[str, Any]) -> str:
        """Format CSV output for Markdown files"""
        return format_csv_output(analysis_result)
