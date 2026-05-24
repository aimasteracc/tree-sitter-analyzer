"""Cover uncovered branches in javascript_formatter.py (67.8% -> 90%+).

Targets:
- Line 46: TypeError for non-dict input
- Line 49: empty format_type string -> format_structure
- Lines 71-76: format_table() format_type save/restore
- Line 80: format_summary() -> _format_compact_table
- Lines 86-90: format_advanced() json/csv/default paths
"""

import pytest

from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


@pytest.fixture
def fmt():
    return JavaScriptTableFormatter()


@pytest.fixture
def sample_data():
    return {
        "file_path": "app.js",
        "imports": [{"name": "react", "path": "react"}],
        "exports": [{"name": "App", "type": "default"}],
        "classes": [{"name": "App", "methods": ["render"]}],
        "functions": [{"name": "handler", "params": ["req", "res"]}],
        "variables": [{"name": "count", "kind": "let"}],
        "statistics": {"function_count": 1, "class_count": 1},
    }


class TestFormatNonDictInput:
    def test_format_raises_typeerror_for_list(self, fmt):
        with pytest.raises(TypeError, match="Expected dict, got <class 'list'>"):
            fmt.format([1, 2, 3], "full")

    def test_format_raises_typeerror_for_string(self, fmt):
        with pytest.raises(TypeError, match="Expected dict, got <class 'str'>"):
            fmt.format("not a dict", "full")

    def test_format_raises_typeerror_for_int(self, fmt):
        with pytest.raises(TypeError, match="Expected dict, got <class 'int'>"):
            fmt.format(42, "full")

    def test_format_raises_typeerror_for_tuple(self, fmt):
        with pytest.raises(TypeError, match="Expected dict, got <class 'tuple'>"):
            fmt.format((1, 2), "full")


class TestFormatEmptyFormatType:
    def test_empty_string_calls_format_structure(self, fmt, sample_data):
        result = fmt.format(sample_data, "")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_none_format_type_calls_format_structure(self, fmt, sample_data):
        result = fmt.format(sample_data, None)
        assert isinstance(result, str)


class TestFormatTable:
    def test_format_table_full(self, fmt, sample_data):
        result = fmt.format_table(sample_data, "full")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_table_compact(self, fmt, sample_data):
        result = fmt.format_table(sample_data, "compact")
        assert isinstance(result, str)

    def test_format_table_restores_format_type(self, fmt, sample_data):
        original = fmt.format_type
        fmt.format_table(sample_data, "compact")
        assert fmt.format_type == original

    def test_format_table_json_unsupported(self, fmt, sample_data):
        with pytest.raises(ValueError, match="Unsupported format type: json"):
            fmt.format_table(sample_data, "json")

    def test_format_table_default_type(self, fmt, sample_data):
        result = fmt.format_table(sample_data)
        assert isinstance(result, str)
        assert len(result) > 0


class TestFormatSummary:
    def test_format_summary_returns_string(self, fmt, sample_data):
        result = fmt.format_summary(sample_data)
        assert isinstance(result, str)

    def test_format_summary_empty_data(self, fmt):
        result = fmt.format_summary({"file_path": "empty.js"})
        assert isinstance(result, str)

    def test_format_summary_with_statistics(self, fmt):
        data = {
            "file_path": "mod.js",
            "statistics": {"function_count": 5, "class_count": 2},
        }
        result = fmt.format_summary(data)
        assert isinstance(result, str)


class TestFormatAdvanced:
    def test_format_advanced_json(self, fmt, sample_data):
        result = fmt.format_advanced(sample_data, "json")
        assert isinstance(result, str)
        assert '"file_path"' in result

    def test_format_advanced_csv(self, fmt, sample_data):
        result = fmt.format_advanced(sample_data, "csv")
        assert isinstance(result, str)

    def test_format_advanced_default_fallback(self, fmt, sample_data):
        result = fmt.format_advanced(sample_data, "full")
        assert isinstance(result, str)

    def test_format_advanced_default_output_format(self, fmt, sample_data):
        result = fmt.format_advanced(sample_data)
        assert isinstance(result, str)
        assert '"file_path"' in result

    def test_format_advanced_non_json_non_csv(self, fmt, sample_data):
        result = fmt.format_advanced(sample_data, "markdown")
        assert isinstance(result, str)
