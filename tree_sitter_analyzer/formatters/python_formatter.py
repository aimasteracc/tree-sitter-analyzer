#!/usr/bin/env python3
"""
Python-specific table formatter.

Provides specialized formatting for Python code analysis results,
handling modern Python features like async/await, type hints, decorators,
context managers, and framework-specific patterns.
"""

from typing import Any

from ._python_formatter_compact import format_python_compact_table
from ._python_formatter_conversion import (
    convert_analysis_result_to_python_format,
    convert_class_element_for_python,
    convert_function_element_for_python,
    convert_import_element_for_python,
    convert_variable_element_for_python,
    process_python_parameters,
)
from ._python_formatter_full import format_python_full_table
from ._python_formatter_helpers import (
    create_compact_signature,
    extract_module_docstring,
    format_decorators,
    format_python_class_method_row,
    format_python_method_row,
    format_python_signature,
    format_python_signature_compact,
    get_python_visibility_symbol,
    shorten_type,
)
from .base_formatter import BaseTableFormatter


class PythonTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Python"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data using the configured format type"""
        if data is None:
            raise TypeError("Cannot format None data")

        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data)}")

        return self.format_structure(data)

    def format_table(self, data: dict[str, Any], table_type: str = "full") -> str:
        """Format table output for Python files"""
        original_format_type = self.format_type
        self.format_type = table_type
        try:
            result = self.format_structure(data)
            return result
        finally:
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for Python"""
        return self._format_compact_table(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Format structure analysis output for Python"""
        return super().format_structure(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for Python"""
        if output_format == "json":
            return self._format_json(analysis_result)
        elif output_format == "csv":
            return self._format_csv(analysis_result)
        else:
            return self._format_full_table(analysis_result)

    def _format_json(self, data: dict[str, Any]) -> str:
        """Format data as JSON"""
        import json

        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return f"# JSON serialization error: {e}\n"

    def format_analysis_result(
        self, analysis_result: Any, table_type: str = "full"
    ) -> str:
        """Format AnalysisResult directly for Python files - prevents degradation"""
        data = self._convert_analysis_result_to_python_format(analysis_result)
        return self.format_table(data, table_type)

    def _convert_analysis_result_to_python_format(
        self, analysis_result: Any
    ) -> dict[str, Any]:
        """Convert AnalysisResult to Python formatter's expected format"""
        return convert_analysis_result_to_python_format(self, analysis_result)

    def _convert_class_element_for_python(self, element: Any) -> dict[str, Any]:
        """Convert class element for Python formatter"""
        return convert_class_element_for_python(element)

    def _convert_function_element_for_python(self, element: Any) -> dict[str, Any]:
        """Convert function element for Python formatter"""
        return convert_function_element_for_python(self, element)

    def _convert_variable_element_for_python(self, element: Any) -> dict[str, Any]:
        """Convert variable element for Python formatter"""
        return convert_variable_element_for_python(element)

    def _convert_import_element_for_python(self, element: Any) -> dict[str, Any]:
        """Convert import element for Python formatter"""
        return convert_import_element_for_python(element)

    def _process_python_parameters(self, params: Any) -> list[dict[str, str]]:
        """Process parameters for Python formatter"""
        return process_python_parameters(params)

    # Public aliases for companion module _python_formatter_conversion.py
    convert_class_element_for_python = _convert_class_element_for_python
    convert_function_element_for_python = _convert_function_element_for_python
    convert_variable_element_for_python = _convert_variable_element_for_python
    convert_import_element_for_python = _convert_import_element_for_python
    process_python_parameters = _process_python_parameters

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Python"""
        return format_python_full_table(self, data)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Python"""
        return format_python_compact_table(self, data)

    def _format_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for Python"""
        return format_python_method_row(self, method)

    def _create_compact_signature(self, method: dict[str, Any]) -> str:
        """Create compact method signature for Python"""
        return create_compact_signature(method)

    def _shorten_type(self, type_name: Any) -> str:
        """Shorten type name for Python tables"""
        return shorten_type(type_name)

    def _extract_module_docstring(self, data: dict[str, Any]) -> str | None:
        """Extract module-level docstring"""
        return extract_module_docstring(data)

    def _format_python_signature(self, method: dict[str, Any]) -> str:
        """Create Python method signature"""
        return format_python_signature(method)

    def _get_python_visibility_symbol(self, visibility: str) -> str:
        """Get Python visibility symbol"""
        return get_python_visibility_symbol(visibility)

    def _format_decorators(self, decorators: list[str]) -> str:
        """Format Python decorators"""
        return format_decorators(decorators)

    def _format_class_method_row(self, method: dict[str, Any]) -> str:
        """Format a method table row for class-specific sections"""
        return format_python_class_method_row(self, method)

    def _format_python_signature_compact(self, method: dict[str, Any]) -> str:
        """Create compact Python method signature for class sections"""
        return format_python_signature_compact(method)

    # Public aliases for companion formatter helper modules
    create_compact_signature = _create_compact_signature
    extract_module_docstring = _extract_module_docstring
    format_python_signature = _format_python_signature
    get_python_visibility_symbol = _get_python_visibility_symbol
    format_decorators = _format_decorators
    format_class_method_row = _format_class_method_row
    format_python_signature_compact = _format_python_signature_compact
