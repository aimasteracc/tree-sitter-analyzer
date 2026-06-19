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


class TestJavaScriptModuleLevelFunctions:
    """Module-level (non-class) functions must render in the full table.

    Regression: the full table previously rendered only classes and their
    methods, silently dropping every top-level function.
    """

    def test_flat_module_functions_render(self, fmt):
        data = {
            "file_path": "/x/util.js",
            "classes": [],
            "methods": [
                {
                    "name": "alpha",
                    "line_range": {"start": 1, "end": 1},
                    "parameters": ["a"],
                    "return_type": "number",
                    "complexity_score": 1,
                },
                {
                    "name": "beta",
                    "line_range": {"start": 2, "end": 4},
                    "parameters": ["b"],
                    "return_type": "number",
                    "complexity_score": 2,
                },
            ],
        }
        result = fmt._format_full_table(data)
        assert "## Global Functions" in result
        assert "| alpha |" in result
        assert "| beta |" in result

    def test_top_level_function_alongside_class(self, fmt):
        data = {
            "file_path": "/x/mixed.js",
            "classes": [
                {"name": "C", "line_range": {"start": 5, "end": 7}},
            ],
            "methods": [
                {
                    "name": "topLevel",
                    "line_range": {"start": 1, "end": 3},
                    "parameters": ["x"],
                    "return_type": "number",
                    "complexity_score": 2,
                },
                {
                    "name": "method",
                    "line_range": {"start": 6, "end": 6},
                    "parameters": ["y"],
                    "return_type": "number",
                    "complexity_score": 1,
                },
            ],
        }
        result = fmt._format_full_table(data)
        # The class method stays under its class; the top-level function does not.
        assert "## Global Functions" in result
        assert "| topLevel |" in result
        global_section = result.split("## Global Functions", 1)[1]
        assert "topLevel" in global_section
        assert "| method |" not in global_section

    def test_plugin_shaped_functions_key_render(self, fmt):
        """Top-level functions arrive under 'functions' (JS plugin shape),
        not 'methods'; they must still render. (Codex P2 on #1092)"""
        data = {
            "file_path": "/x/util.js",
            "classes": [],
            "methods": [],
            "functions": [
                {
                    "name": "gamma",
                    "line_range": {"start": 1, "end": 2},
                    "parameters": ["g"],
                    "return_type": "number",
                    "complexity_score": 1,
                }
            ],
        }
        result = fmt._format_full_table(data)
        assert "## Global Functions" in result
        assert "| gamma |" in result
