#!/usr/bin/env python3
"""
Java-specific table formatter.
"""

from typing import Any

from ._java_formatter_class_mixin import JavaTableFormatterClassMixin
from ._java_formatter_compact_mixin import JavaTableFormatterCompactMixin
from ._java_formatter_full_mixin import JavaTableFormatterFullMixin
from ._java_formatter_signatures_mixin import JavaTableFormatterSignaturesMixin
from .base_formatter import BaseTableFormatter


def _format_json(data: dict[str, Any]) -> str:
    """Format data as JSON."""
    import json

    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return f"# JSON serialization error: {e}\n"


class JavaTableFormatter(
    JavaTableFormatterFullMixin,
    JavaTableFormatterClassMixin,
    JavaTableFormatterCompactMixin,
    JavaTableFormatterSignaturesMixin,
    BaseTableFormatter,
):
    """Table formatter specialized for Java"""

    _format_json = staticmethod(_format_json)

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """Format table output for Java"""
        original_format_type = self.format_type
        self.format_type = table_type

        try:
            if table_type == "json":
                return self._format_json(analysis_result)
            return self.format_structure(analysis_result)
        finally:
            self.format_type = original_format_type

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Format summary output for Java"""
        return self._format_compact_table(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Format advanced analysis output for Java"""
        if output_format == "json":
            return self._format_json(analysis_result)
        if output_format == "csv":
            return self._format_csv(analysis_result)
        return self._format_full_table(analysis_result)
