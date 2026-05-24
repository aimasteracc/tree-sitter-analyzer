#!/usr/bin/env python3
"""
Tests for HTML Formatter (basic)

Tests for HTML-specific formatters including HtmlFormatter, HtmlJsonFormatter,
HtmlCompactFormatter, registration, edge cases, coverage gaps, table formatting,
dict conversion, and CSV formatter coverage.
"""

import json

from tests.unit.formatters._test_html_formatter_mixin import (
    TestHtmlCompactFormatterMixin,
    TestHtmlFormatterMixin,
    TestHtmlFormatterRegistrationMixin,
    TestHtmlJsonFormatterMixin,
)
from tree_sitter_analyzer.formatters.formatter_registry import IFormatter
from tree_sitter_analyzer.formatters.html_formatter import (
    HtmlCompactFormatter,
    HtmlCsvFormatter,
    HtmlFormatter,
    HtmlJsonFormatter,
)
from tree_sitter_analyzer.models import Function, MarkupElement, StyleElement


class TestHtmlFormatter(TestHtmlFormatterMixin):
    """Test HtmlFormatter functionality"""

    __test__ = True


class TestHtmlJsonFormatter(TestHtmlJsonFormatterMixin):
    """Test HtmlJsonFormatter functionality"""

    __test__ = True


class TestHtmlCompactFormatter(TestHtmlCompactFormatterMixin):
    """Test HtmlCompactFormatter functionality"""

    __test__ = True


class TestHtmlFormatterRegistration(TestHtmlFormatterRegistrationMixin):
    """Test HTML formatter registration"""

    __test__ = True


class TestHtmlFormatterEdgeCases:
    """Test edge cases and error conditions"""

    def test_formatter_with_malformed_elements(self):
        """Test formatters with malformed elements"""

        # Create element with missing attributes
        class MalformedMarkupElement(MarkupElement):
            def __init__(self):
                super().__init__(name="malformed", start_line=1, end_line=1)
                # Don't set tag_name or other expected attributes

        malformed = MalformedMarkupElement()

        # Test that formatters handle missing attributes gracefully
        html_formatter = HtmlFormatter()
        result = html_formatter.format([malformed])
        assert "malformed" in result

        json_formatter = HtmlJsonFormatter()
        result = json_formatter.format([malformed])
        data = json.loads(result)
        assert len(data["html_analysis"]["markup_elements"]) == 1

        compact_formatter = HtmlCompactFormatter()
        result = compact_formatter.format([malformed])
        # Compact formatter uses table format, check that it doesn't crash
        assert "## Summary" in result
        assert "| **Total** | **1** |" in result

    def test_formatter_with_none_values(self):
        """Test formatters with None values"""
        element = MarkupElement(
            name="test",
            start_line=1,
            end_line=1,
            tag_name=None,  # Explicitly None
            attributes=None,  # Explicitly None
            element_class=None,  # Explicitly None
        )

        html_formatter = HtmlFormatter()
        result = html_formatter.format([element])
        # Should not crash
        assert isinstance(result, str)

    def test_formatter_with_unicode_content(self):
        """Test formatters with Unicode content"""
        element = MarkupElement(
            name="テスト",  # Japanese
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={"title": "こんにちは"},  # Japanese
            element_class="structure",
            language="html",
        )

        html_formatter = HtmlFormatter()
        result = html_formatter.format([element])
        assert "テスト" in result
        assert "こんにちは" in result

        json_formatter = HtmlJsonFormatter()
        result = json_formatter.format([element])
        data = json.loads(result)
        markup_data = data["html_analysis"]["markup_elements"][0]
        assert markup_data["name"] == "テスト"
        assert markup_data["attributes"]["title"] == "こんにちは"

    def test_formatter_with_very_long_content(self):
        """Test formatters with very long content"""
        long_attributes = {f"attr{i}": f"value{i}" * 100 for i in range(50)}

        element = MarkupElement(
            name="test",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes=long_attributes,
            element_class="structure",
            language="html",
        )

        html_formatter = HtmlFormatter()
        result = html_formatter.format([element])
        # Should handle long content without issues
        assert isinstance(result, str)
        assert len(result) > 0

    def test_formatter_with_special_characters(self):
        """Test formatters with special characters"""
        element = MarkupElement(
            name="test",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={
                "data-test": "value with spaces",
                "onclick": "alert('Hello \"World\"');",
                "style": "background: url('image.jpg'); color: #ff0000;",
            },
            element_class="structure",
            language="html",
        )

        html_formatter = HtmlFormatter()
        result = html_formatter.format([element])
        # Should handle special characters properly
        assert isinstance(result, str)

        json_formatter = HtmlJsonFormatter()
        result = json_formatter.format([element])
        # Should produce valid JSON
        data = json.loads(result)
        assert len(data["html_analysis"]["markup_elements"]) == 1


