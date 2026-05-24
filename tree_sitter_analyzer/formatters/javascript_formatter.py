#!/usr/bin/env python3
"""
JavaScript-specific table formatter.

Provides specialized formatting for JavaScript code analysis results,
handling modern JavaScript features like ES6+ syntax, async/await,
classes, modules, and framework-specific patterns.
"""

from typing import Any

from ._javascript_formatter_compact_mixin import JavaScriptTableFormatterCompactMixin
from ._javascript_formatter_full_mixin import JavaScriptTableFormatterFullMixin
from ._javascript_formatter_rows_mixin import JavaScriptTableFormatterRowsMixin
from ._javascript_formatter_type_mixin import JavaScriptTableFormatterTypeMixin
from .base_formatter import BaseTableFormatter


def _format_json(data: dict[str, Any]) -> str:
    """Format data as JSON."""
    import json

    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return f"# JSON serialization error: {e}\n"


class JavaScriptTableFormatter(
    JavaScriptTableFormatterFullMixin,
    JavaScriptTableFormatterCompactMixin,
    JavaScriptTableFormatterRowsMixin,
    JavaScriptTableFormatterTypeMixin,
    BaseTableFormatter,
):
    """Table formatter specialized for JavaScript"""

    _format_json = staticmethod(_format_json)

    def format(self, data: dict[str, Any] | None, format_type: str = "full") -> str:
        """Format data using the configured format type"""
        if data is None:
            data = {}

        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data)}")

        if not format_type:
            return self.format_structure(data)

        supported_formats = ["full", "compact", "csv", "json"]
        if format_type not in supported_formats:
            raise ValueError(
                f"Unsupported format type: {format_type}. Supported formats: {supported_formats}"
            )

        if format_type == "json":
            return self._format_json(data)

        original_format = self.format_type
        self.format_type = format_type
        try:
            return self.format_structure(data)
        finally:
            self.format_type = original_format

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for JavaScript"""
        original_format_type = self.format_type
        self.format_type = table_type
        try:
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for JavaScript"""
        return self._format_compact_table(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for JavaScript"""
        if output_format == "json":
            return self._format_json(analysis_result)
        if output_format == "csv":
            return self._format_csv(analysis_result)
        return self._format_full_table(analysis_result)
