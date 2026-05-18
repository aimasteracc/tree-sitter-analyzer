#!/usr/bin/env python3
"""
TypeScript-specific table formatter.

Provides specialized formatting for TypeScript code analysis results,
handling TypeScript-specific features like interfaces, type aliases, enums,
generics, decorators, and modern JavaScript features with type annotations.
"""

from typing import Any

from ._typescript_formatter_compact import format_typescript_compact_table
from ._typescript_formatter_csv import format_typescript_csv
from ._typescript_formatter_full import format_typescript_full_table
from ._typescript_formatter_helpers import (
    create_compact_signature,
    create_csv_signature,
    create_full_signature,
    format_method_row,
    format_typescript_modifiers,
    get_class_fields,
    get_class_methods,
)
from .base_formatter import BaseTableFormatter


class TypeScriptTableFormatter(BaseTableFormatter):
    """Table formatter specialized for TypeScript"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data using the configured format type"""
        return self.format_structure(data)

    # Format data for output: _format_full_table
    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for TypeScript - matches golden master format"""
        return format_typescript_full_table(self, data)

    # Format data for output: _format_compact_table
    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for TypeScript - matches golden master format"""
        return format_typescript_compact_table(self, data)

    # Format data for output: _format_csv
    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for TypeScript - matches golden master format"""
        return format_typescript_csv(self, data)

    def _get_class_methods(
        self, methods: list[dict[str, Any]], line_range: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get methods within a class range"""
        return get_class_methods(methods, line_range)

    def _get_class_fields(
        self, fields: list[dict[str, Any]], line_range: dict[str, int]
    ) -> list[dict[str, Any]]:
        """Get fields within a class range"""
        return get_class_fields(fields, line_range)

    # Format data for output: _format_method_row
    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row"""
        return format_method_row(self, method)

    def _create_full_signature(self, method: dict[str, Any]) -> str:
        """Create full method signature"""
        return create_full_signature(method)

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature"""
        return create_compact_signature(method)

    def _create_csv_signature(self, method: dict[str, Any]) -> str:
        """Create CSV method signature with full parameter details"""
        return create_csv_signature(method)

    # Format data for output: _format_modifiers
    def _format_modifiers(self, element: dict[str, Any]) -> str:
        """Format element modifiers"""
        return format_typescript_modifiers(element)

    # Format data for output: format_table
    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for TypeScript"""
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original_format_type

    # Format data for output: format_summary
    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for TypeScript"""
        return self._format_compact_table(analysis_result)

    # Format data for output: format_structure
    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for TypeScript"""
        return super().format_structure(analysis_result)

    # Format data for output: format_advanced
    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for TypeScript"""
        if output_format == "json":
            return self._format_json(analysis_result)
        elif output_format == "csv":
            return self._format_csv(analysis_result)
        else:
            return self._format_full_table(analysis_result)

    # Format data for output: _format_json
    def _format_json(self, data: dict[str, Any]) -> str:
        """Format data as JSON"""
        import json

        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return f"# JSON serialization error: {e}\n"