def test_html_formatter_summary():
    formatter = HtmlFormatter()
    result = {"file_path": "test.html", "language": "html", "elements": []}
    output = formatter.format_summary(result)
    assert isinstance(output, str)


def test_html_formatter_structure():
    formatter = HtmlFormatter()
    result = {"file_path": "test.html", "language": "html", "classes": []}
    output = formatter.format_structure(result)
    assert isinstance(output, str)


def test_html_formatter_advanced():
    formatter = HtmlFormatter()
    result = {"file_path": "test.html", "language": "html"}
    output = formatter.format_advanced(result)
    assert isinstance(output, str)


# === Coverage-targeted tests: format_summary, format_advanced, format_analysis_result ===


class TestHtmlFormatterCoverageGap:
    """Tests targeting uncovered code paths in HtmlFormatter"""

    def setup_method(self):
        self.formatter = HtmlFormatter()
        self.markup = MarkupElement(
            name="div",
            start_line=1,
            end_line=5,
            tag_name="div",
            attributes={"class": "container"},
            element_class="structure",
            language="html",
        )
        self.style = StyleElement(
            name="body",
            start_line=1,
            end_line=3,
            selector="body",
            properties={"margin": "0"},
            element_class="layout",
            language="css",
        )
        self.func = Function(
            name="init", start_line=1, end_line=3, language="javascript"
        )

    def _make_result(self, elements):
        """Create an analysis result object with .elements attribute"""

        class AR:
            pass

        ar = AR()
        ar.elements = elements
        return ar

    def test_format_summary_with_markup_only(self):
        """format_summary with only MarkupElements (lines 79-91)"""
        result = {"file_path": "t.html", "language": "html", "elements": [self.markup]}
        output = self.formatter.format_summary(result)
        assert "**Total Elements:** 1" in output
        assert "- Markup Elements: 1" in output
        assert "- Style Elements: 0" in output
        assert "- Other Elements: 0" in output

    def test_format_summary_with_style_only(self):
        """format_summary with only StyleElements"""
        result = {"file_path": "t.css", "language": "css", "elements": [self.style]}
        output = self.formatter.format_summary(result)
        assert "- Markup Elements: 0" in output
        assert "- Style Elements: 1" in output

    def test_format_summary_with_mixed_elements(self):
        """format_summary with mixed element types"""
        result = {
            "file_path": "t.html",
            "language": "html",
            "elements": [self.markup, self.style, self.func],
        }
        output = self.formatter.format_summary(result)
        assert "**Total Elements:** 3" in output
        assert "- Markup Elements: 1" in output
        assert "- Style Elements: 1" in output
        assert "- Other Elements: 1" in output

    def test_format_advanced_non_json(self):
        """format_advanced with non-JSON output_format (line 108)"""
        result = {
            "file_path": "t.html",
            "language": "html",
            "elements": [self.markup],
        }
        output = self.formatter.format_advanced(result, output_format="text")
        assert "# HTML Structure Analysis" in output

    def test_format_analysis_result_compact(self):
        """format_analysis_result with compact table_type (lines 120-122)"""
        ar = self._make_result([self.markup])
        output = self.formatter.format_analysis_result(ar, table_type="compact")
        assert "## Summary" in output

    def test_format_analysis_result_json(self):
        """format_analysis_result with json table_type (lines 123-125)"""
        ar = self._make_result([self.markup])
        output = self.formatter.format_analysis_result(ar, table_type="json")
        data = json.loads(output)
        assert "html_analysis" in data
        assert len(data["html_analysis"]["markup_elements"]) == 1

    def test_format_analysis_result_csv(self):
        """format_analysis_result with csv table_type (lines 126-128)"""
        ar = self._make_result([self.markup])
        output = self.formatter.format_analysis_result(ar, table_type="csv")
        assert "Name" in output
        assert "div" in output

    def test_format_analysis_result_full_default(self):
        """format_analysis_result with full table_type goes to else (line 129-131)"""
        ar = self._make_result([self.markup])
        output = self.formatter.format_analysis_result(ar, table_type="full")
        assert "# HTML Structure Analysis" in output

    def test_format_analysis_result_unknown_type_falls_to_default(self):
        """format_analysis_result with unknown table_type falls to else (line 131)"""
        ar = self._make_result([self.markup])
        output = self.formatter.format_analysis_result(ar, table_type="unknown")
        assert "# HTML Structure Analysis" in output

    def test_format_analysis_result_with_analysis_result_object(self):
        """format_analysis_result with object that has .elements (line 115-116)"""

        class FakeAnalysisResult:
            def __init__(self):
                self.elements = [
                    MarkupElement(
                        name="span",
                        start_line=1,
                        end_line=1,
                        tag_name="span",
                        attributes={},
                        element_class="inline",
                        language="html",
                    )
                ]

        fake = FakeAnalysisResult()
        output = self.formatter.format_analysis_result(fake, table_type="full")
        assert "span" in output

    def test_format_analysis_result_without_elements_attr(self):
        """format_analysis_result with object lacking .elements (line 118)"""
        output = self.formatter.format_analysis_result(
            "plain_string", table_type="full"
        )
        assert "No HTML elements found" in output


