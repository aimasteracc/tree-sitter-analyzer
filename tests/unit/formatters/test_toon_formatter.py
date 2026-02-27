#!/usr/bin/env python3
"""
Targeted tests for ToonFormatter to cover missing lines.

Covers:
- format() error handling (ToonEncodeError and generic Exception fallback)
- _format_internal() AnalysisResult dispatch and ImportError handling
- format_analysis_result() with metadata, summary, elements, classes,
  methods (compact and non-compact), functions
- format_summary(), format_advanced(), format_table()
- _method_to_dict()
- is_toon_content() static method
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.formatters.toon_encoder import ToonEncodeError
from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter
from tree_sitter_analyzer.models import (
    AnalysisResult,
    Class,
    Function,
    JavaPackage,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def formatter():
    """Default ToonFormatter instance."""
    return ToonFormatter()


@pytest.fixture
def formatter_no_fallback():
    """ToonFormatter with fallback_to_json disabled."""
    return ToonFormatter(fallback_to_json=False)


@pytest.fixture
def formatter_no_metadata():
    """ToonFormatter with include_metadata disabled."""
    return ToonFormatter(include_metadata=False)


@pytest.fixture
def formatter_no_compact():
    """ToonFormatter with compact_arrays disabled."""
    return ToonFormatter(compact_arrays=False)


def _make_analysis_result(
    elements=None,
    package=None,
    file_path="test.py",
    language="python",
):
    """Helper to build an AnalysisResult with optional elements/package."""
    return AnalysisResult(
        file_path=file_path,
        language=language,
        elements=elements or [],
        package=package,
    )


# ---------------------------------------------------------------------------
# format() error handling  (lines 78-89)
# ---------------------------------------------------------------------------

class TestFormatErrorHandling:
    """Tests for format() ToonEncodeError and Exception fallback paths."""

    def test_toon_encode_error_with_fallback(self, formatter):
        """ToonEncodeError in _format_internal triggers JSON fallback."""
        with patch.object(
            formatter,
            "_format_internal",
            side_effect=ToonEncodeError("boom"),
        ):
            result = formatter.format({"key": "value"})
            # Fallback produces JSON output
            assert isinstance(result, str)
            assert "key" in result

    def test_toon_encode_error_without_fallback(self, formatter_no_fallback):
        """ToonEncodeError re-raised when fallback_to_json is False."""
        with patch.object(
            formatter_no_fallback,
            "_format_internal",
            side_effect=ToonEncodeError("boom"),
        ):
            with pytest.raises(ToonEncodeError):
                formatter_no_fallback.format({"key": "value"})

    def test_generic_exception_with_fallback(self, formatter):
        """Generic Exception in _format_internal triggers JSON fallback."""
        with patch.object(
            formatter,
            "_format_internal",
            side_effect=RuntimeError("unexpected"),
        ):
            result = formatter.format({"key": "value"})
            assert isinstance(result, str)
            assert "key" in result

    def test_generic_exception_without_fallback(self, formatter_no_fallback):
        """Generic Exception re-raised as ToonEncodeError when no fallback."""
        with patch.object(
            formatter_no_fallback,
            "_format_internal",
            side_effect=RuntimeError("unexpected"),
        ):
            with pytest.raises(ToonEncodeError):
                formatter_no_fallback.format({"key": "value"})


# ---------------------------------------------------------------------------
# _format_internal() – AnalysisResult dispatch  (lines 102-120)
# ---------------------------------------------------------------------------

class TestFormatInternal:
    """Tests for _format_internal routing."""

    def test_analysis_result_dispatches_to_format_analysis_result(self, formatter):
        """AnalysisResult objects route to format_analysis_result."""
        ar = _make_analysis_result()
        result = formatter.format(ar)
        # format_analysis_result produces "file:" metadata
        assert "file:" in result

    def test_non_mcp_dict_dispatches_to_format_structure(self, formatter):
        """Regular dicts (non-MCP) go through format_structure."""
        data = {"name": "foo", "count": 1}
        result = formatter.format(data)
        assert "name:" in result

    def test_non_dict_non_analysis_falls_through_to_encode(self, formatter):
        """Primitives / lists fall through to encoder.encode."""
        result = formatter.format([1, 2, 3])
        assert isinstance(result, str)
        assert "1" in result


# ---------------------------------------------------------------------------
# format_analysis_result()  (lines 137-212)
# ---------------------------------------------------------------------------

class TestFormatAnalysisResult:
    """Tests for the full format_analysis_result method."""

    def test_metadata_section(self, formatter):
        """Include file, language, and package in metadata."""
        pkg = JavaPackage(name="com.example")
        ar = _make_analysis_result(
            file_path="Main.java",
            language="java",
            package=pkg,
        )
        result = formatter.format_analysis_result(ar)
        assert "file: Main.java" in result
        assert "language: java" in result
        assert "package: com.example" in result

    def test_metadata_package_without_name_attr(self, formatter):
        """Package that lacks .name attribute falls back to str()."""
        ar = _make_analysis_result()
        # Use a plain string as package (has no .name)
        ar.package = "some.package.string"
        result = formatter.format_analysis_result(ar)
        assert "package: some.package.string" in result

    def test_no_metadata_when_disabled(self, formatter_no_metadata):
        """Metadata section omitted when include_metadata is False."""
        ar = _make_analysis_result(file_path="skip.py")
        result = formatter_no_metadata.format_analysis_result(ar)
        assert "file:" not in result
        assert "language:" not in result

    def test_summary_section(self, formatter):
        """Summary stats appear when get_summary returns data."""
        ar = _make_analysis_result()
        result = formatter.format_analysis_result(ar)
        assert "summary:" in result
        assert "file_path:" in result

    def test_classes_listed(self, formatter):
        """Classes in elements appear under classes section."""
        elements = [
            Class(name="Foo", start_line=1, end_line=10),
            Class(name="Bar", start_line=11, end_line=20),
        ]
        ar = _make_analysis_result(elements=elements)
        result = formatter.format_analysis_result(ar)
        assert "classes[2]:" in result
        assert "- Foo" in result
        assert "- Bar" in result

    def test_methods_compact_format(self, formatter):
        """Methods rendered with compact array table when compact_arrays=True."""
        elements = [
            Function(
                name="do_thing",
                start_line=5,
                end_line=15,
                element_type="method",
                visibility="public",
            ),
        ]
        ar = _make_analysis_result(elements=elements)
        result = formatter.format_analysis_result(ar)
        assert "methods[1]:" in result
        # Compact table header with schema
        assert "{name" in result or "do_thing" in result

    def test_methods_non_compact_format(self, formatter_no_compact):
        """Methods listed with '- name' when compact_arrays is False."""
        elements = [
            Function(
                name="do_thing",
                start_line=5,
                end_line=15,
                element_type="method",
                visibility="public",
            ),
        ]
        ar = _make_analysis_result(elements=elements)
        result = formatter_no_compact.format_analysis_result(ar)
        assert "methods[1]:" in result
        assert "- do_thing" in result

    def test_functions_listed(self, formatter):
        """Functions in elements appear under functions section."""
        elements = [
            Function(name="helper", start_line=1, end_line=5, element_type="function"),
        ]
        ar = _make_analysis_result(elements=elements)
        result = formatter.format_analysis_result(ar)
        assert "functions[1]:" in result
        assert "- helper" in result

    def test_all_element_types_together(self, formatter):
        """Classes, methods, and functions all appear together."""
        elements = [
            Class(name="Widget", start_line=1, end_line=50),
            Function(name="get_widget", start_line=5, end_line=10, element_type="method", visibility="private"),
            Function(name="free_func", start_line=55, end_line=60, element_type="function"),
        ]
        ar = _make_analysis_result(elements=elements)
        result = formatter.format_analysis_result(ar)
        assert "elements[3]:" in result
        assert "classes[1]:" in result
        assert "methods[1]:" in result
        assert "functions[1]:" in result

    def test_non_analysis_result_dict_delegates(self, formatter):
        """Passing a dict to format_analysis_result routes to format_structure."""
        result = formatter.format_analysis_result({"a": 1})
        assert isinstance(result, str)

    def test_non_analysis_result_non_dict_encodes(self, formatter):
        """Passing a non-dict/non-AnalysisResult encodes directly."""
        result = formatter.format_analysis_result("hello")
        assert isinstance(result, str)

    def test_empty_elements(self, formatter):
        """AnalysisResult with no elements produces no elements section."""
        ar = _make_analysis_result(elements=[])
        result = formatter.format_analysis_result(ar)
        assert "elements" not in result


# ---------------------------------------------------------------------------
# _method_to_dict()  (lines 292-296)
# ---------------------------------------------------------------------------

class TestMethodToDict:
    """Tests for _method_to_dict helper."""

    def test_method_element_to_dict(self, formatter):
        """Converts a proper method element to dict."""
        method = Function(
            name="calculate",
            start_line=10,
            end_line=25,
            element_type="method",
            visibility="protected",
        )
        d = formatter._method_to_dict(method)
        assert d["name"] == "calculate"
        assert d["visibility"] == "protected"
        assert d["lines"] == "10-25"

    def test_method_without_name_attr(self, formatter):
        """Object without .name falls back to str()."""
        obj = 42
        d = formatter._method_to_dict(obj)
        assert d["name"] == "42"
        assert d["visibility"] == ""
        assert d["lines"] == "0-0"


# ---------------------------------------------------------------------------
# format_summary / format_advanced / format_table  (lines 238, 265, 280)
# ---------------------------------------------------------------------------

class TestBaseFormatterMethods:
    """Tests for BaseFormatter requirement methods."""

    def test_format_summary(self, formatter):
        """format_summary encodes dict as TOON."""
        result = formatter.format_summary({"total": 10, "passed": 8})
        assert "total: 10" in result
        assert "passed: 8" in result

    def test_format_advanced(self, formatter):
        """format_advanced encodes dict as TOON regardless of output_format."""
        result = formatter.format_advanced({"depth": 3}, output_format="json")
        assert "depth: 3" in result

    def test_format_table(self, formatter):
        """format_table encodes dict as TOON."""
        result = formatter.format_table({"rows": 5}, table_type="compact")
        assert "rows: 5" in result


# ---------------------------------------------------------------------------
# is_toon_content()  (lines 311-350)
# ---------------------------------------------------------------------------

class TestIsToonContent:
    """Tests for the is_toon_content static method."""

    def test_empty_string_returns_false(self):
        assert ToonFormatter.is_toon_content("") is False

    def test_whitespace_only_returns_false(self):
        assert ToonFormatter.is_toon_content("   \n  ") is False

    def test_json_object_returns_false(self):
        assert ToonFormatter.is_toon_content('{"key": "value"}') is False

    def test_json_array_returns_false(self):
        assert ToonFormatter.is_toon_content('[1, 2, 3]') is False

    def test_valid_toon_key_value_pairs(self):
        """Multiple key: value lines are detected as TOON."""
        content = "name: test\ncount: 42\nactive: true"
        assert ToonFormatter.is_toon_content(content) is True

    def test_single_key_value_not_enough(self):
        """A single key: value line doesn't meet the threshold of 2."""
        content = "name: test"
        assert ToonFormatter.is_toon_content(content) is False

    def test_array_table_header_detected(self):
        """Array table header like [N]{...}: counts for 2 pattern points.

        Note: content starting with '[' is rejected early as JSON-like,
        so the array table header must appear after other TOON content.
        """
        content = "results:\n  [3]{name,age}:\n  Alice,30"
        assert ToonFormatter.is_toon_content(content) is True

    def test_content_starting_with_bracket_returns_false(self):
        """Content whose first char is '[' is rejected as JSON-like."""
        content = "[3]{name,age}:\n  Alice,30"
        assert ToonFormatter.is_toon_content(content) is False

    def test_blank_lines_skipped(self):
        """Blank lines between content are ignored."""
        content = "name: test\n\ncount: 42"
        assert ToonFormatter.is_toon_content(content) is True

    def test_quoted_json_line_not_counted(self):
        """Lines starting with '"' are not counted as key-value."""
        content = '"key": "value"\n"other": "data"'
        assert ToonFormatter.is_toon_content(content) is False

    def test_brace_line_not_counted(self):
        """Lines starting with '{' are not counted as key-value."""
        content = '{key: value}\n{other: data}'
        assert ToonFormatter.is_toon_content(content) is False

    def test_mixed_toon_content(self):
        """Realistic TOON output is detected."""
        content = (
            "file: example.py\n"
            "language: python\n"
            "\n"
            "summary:\n"
            "  class_count: 2\n"
            "  method_count: 5\n"
        )
        assert ToonFormatter.is_toon_content(content) is True

    def test_key_with_empty_value(self):
        """Key with colon but no real key part doesn't count."""
        content = ": only_value\n: another"
        # parts[0].strip() is empty, so these don't count
        assert ToonFormatter.is_toon_content(content) is False
