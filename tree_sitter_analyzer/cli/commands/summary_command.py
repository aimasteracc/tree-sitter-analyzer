#!/usr/bin/env python3
"""
Summary Command

Handles summary functionality with specified element types.
"""

from typing import TYPE_CHECKING, Any

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
        output_section("Summary Results")

        # Get summary types from args (default: classes,methods)
        summary_types = getattr(self.args, "summary", "classes,methods")
        if summary_types:
            requested_types = [t.strip() for t in summary_types.split(",")]
        else:
            requested_types = ["classes", "methods"]

        # Extract elements by type
        classes = [
            e for e in analysis_result.elements if e.__class__.__name__ == "Class"
        ]
        methods = [
            e for e in analysis_result.elements if e.__class__.__name__ == "Function"
        ]
        fields = [
            e for e in analysis_result.elements if e.__class__.__name__ == "Variable"
        ]
        imports = [
            e for e in analysis_result.elements if e.__class__.__name__ == "Import"
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