class TestHtmlFormatTable:
    """Tests for format_table method (lines 133-217)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()
        self.markup = MarkupElement(
            name="div",
            start_line=1,
            end_line=5,
            tag_name="div",
            attributes={"class": "main", "id": "app"},
            element_class="structure",
            language="html",
        )
        self.style = StyleElement(
            name="body_style",
            start_line=1,
            end_line=3,
            selector="body",
            properties={"margin": "0", "padding": "0"},
            element_class="layout",
            language="css",
        )

    def test_format_table_full(self):
        """format_table with full output"""
        result = {"elements": [self.markup, self.style]}
        output = self.formatter.format_table(result, table_type="full")
        assert "| Tag | Name | Lines | Attributes | Children |" in output
        assert "div" in output
        assert "Structure Elements" in output

    def test_format_table_compact(self):
        """format_table with compact output"""
        result = {"elements": [self.markup]}
        output = self.formatter.format_table(result, table_type="compact")
        assert "## Summary" in output
        assert "div" in output

    def test_format_table_json(self):
        """format_table with json output"""
        result = {"elements": [self.markup]}
        output = self.formatter.format_table(result, table_type="json")
        data = json.loads(output)
        assert "html_analysis" in data

    def test_format_table_empty(self):
        """format_table with empty elements"""
        result = {"elements": []}
        output = self.formatter.format_table(result)
        assert "No HTML elements found" in output


class TestHtmlFormatDictConversion:
    """Tests for dict-to-element conversion in HtmlFormatter.format()"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def test_format_dict_with_tag_name(self):
        """format() with dict containing tag_name (line 50-51)"""
        elements = [{"tag_name": "div", "type": "tag", "attributes": {}}]
        output = self.formatter.format(elements)
        assert "# HTML Structure Analysis" in output
        assert "div" in output

    def test_format_dict_with_selector(self):
        """format() with dict containing selector (line 52-53)"""
        elements = [{"selector": "body", "type": "rule", "properties": {"margin": "0"}}]
        output = self.formatter.format(elements)
        assert "body" in output

    def test_format_dict_unknown_type(self):
        """format() with dict of unknown type goes to other_elements (line 54-55)"""
        elements = [{"type": "unknown", "data": "something"}]
        output = self.formatter.format(elements)
        assert isinstance(output, str)

    def test_format_dict_element_type_fallback(self):
        """format() with element_type field instead of type (line 49)"""
        elements = [{"element_type": "tag", "tag_name": "p", "attributes": {}}]
        output = self.formatter.format(elements)
        assert "p" in output


