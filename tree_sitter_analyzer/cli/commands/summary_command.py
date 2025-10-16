#!/usr/bin/env python3
"""
Summary Command

Handles summary functionality with specified element types.
"""

from typing import TYPE_CHECKING, Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...formatters.language_formatter_factory import create_language_formatter
from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

if TYPE_CHECKING:
    from ...models import AnalysisResult


class SummaryCommand(BaseCommand):
    """Command for summary analysis with specified element types."""

    async def execute_async(self, language: str) -> int:
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1

        self._output_summary_analysis(analysis_result)
        return 0

    def _output_summary_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output summary analysis results."""
        # Check if we have a language-specific formatter
        formatter = create_language_formatter(analysis_result.language)
        if formatter:
            # Use language-specific formatter
            formatted_output = formatter.format_summary(
                self._convert_to_formatter_format(analysis_result)
            )
            print(formatted_output)
            return

        # Fallback to original implementation for unsupported languages
        output_section("Summary Results")

        # Get summary types from args (default: classes,methods)
        summary_types = getattr(self.args, "summary", "classes,methods")
        if summary_types:
            requested_types = [t.strip() for t in summary_types.split(",")]
        else:
            requested_types = ["classes", "methods"]

        # Extract elements by type
        classes = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_CLASS)
        ]
        methods = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_FUNCTION)
        ]
        fields = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_VARIABLE)
        ]
        imports = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_IMPORT)
        ]

        summary_data: dict[str, Any] = {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "summary": {},
        }

        if "classes" in requested_types:
            summary_data["summary"]["classes"] = [
                {"name": getattr(c, "name", "unknown")} for c in classes
            ]

        if "methods" in requested_types:
            summary_data["summary"]["methods"] = [
                {"name": getattr(m, "name", "unknown")} for m in methods
            ]

        if "fields" in requested_types:
            summary_data["summary"]["fields"] = [
                {"name": getattr(f, "name", "unknown")} for f in fields
            ]

        if "imports" in requested_types:
            summary_data["summary"]["imports"] = [
                {"name": getattr(i, "name", "unknown")} for i in imports
            ]

        if self.args.output_format == "json":
            output_json(summary_data)
        else:
            self._output_text_format(summary_data, requested_types)

    def _convert_to_formatter_format(
        self, analysis_result: "AnalysisResult"
    ) -> dict[str, Any]:
        """Convert AnalysisResult to format expected by formatters."""
        from ...constants import get_element_type

        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "line_count": analysis_result.line_count,
            "elements": [
                {
                    "name": getattr(element, "name", str(element)),
                    "type": get_element_type(element),
                    "start_line": getattr(element, "start_line", 0),
                    "end_line": getattr(element, "end_line", 0),
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

    def _output_text_format(self, summary_data: dict, requested_types: list) -> None:
        """Output summary in human-readable text format."""
        output_data(f"File: {summary_data['file_path']}")
        output_data(f"Language: {summary_data['language']}")

        for element_type in requested_types:
            if element_type in summary_data["summary"]:
                elements = summary_data["summary"][element_type]
                type_name_map = {
                    "classes": "Classes",
                    "methods": "Methods",
                    "fields": "Fields",
                    "imports": "Imports",
                }
                type_name = type_name_map.get(element_type, element_type)
                output_data(f"\n{type_name} ({len(elements)} items):")
                for element in elements:
                    output_data(f"  - {element['name']}")
