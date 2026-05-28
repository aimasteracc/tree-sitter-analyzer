#!/usr/bin/env python3
"""
C/C++ specific table formatter.
Supports files with mixed classes/structs and global functions.
"""

from typing import Any

from ._cpp_formatter_convert_mixin import CppTableFormatterConvertMixin
from ._cpp_formatter_helpers import (
    create_cpp_compact_signature,
    format_cpp_class_details,
    format_cpp_compact_table,
    format_cpp_full_table,
    shorten_cpp_type,
)
from .base_formatter import BaseTableFormatter


class CppTableFormatter(CppTableFormatterConvertMixin, BaseTableFormatter):
    """Table formatter specialized for C and C++"""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for C/C++"""
        return format_cpp_full_table(self, data)

    def _format_class_details(
        self, class_info: dict[str, Any], data: dict[str, Any]
    ) -> list[str]:
        """Format details for a single class"""
        return format_cpp_class_details(self, class_info, data)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for C/C++"""
        return format_cpp_compact_table(self, data)

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row"""
        name = str(method.get("name", ""))
        signature = self._create_full_signature(method)
        visibility = self._convert_visibility(str(method.get("visibility", "")))
        line_range = method.get("line_range", {})
        lines_str = f"{line_range.get('start', 0)}-{line_range.get('end', 0)}"
        cols_str = "5-6"  # default placeholder
        complexity = method.get("complexity_score", 0)
        doc = self._clean_csv_text(
            self._extract_doc_summary(str(method.get("javadoc", "")))
        )

        return f"| {name} | {signature} | {visibility} | {lines_str} | {cols_str} | {complexity} | {doc} |"

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature"""
        return create_cpp_compact_signature(self._shorten_type, method)

    def _shorten_type(self, type_name: Any) -> str:
        """Shorten type name for C/C++ compact display"""
        return shorten_cpp_type(type_name)

    # Public aliases for companion module _cpp_formatter_helpers.py
    format_class_details = _format_class_details
    format_method_row = _format_method_row
    create_compact_signature = _create_compact_signature
    shorten_type = _shorten_type

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output"""
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            if table_type == "json":
                return self._format_json(analysis_result)
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output"""
        return self._format_compact_table(analysis_result)

    def format_analysis_result(self, analysis_result: Any, table_type: str) -> str:
        """
        Format analysis result directly (C++ specific).
        Converts AnalysisResult to structure format with all namespaces extracted.
        """
        # Convert analysis result to structure format (with namespace extraction)
        formatted_data = self._convert_analysis_result_to_format(analysis_result)

        # Format based on table type
        if table_type == "full":
            return self._format_full_table(formatted_data)
        elif table_type == "compact":
            return self._format_compact_table(formatted_data)
        elif table_type == "csv":
            return self._format_csv(formatted_data)
        else:
            return self._format_full_table(formatted_data)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output"""
        if output_format == "json":
            return self._format_json(analysis_result)
        elif output_format == "csv":
            return self._format_csv(analysis_result)
        else:
            return self._format_full_table(analysis_result)

    def _format_json(self, data: dict[str, Any]) -> str:
        import json

        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return f"# JSON serialization error: {e}\\n"