class TestHtmlCsvFormatterCoverage:
    """Tests for HtmlCsvFormatter.format() - entire class uncovered"""

    def setup_method(self):
        self.formatter = HtmlCsvFormatter()

    def test_get_format_name(self):
        assert self.formatter.get_format_name() == "html_csv"

    def test_format_markup_element(self):
        """CSV format with MarkupElement (lines 600-624)"""
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=5,
            tag_name="div",
            attributes={"class": "container", "id": "main"},
            element_class="structure",
            language="html",
        )
        result = self.formatter.format([elem])
        assert "div" in result
        assert "structure" in result
        assert "class=container" in result
        assert "1" in result
        assert "5" in result

    def test_format_markup_element_empty_attributes(self):
        """CSV format MarkupElement with empty attributes (line 622)"""
        elem = MarkupElement(
            name="br",
            start_line=1,
            end_line=1,
            tag_name="br",
            attributes={},
            element_class="inline",
            language="html",
        )
        result = self.formatter.format([elem])
        assert "br" in result

    def test_format_markup_element_none_attributes(self):
        """CSV format MarkupElement with None attributes"""
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes=None,
            element_class="structure",
            language="html",
        )
        result = self.formatter.format([elem])
        assert isinstance(result, str)

    def test_format_markup_attribute_boolean_value(self):
        """CSV format with boolean attribute value (line 621)"""
        elem = MarkupElement(
            name="input",
            start_line=1,
            end_line=1,
            tag_name="input",
            attributes={"disabled": True, "readonly": False},
            element_class="form",
            language="html",
        )
        result = self.formatter.format([elem])
        assert "disabled" in result
        assert "readonly" in result

    def test_format_markup_attribute_empty_string(self):
        """CSV format with empty string attribute value (line 618-621)"""
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={"hidden": ""},
            element_class="structure",
            language="html",
        )
        result = self.formatter.format([elem])
        assert "hidden" in result

    def test_format_style_element(self):
        """CSV format with StyleElement (lines 625-638)"""
        elem = StyleElement(
            name="body_style",
            start_line=1,
            end_line=3,
            selector="body",
            properties={"margin": "0", "padding": "0"},
            element_class="layout",
            language="css",
        )
        result = self.formatter.format([elem])
        assert "body" in result
        assert "layout" in result
        assert "margin:0" in result
        assert "padding:0" in result

    def test_format_style_element_empty_properties(self):
        """CSV format StyleElement with empty properties (line 633-636)"""
        elem = StyleElement(
            name="empty_style",
            start_line=1,
            end_line=1,
            selector="*",
            properties={},
            element_class="reset",
            language="css",
        )
        result = self.formatter.format([elem])
        assert "*" in result

    def test_format_dict_element(self):
        """CSV format with dict element (lines 639-649)"""
        elem = {
            "name": "test_div",
            "tag_name": "div",
            "element_class": "structure",
            "start_line": 3,
            "end_line": 7,
            "attributes": {"class": "test"},
            "children_count": 2,
            "language": "html",
        }
        result = self.formatter.format([elem])
        assert "test_div" in result
        assert "div" in result
        assert "3" in result

    def test_format_dict_with_selector(self):
        """CSV format dict with selector instead of tag_name (line 641)"""
        elem = {
            "name": "test_rule",
            "selector": "h1",
            "element_class": "typography",
            "start_line": 1,
            "end_line": 1,
            "properties": {"font-size": "2rem"},
            "children_count": 0,
            "language": "css",
        }
        result = self.formatter.format([elem])
        assert "test_rule" in result
        assert "h1" in result

    def test_format_unknown_object_type(self):
        """CSV format with unknown object using getattr (lines 651-658)"""

        class UnknownElement:
            pass

        elem = UnknownElement()
        elem.name = "unknown"
        elem.tag_name = "custom"
        elem.element_class = "special"
        elem.start_line = 10
        elem.end_line = 20
        elem.language = "xml"

        result = self.formatter.format([elem])
        assert "unknown" in result
        assert "custom" in result

    def test_format_unknown_object_no_tag_name(self):
        """CSV format unknown object with selector but no tag_name (line 652)"""

        class UnknownElement:
            pass

        elem = UnknownElement()
        elem.name = "styled"
        elem.selector = ".main"
        elem.element_class = "layout"
        elem.start_line = 1
        elem.end_line = 1
        elem.language = "css"

        result = self.formatter.format([elem])
        assert "styled" in result
        assert ".main" in result

    def test_format_multiple_elements(self):
        """CSV format with multiple element types"""
        markup = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={"class": "box"},
            element_class="structure",
            language="html",
        )
        style = StyleElement(
            name="div_rule",
            start_line=1,
            end_line=1,
            selector=".box",
            properties={"color": "red"},
            element_class="style",
            language="css",
        )
        d = {
            "name": "inline",
            "tag_name": "span",
            "element_class": "inline",
            "start_line": 5,
            "end_line": 5,
            "attributes": {},
            "children_count": 1,
            "language": "html",
        }
        result = self.formatter.format([markup, style, d])
        assert "div" in result
        assert ".box" in result
        assert "span" in result

    def test_is_i_formatter(self):
        """HtmlCsvFormatter is an IFormatter"""
        assert isinstance(self.formatter, IFormatter)
