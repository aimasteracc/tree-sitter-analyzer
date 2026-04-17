"""Coverage tests for base_formatter uncovered methods."""
from __future__ import annotations

from tree_sitter_analyzer.formatters.base_formatter import BaseTableFormatter


class _ConcreteFormatter(BaseTableFormatter):
    """Concrete subclass for testing abstract base."""

    def format_structure(self, data: dict) -> str:
        return f"structured: {len(data)} keys"

    def _format_compact_table(self, analysis_result: dict) -> str:
        return f"compact: {list(analysis_result.keys())}"

    def _format_full_table(self, analysis_result: dict) -> str:
        return f"full: {list(analysis_result.keys())}"


class TestBaseTableFormatter:
    def test_format_with_dict(self) -> None:
        fmt = _ConcreteFormatter(format_type="full")
        result = fmt.format({"key": "value"})
        assert "structured: 1 keys" == result

    def test_format_with_non_dict(self) -> None:
        fmt = _ConcreteFormatter(format_type="full")
        result = fmt.format("just a string")
        assert '"just a string"' in result

    def test_format_summary_uses_compact(self) -> None:
        fmt = _ConcreteFormatter(format_type="compact")
        result = fmt.format_summary({"classes": [{"name": "Foo"}]})
        assert isinstance(result, str)

    def test_format_advanced_json(self) -> None:
        fmt = _ConcreteFormatter(format_type="full")
        result = fmt.format_advanced({"key": "val"}, output_format="json")
        assert "key" in result and "val" in result

    def test_format_advanced_non_json(self) -> None:
        fmt = _ConcreteFormatter(format_type="full")
        result = fmt.format_advanced({"key": "val"}, output_format="full")
        assert isinstance(result, str)

    def test_format_table_temporarily_changes_type(self) -> None:
        fmt = _ConcreteFormatter(format_type="full")
        result = fmt.format_table({"a": 1}, table_type="compact")
        assert fmt.format_type == "full"  # restored after
        assert isinstance(result, str)
