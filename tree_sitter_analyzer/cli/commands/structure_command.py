#!/usr/bin/env python3
"""
Structure Command

Handles structure analysis functionality with appropriate Japanese output.
"""

from typing import TYPE_CHECKING, Any

from ...constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    is_element_of_type,
)
from ...output_manager import output_data, output_json, output_section
from .base_command import BaseCommand

# TOON formatter for CLI output
try:
    from ...formatters.toon_formatter import ToonFormatter

    _toon_available = True
except ImportError:
    _toon_available = False

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
        if self.args.output_format not in ("json", "toon"):
            output_section("Structure Analysis Results")

        # Convert to legacy structure format expected by tests
        structure_dict = self._convert_to_legacy_format(analysis_result)

        if self.args.output_format == "json":
            output_json(structure_dict)
        elif self.args.output_format == "toon" and _toon_available:
            use_tabs = getattr(self.args, "toon_use_tabs", False)
            formatter = ToonFormatter(use_tabs=use_tabs)
            print(formatter.format(structure_dict))
        else:
            self._output_text_format(structure_dict)

    def _convert_to_legacy_format(self, analysis_result: "AnalysisResult") -> dict:
        """Convert AnalysisResult to legacy structure format expected by tests.

        r37d6 (dogfood): 131 lines → ~20 lines of phase dispatch. Phase
        helpers (``_partition_structure_elements``, ``_legacy_package_block``,
        ``_legacy_statistics_block``, ``_attach_structure_envelope``) own
        the per-section work. Output dict keys + tuple shapes are preserved.
        """
        classes, methods, fields, imports, packages = (
            self._partition_structure_elements(analysis_result)
        )
        legacy_dict: dict[str, Any] = {
            "file_path": analysis_result.file_path,
            "language": analysis_result.language,
            "package": self._legacy_package_block(packages),
            "classes": [
                {
                    "name": getattr(c, "name", "unknown"),
                    "visibility": getattr(c, "visibility", ""),
                    "line_range": (
                        getattr(c, "start_line", 0),
                        getattr(c, "end_line", 0),
                    ),
                }
                for c in classes
            ],
            "methods": [
                {
                    "name": getattr(m, "name", "unknown"),
                    "visibility": getattr(m, "visibility", ""),
                    "line_range": (
                        getattr(m, "start_line", 0),
                        getattr(m, "end_line", 0),
                    ),
                }
                for m in methods
            ],
            "fields": [
                {
                    "name": getattr(f, "name", "unknown"),
                    "type": getattr(f, "type_annotation", ""),
                    "line_range": (
                        getattr(f, "start_line", 0),
                        getattr(f, "end_line", 0),
                    ),
                }
                for f in fields
            ],
            "imports": [
                {
                    "name": getattr(i, "name", "unknown"),
                    "is_static": getattr(i, "is_static", False),
                    "is_wildcard": getattr(i, "is_wildcard", False),
                    "statement": getattr(i, "import_statement", ""),
                    "line_range": (
                        getattr(i, "start_line", 0),
                        getattr(i, "end_line", 0),
                    ),
                }
                for i in imports
            ],
            "annotations": [],
            "statistics": self._legacy_statistics_block(
                analysis_result, classes, methods, fields, imports
            ),
            "analysis_metadata": self._legacy_metadata_block(analysis_result),
        }
        self._attach_structure_envelope(
            legacy_dict,
            analysis_result,
            classes=classes,
            methods=methods,
            fields=fields,
            imports=imports,
        )
        return legacy_dict

    @staticmethod
    def _partition_structure_elements(
        analysis_result: "AnalysisResult",
    ) -> tuple[list[Any], list[Any], list[Any], list[Any], list[Any]]:
        """Bucket elements into (classes, methods, fields, imports, packages)."""
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
        return classes, methods, fields, imports, packages

    @staticmethod
    def _legacy_package_block(packages: list[Any]) -> dict[str, Any] | None:
        """Return the package dict (name + line_range tuple) or ``None``."""
        if not packages:
            return None
        return {
            "name": packages[0].name,
            "line_range": (
                packages[0].start_line,
                packages[0].end_line,
            ),
        }

    @staticmethod
    def _legacy_statistics_block(
        analysis_result: "AnalysisResult",
        classes: list[Any],
        methods: list[Any],
        fields: list[Any],
        imports: list[Any],
    ) -> dict[str, Any]:
        """Return the legacy ``statistics`` dict."""
        return {
            "class_count": len(classes),
            "method_count": len(methods),
            "field_count": len(fields),
            "import_count": len(imports),
            "total_lines": analysis_result.line_count,
            "annotation_count": 0,
        }

    @staticmethod
    def _legacy_metadata_block(
        analysis_result: "AnalysisResult",
    ) -> dict[str, Any]:
        """Return the legacy ``analysis_metadata`` dict (incl. timestamp)."""
        import time

        return {
            "analysis_time": getattr(analysis_result, "analysis_time", 0.0),
            "language": analysis_result.language,
            "file_path": analysis_result.file_path,
            "analyzer_version": "2.0.0",
            "timestamp": time.time(),
        }

    @staticmethod
    def _attach_structure_envelope(
        legacy_dict: dict[str, Any],
        analysis_result: "AnalysisResult",
        *,
        classes: list[Any],
        methods: list[Any],
        fields: list[Any],
        imports: list[Any],
    ) -> None:
        """Attach the r37aa canonical envelope (success / summary_line /
        verdict / agent_summary). Third CLI surface (after ``--advanced``
        r37y and ``--summary`` r37z) that was emitting ``=None`` for the
        envelope fields — agents reading the response shape couldn't tell
        the call succeeded vs. silently failed.
        """
        summary_line = (
            f"{analysis_result.file_path} ({analysis_result.language}) structure: "
            f"classes={len(classes)} methods={len(methods)} "
            f"fields={len(fields)} imports={len(imports)} "
            f"lines={analysis_result.line_count}"
        )
        legacy_dict["success"] = True
        legacy_dict["summary_line"] = summary_line
        legacy_dict["verdict"] = "INFO"
        legacy_dict["agent_summary"] = {
            "summary_line": summary_line,
            "next_step": (
                "Use --table for a Markdown breakdown, or extract_code_section "
                "(MCP) to read specific elements by line range."
            ),
            "verdict": "INFO",
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
