#!/usr/bin/env python3
"""
Structure Command

Handles structure analysis functionality with appropriate Japanese output.
"""

from typing import TYPE_CHECKING

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...formatters.language_formatter_factory import create_language_formatter
from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

if TYPE_CHECKING:
    from ...models import AnalysisResult


class StructureCommand(BaseCommand):
    """Command for structure analysis with Japanese output."""

    async def execute_async(self, language: str) -> int:
        analysis_result = await self.analyze_file(language)
        if not analysis_result:
            return 1

        self._output_structure_analysis(analysis_result)
        return 0

    def _output_structure_analysis(self, analysis_result: "AnalysisResult") -> None:
        """Output structure analysis results with appropriate header."""
        # Check if we have a language-specific formatter
        formatter = create_language_formatter(analysis_result.language)
        if formatter:
            # Use language-specific formatter
            formatted_output = formatter.format_structure(
                self._convert_to_formatter_format(analysis_result)
            )
            print(formatted_output)
            return

        # Fallback to original implementation for unsupported languages
        output_section("Structure Analysis Results")

        # Convert to legacy structure format expected by tests
        structure_dict = self._convert_to_legacy_format(analysis_result)

        if self.args.output_format == "json":
            output_json(structure_dict)
        else:
            self._output_text_format(structure_dict)

    def _convert_to_formatter_format(self, analysis_result: "AnalysisResult") -> dict:
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

    def _convert_to_legacy_format(self, analysis_result: "AnalysisResult") -> dict:
        """Convert AnalysisResult to legacy structure format expected by tests."""
        import time

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
        packages = [
            e
            for e in analysis_result.elements
            if is_element_of_type(e, ELEMENT_TYPE_PACKAGE)
        ]

        return {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "package": (
                {
                    "name": packages[0].name,
                    "line_range": {
                        "start": packages[0].start_line,
                        "end": packages[0].end_line,
                    },
                }
                if packages
                else None
            ),
            "classes": [{"name": getattr(c, "name", "unknown")} for c in classes],
            "methods": [{"name": getattr(m, "name", "unknown")} for m in methods],
            "fields": [{"name": getattr(f, "name", "unknown")} for f in fields],
            "imports": [
                {
                    "name": getattr(i, "name", "unknown"),
                    "is_static": getattr(i, "is_static", False),
                    "is_wildcard": getattr(i, "is_wildcard", False),
                    "statement": getattr(i, "import_statement", ""),
                    "line_range": {
                        "start": getattr(i, "start_line", 0),
                        "end": getattr(i, "end_line", 0),
                    },
                }
                for i in imports
            ],
            "annotations": [],
            "statistics": {
                "class_count": len(classes),
                "method_count": len(methods),
                "field_count": len(fields),
                "import_count": len(imports),
                "total_lines": analysis_result.line_count,
                "annotation_count": 0,
            },
            "analysis_metadata": {
                "analysis_time": getattr(analysis_result, "analysis_time", 0.0),
                "language": analysis_result.language,
                "file_path": analysis_result.file_path,
                "analyzer_version": "2.0.0",
                "timestamp": time.time(),
            },
        }

    def _output_text_format(self, structure_dict: dict) -> None:
        """Output structure analysis in human-readable text format."""
        output_data(f"File: {structure_dict['file_path']}")
        output_data(f"Language: {structure_dict['language']}")

        if structure_dict["package"]:
            output_data(f"Package: {structure_dict['package']['name']}")

        stats = structure_dict["statistics"]
        output_data("Statistics:")
        output_data(f"  Classes: {stats['class_count']}")
        output_data(f"  Methods: {stats['method_count']}")
        output_data(f"  Fields: {stats['field_count']}")
        output_data(f"  Imports: {stats['import_count']}")
        output_data(f"  Total lines: {stats['total_lines']}")

        if structure_dict["classes"]:
            output_data("Classes:")
            for cls in structure_dict["classes"]:
                output_data(f"  - {cls['name']}")

        if structure_dict["methods"]:
            output_data("Methods:")
            for method in structure_dict["methods"]:
                output_data(f"  - {method['name']}")

        if structure_dict["fields"]:
            output_data("Fields:")
            for field in structure_dict["fields"]:
                output_data(f"  - {field['name']}")
