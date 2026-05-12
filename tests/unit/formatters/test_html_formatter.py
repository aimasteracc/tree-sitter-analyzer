#!/usr/bin/env python3
"""
Tests for HTML Formatter

Tests for HTML-specific formatters including HtmlFormatter, HtmlJsonFormatter,
and HtmlCompactFormatter for MarkupElement and StyleElement formatting.
"""

import json

import pytest

from tree_sitter_analyzer.formatters.formatter_registry import IFormatter
from tree_sitter_analyzer.formatters.html_formatter import (
    HtmlCompactFormatter,
    HtmlCsvFormatter,
    HtmlFormatter,
    HtmlJsonFormatter,
)
from tree_sitter_analyzer.models import Function, MarkupElement, StyleElement, Variable


class TestHtmlFormatter:
    """Test HtmlFormatter functionality"""

    def setup_method(self):
        """Setup test data"""
        self.formatter = HtmlFormatter()

        # Create test MarkupElements
        self.markup_elements = [
            MarkupElement(
                name="html",
                start_line=1,
                end_line=20,
                tag_name="html",
                attributes={"lang": "en"},
                element_class="structure",
                language="html",
            ),
            MarkupElement(
                name="div",
                start_line=5,
                end_line=15,
                tag_name="div",
                attributes={"class": "container", "id": "main"},
                element_class="structure",
                language="html",
            ),
            MarkupElement(
                name="h1",
                start_line=6,
                end_line=6,
                tag_name="h1",
                attributes={"class": "title"},
                element_class="heading",
                language="html",
            ),
            MarkupElement(
                name="p",
                start_line=8,
                end_line=10,
                tag_name="p",
                attributes={},
                element_class="text",
                language="html",
            ),
            MarkupElement(
                name="img",
                start_line=12,
                end_line=12,
                tag_name="img",
                attributes={"src": "image.jpg", "alt": "Test image"},
                element_class="media",
                language="html",
            ),
        ]

        # Create test StyleElements
        self.style_elements = [
            StyleElement(
                name="body",
                start_line=1,
                end_line=5,
                selector="body",
                properties={"margin": "0", "padding": "0", "font-family": "Arial"},
                element_class="layout",
                language="css",
            ),
            StyleElement(
                name=".container",
                start_line=7,
                end_line=12,
                selector=".container",
                properties={"width": "100%", "max-width": "1200px", "margin": "0 auto"},
                element_class="layout",
                language="css",
            ),
            StyleElement(
                name="h1",
                start_line=14,
                end_line=18,
                selector="h1",
                properties={
                    "font-size": "2rem",
                    "color": "#333",
                    "margin-bottom": "1rem",
                },
                element_class="typography",
                language="css",
            ),
        ]

        # Create other elements
        self.other_elements = [
            Function(name="init", start_line=1, end_line=5, language="javascript"),
            Variable(name="config", start_line=7, end_line=7, language="javascript"),
        ]

    def test_formatter_inheritance(self):
        """Test that HtmlFormatter inherits from IFormatter"""
        assert isinstance(self.formatter, IFormatter)

    def test_get_format_name(self):
        """Test format name"""
        assert self.formatter.get_format_name() == "html"

    def test_format_empty_list(self):
        """Test formatting empty element list"""
        result = self.formatter.format([])
        assert result == "No HTML elements found."

    def test_format_markup_elements_only(self):
        """Test formatting only MarkupElements"""
        result = self.formatter.format(self.markup_elements)

        # Check basic structure
        assert "# HTML Structure Analysis" in result
        assert "## HTML Elements" in result

        # Check element groups
        assert "### Structure Elements (2)" in result
        assert "### Heading Elements (1)" in result
        assert "### Text Elements (1)" in result
        assert "### Media Elements (1)" in result

        # Check table headers
        assert "| Tag | Name | Lines | Attributes | Children |" in result

        # Check specific elements
        assert "`html`" in result
        assert "`div`" in result
        assert "`h1`" in result
        assert "`p`" in result
        assert "`img`" in result

        # Check attributes
        assert 'lang="en"' in result
        assert 'class="container"' in result
        assert 'id="main"' in result

    def test_format_style_elements_only(self):
        """Test formatting only StyleElements"""
        result = self.formatter.format(self.style_elements)

        # Check basic structure
        assert "# HTML Structure Analysis" in result
        assert "## CSS Rules" in result

        # Check element groups
        assert "### Layout Rules (2)" in result
        assert "### Typography Rules (1)" in result

        # Check table headers
        assert "| Selector | Properties | Lines |" in result

        # Check specific selectors
        assert "`body`" in result
        assert "`.container`" in result
        assert "`h1`" in result

        # Check properties
        assert "margin: 0" in result
        assert "width: 100%" in result
        assert "font-size: 2rem" in result

    def test_format_mixed_elements(self):
        """Test formatting mixed element types"""
        mixed_elements = (
            self.markup_elements + self.style_elements + self.other_elements
        )
        result = self.formatter.format(mixed_elements)

        # Check all sections are present
        assert "## HTML Elements" in result
        assert "## CSS Rules" in result
        assert "## Other Elements" in result

        # Check markup elements
        assert "### Structure Elements" in result
        assert "### Heading Elements" in result

        # Check style elements
        assert "### Layout Rules" in result
        assert "### Typography Rules" in result

        # Check other elements
        assert "function" in result
        assert "variable" in result
        assert "javascript" in result

    def test_format_element_hierarchy(self):
        """Test element hierarchy formatting"""
        # Create parent-child relationship
        parent = MarkupElement(
            name="div",
            start_line=1,
            end_line=10,
            tag_name="div",
            attributes={"class": "parent"},
            element_class="structure",
            language="html",
        )

        child1 = MarkupElement(
            name="p",
            start_line=2,
            end_line=4,
            tag_name="p",
            attributes={"class": "child"},
            element_class="text",
            language="html",
            parent=parent,
        )

        child2 = MarkupElement(
            name="span",
            start_line=5,
            end_line=7,
            tag_name="span",
            attributes={"id": "highlight"},
            element_class="text",
            language="html",
            parent=parent,
        )

        parent.children = [child1, child2]

        elements = [parent, child1, child2]
        result = self.formatter.format(elements)

        # Check hierarchy section
        assert "### Element Hierarchy" in result
        assert "- `div`" in result
        assert "  - `p`" in result
        assert "  - `span`" in result

        # Check attributes in hierarchy
        assert 'class="parent"' in result
        assert 'class="child"' in result
        assert 'id="highlight"' in result

    def test_format_long_attributes(self):
        """Test formatting with long attributes"""
        element = MarkupElement(
            name="input",
            start_line=1,
            end_line=1,
            tag_name="input",
            attributes={
                "type": "text",
                "name": "very_long_field_name",
                "placeholder": "This is a very long placeholder text that should be truncated",
                "data-validation": "required|min:5|max:100",
                "class": "form-control input-lg",
            },
            element_class="form",
            language="html",
        )

        result = self.formatter.format([element])

        # Check that long attributes are truncated
        assert "..." in result

    def test_format_long_css_properties(self):
        """Test formatting with long CSS properties"""
        element = StyleElement(
            name=".complex",
            start_line=1,
            end_line=10,
            selector=".complex",
            properties={
                "background": "linear-gradient(45deg, #ff0000, #00ff00, #0000ff)",
                "box-shadow": "0 4px 8px rgba(0,0,0,0.1), 0 6px 20px rgba(0,0,0,0.15)",
                "transform": "translateX(-50%) translateY(-50%) scale(1.2) rotate(45deg)",
                "font-family": "Arial, Helvetica, sans-serif, monospace",
            },
            element_class="layout",
            language="css",
        )

        result = self.formatter.format([element])

        # Check that long properties are truncated
        assert "..." in result

    def test_format_elements_without_attributes(self):
        """Test formatting elements without attributes"""
        element = MarkupElement(
            name="br",
            start_line=1,
            end_line=1,
            tag_name="br",
            attributes={},
            element_class="text",
            language="html",
        )

        result = self.formatter.format([element])

        # Check that empty attributes show as dash
        assert "| `br` | br | 1-1 | - | 0 |" in result

    def test_format_elements_without_properties(self):
        """Test formatting CSS elements without properties"""
        element = StyleElement(
            name="*",
            start_line=1,
            end_line=1,
            selector="*",
            properties={},
            element_class="layout",
            language="css",
        )

        result = self.formatter.format([element])

        # Check that empty properties show as dash
        assert "| `*` | - | 1-1 |" in result


class TestHtmlJsonFormatter:
    """Test HtmlJsonFormatter functionality"""

    def setup_method(self):
        """Setup test data"""
        self.formatter = HtmlJsonFormatter()

        self.test_elements = [
            MarkupElement(
                name="div",
                start_line=1,
                end_line=5,
                tag_name="div",
                attributes={"class": "container"},
                element_class="structure",
                language="html",
            ),
            StyleElement(
                name=".container",
                start_line=10,
                end_line=15,
                selector=".container",
                properties={"width": "100%"},
                element_class="layout",
                language="css",
            ),
            Function(name="init", start_line=20, end_line=25, language="javascript"),
        ]

    def test_formatter_inheritance(self):
        """Test that HtmlJsonFormatter inherits from IFormatter"""
        assert isinstance(self.formatter, IFormatter)

    def test_get_format_name(self):
        """Test format name"""
        assert self.formatter.get_format_name() == "html_json"

    def test_format_mixed_elements(self):
        """Test JSON formatting of mixed elements"""
        result = self.formatter.format(self.test_elements)

        # Parse JSON to verify structure
        data = json.loads(result)

        assert "html_analysis" in data
        analysis = data["html_analysis"]

        assert analysis["total_elements"] == 3
        assert len(analysis["markup_elements"]) == 1
        assert len(analysis["style_elements"]) == 1
        assert len(analysis["other_elements"]) == 1

    def test_format_markup_element_json(self):
        """Test MarkupElement JSON formatting"""
        markup_element = MarkupElement(
            name="article",
            start_line=1,
            end_line=20,
            tag_name="article",
            attributes={"class": "post", "id": "post-1"},
            element_class="structure",
            language="html",
        )

        child = MarkupElement(
            name="h2",
            start_line=2,
            end_line=2,
            tag_name="h2",
            attributes={"class": "title"},
            element_class="heading",
            language="html",
            parent=markup_element,
        )

        markup_element.children = [child]

        result = self.formatter.format([markup_element, child])
        data = json.loads(result)

        markup_data = data["html_analysis"]["markup_elements"][0]

        assert markup_data["name"] == "article"
        assert markup_data["tag_name"] == "article"
        assert markup_data["element_class"] == "structure"
        assert markup_data["start_line"] == 1
        assert markup_data["end_line"] == 20
        assert markup_data["attributes"] == {"class": "post", "id": "post-1"}
        assert markup_data["children_count"] == 1
        assert len(markup_data["children"]) == 1
        assert markup_data["children"][0]["name"] == "h2"

    def test_format_style_element_json(self):
        """Test StyleElement JSON formatting"""
        style_element = StyleElement(
            name="#header",
            start_line=5,
            end_line=10,
            selector="#header",
            properties={"background": "blue", "height": "60px"},
            element_class="layout",
            language="css",
        )

        result = self.formatter.format([style_element])
        data = json.loads(result)

        style_data = data["html_analysis"]["style_elements"][0]

        assert style_data["name"] == "#header"
        assert style_data["selector"] == "#header"
        assert style_data["element_class"] == "layout"
        assert style_data["start_line"] == 5
        assert style_data["end_line"] == 10
        assert style_data["properties"] == {"background": "blue", "height": "60px"}
        assert style_data["language"] == "css"

    def test_format_other_element_json(self):
        """Test other CodeElement JSON formatting"""
        function_element = Function(
            name="handleClick", start_line=15, end_line=20, language="javascript"
        )

        result = self.formatter.format([function_element])
        data = json.loads(result)

        other_data = data["html_analysis"]["other_elements"][0]

        assert other_data["name"] == "handleClick"
        assert other_data["type"] == "function"
        assert other_data["start_line"] == 15
        assert other_data["end_line"] == 20
        assert other_data["language"] == "javascript"

    def test_format_empty_list(self):
        """Test JSON formatting of empty list"""
        result = self.formatter.format([])
        data = json.loads(result)

        analysis = data["html_analysis"]
        assert analysis["total_elements"] == 0
        assert len(analysis["markup_elements"]) == 0
        assert len(analysis["style_elements"]) == 0
        assert len(analysis["other_elements"]) == 0

    def test_json_unicode_handling(self):
        """Test JSON formatting with Unicode content"""
        element = MarkupElement(
            name="タイトル",
            start_line=1,
            end_line=1,
            tag_name="h1",
            attributes={"class": "日本語"},
            element_class="heading",
            language="html",
        )

        result = self.formatter.format([element])
        data = json.loads(result)

        markup_data = data["html_analysis"]["markup_elements"][0]
        assert markup_data["name"] == "タイトル"
        assert markup_data["attributes"]["class"] == "日本語"


class TestHtmlCompactFormatter:
    """Test HtmlCompactFormatter functionality"""

    def setup_method(self):
        """Setup test data"""
        self.formatter = HtmlCompactFormatter()

        self.test_elements = [
            MarkupElement(
                name="div",
                start_line=1,
                end_line=5,
                tag_name="div",
                attributes={"class": "container", "id": "main"},
                element_class="structure",
                language="html",
            ),
            MarkupElement(
                name="img",
                start_line=7,
                end_line=7,
                tag_name="img",
                attributes={"src": "image.jpg"},
                element_class="media",
                language="html",
            ),
            StyleElement(
                name=".container",
                start_line=10,
                end_line=15,
                selector=".container",
                properties={"width": "100%"},
                element_class="layout",
                language="css",
            ),
            Function(name="init", start_line=20, end_line=25, language="javascript"),
        ]

    def test_formatter_inheritance(self):
        """Test that HtmlCompactFormatter inherits from IFormatter"""
        assert isinstance(self.formatter, IFormatter)

    def test_get_format_name(self):
        """Test format name"""
        assert self.formatter.get_format_name() == "html_compact"

    def test_format_mixed_elements(self):
        """Test compact formatting of mixed elements"""
        result = self.formatter.format(self.test_elements)

        # Check header and summary table format
        assert "## Summary" in result
        assert "| Element Type | Count |" in result

        # Check element counts in table
        assert "| Structure | 1 |" in result
        assert "| Media | 1 |" in result
        assert "| CSS Rules | 1 |" in result
        assert "| **Total** | **4** |" in result

        # Check top-level elements table
        assert "## Top-Level Elements" in result
        assert "| Tag | ID/Class | Lines | Children |" in result

    def test_format_markup_element_with_attributes(self):
        """Test compact formatting of MarkupElement with attributes"""
        element = MarkupElement(
            name="button",
            start_line=1,
            end_line=1,
            tag_name="button",
            attributes={"id": "submit-btn", "class": "btn-primary"},
            element_class="form",
            language="html",
        )

        result = self.formatter.format([element])

        # Check that element is in top-level table
        assert "| `button` |" in result
        assert "| Forms | 1 |" in result

    def test_format_markup_element_without_attributes(self):
        """Test compact formatting of MarkupElement without attributes"""
        element = MarkupElement(
            name="br",
            start_line=1,
            end_line=1,
            tag_name="br",
            attributes={},
            element_class="text",
            language="html",
        )

        result = self.formatter.format([element])

        # Check element is in summary table
        assert "| Text | 1 |" in result
        assert "| **Total** | **1** |" in result

    def test_format_style_element(self):
        """Test compact formatting of StyleElement"""
        element = StyleElement(
            name="#header",
            start_line=5,
            end_line=10,
            selector="#header",
            properties={"background": "blue"},
            element_class="layout",
            language="css",
        )

        result = self.formatter.format([element])

        # Check CSS rule in summary
        assert "| CSS Rules | 1 |" in result
        assert "| **Total** | **1** |" in result

    def test_format_other_element(self):
        """Test compact formatting of other CodeElement"""
        element = Variable(
            name="config", start_line=1, end_line=1, language="javascript"
        )

        result = self.formatter.format([element])

        # Non-markup elements should still be counted in total
        assert "| **Total** | **1** |" in result

    def test_format_empty_list(self):
        """Test compact formatting of empty list"""
        result = self.formatter.format([])
        assert result == "No HTML elements found."

    def test_format_counts_accuracy(self):
        """Test that element counts are accurate"""
        markup_elements = [
            MarkupElement(name="div", start_line=1, end_line=1, tag_name="div"),
            MarkupElement(name="p", start_line=2, end_line=2, tag_name="p"),
        ]

        style_elements = [
            StyleElement(name=".test", start_line=3, end_line=3, selector=".test"),
        ]

        other_elements = [
            Function(name="func1", start_line=4, end_line=4),
            Function(name="func2", start_line=5, end_line=5),
            Variable(name="var1", start_line=6, end_line=6),
        ]

        all_elements = markup_elements + style_elements + other_elements
        result = self.formatter.format(all_elements)

        # Check total count in new table format
        assert "| **Total** | **6** |" in result
        # Check CSS rules count
        assert "| CSS Rules | 1 |" in result


class TestHtmlFormatterRegistration:
    """Test HTML formatter registration"""

    @pytest.mark.skip(
        reason="HTML formatters intentionally excluded in v1.6.1.4 for format specification compliance"
    )
    def test_html_formatters_auto_registration(self):
        """Test that HTML formatters are automatically registered"""
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry

        available_formats = FormatterRegistry.get_available_formats()

        assert "html" in available_formats
        assert "html_json" in available_formats
        assert "html_compact" in available_formats

    @pytest.mark.skip(
        reason="HTML formatters intentionally excluded in v1.6.1.4 for format specification compliance"
    )
    def test_get_html_formatters(self):
        """Test getting HTML formatter instances"""
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry

        html_formatter = FormatterRegistry.get_formatter("html")
        html_json_formatter = FormatterRegistry.get_formatter("html_json")
        html_compact_formatter = FormatterRegistry.get_formatter("html_compact")

        assert isinstance(html_formatter, HtmlFormatter)
        assert isinstance(html_json_formatter, HtmlJsonFormatter)
        assert isinstance(html_compact_formatter, HtmlCompactFormatter)


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
        self.func = Function(name="init", start_line=1, end_line=3, language="javascript")

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
        output = self.formatter.format_analysis_result("plain_string", table_type="full")
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


class TestHtmlFormatterFalsyAttributes:
    """Cover attribute formatting with falsy values (line 185)"""

    def test_markup_with_empty_string_attribute(self):
        """Format markup element with empty string attribute value"""
        formatter = HtmlFormatter()
        elem = MarkupElement(
            name="input",
            start_line=1,
            end_line=1,
            tag_name="input",
            attributes={"disabled": "", "type": "text"},
            element_class="form",
            language="html",
        )
        result = formatter.format([elem])
        assert "disabled" in result

    def test_markup_with_none_attribute(self):
        """Format markup element with None attribute value"""
        formatter = HtmlFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={"hidden": None, "data-x": "val"},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem])
        assert "hidden" in result

    def test_markup_with_boolean_false_attribute(self):
        """Format markup element with False attribute value"""
        formatter = HtmlFormatter()
        elem = MarkupElement(
            name="span",
            start_line=1,
            end_line=1,
            tag_name="span",
            attributes={"contenteditable": False},
            element_class="text",
            language="html",
        )
        result = formatter.format([elem])
        assert "contenteditable" in result


class TestHtmlFormatterUnknownElementType:
    """Cover getattr fallback for unknown element types (lines 295-299)"""

    def test_unknown_object_in_format(self):
        """Format with unknown object type uses getattr fallback"""
        formatter = HtmlFormatter()

        class UnknownType:
            pass

        obj = UnknownType()
        obj.element_type = "custom"
        obj.name = "my_custom"
        obj.start_line = 10
        obj.end_line = 20
        obj.language = "xml"

        result = formatter.format([obj])
        # Should appear in the "Other elements" section
        assert "custom" in result


class TestHtmlOtherElementsNonDict:
    """Cover HtmlJsonFormatter dict element handling (lines 381-393)"""

    def test_json_format_dict_with_tag_name(self):
        """JSON format dict element with tag_name"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "test_div",
            "tag_name": "div",
            "element_class": "structure",
            "start_line": 1,
            "end_line": 10,
            "attributes": {},
            "language": "html",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["markup_elements"]) == 1

    def test_json_format_dict_with_element_type_tag(self):
        """JSON format dict element with type='tag'"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "header",
            "element_type": "tag",
            "start_line": 1,
            "end_line": 5,
            "language": "html",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["markup_elements"]) == 1

    def test_json_format_dict_with_selector(self):
        """JSON format dict element with selector"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "body_rule",
            "selector": "body",
            "element_class": "layout",
            "start_line": 1,
            "end_line": 20,
            "language": "css",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["style_elements"]) == 1

    def test_json_format_dict_with_type_rule(self):
        """JSON format dict element with element_type='rule'"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "h1_rule",
            "element_type": "rule",
            "start_line": 5,
            "end_line": 10,
            "language": "css",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["style_elements"]) == 1

    def test_json_format_dict_unknown_type(self):
        """JSON format dict element with unknown type goes to other"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "custom_thing",
            "element_type": "weird_type",
            "start_line": 1,
            "end_line": 1,
            "language": "text",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["other_elements"]) == 1


class TestHtmlCompactFormatterFilepath:
    """Cover filename extraction in compact formatter (lines 455-457)"""

    def test_filepath_html_extension_stripped(self):
        """Compact format strips .html extension from filename"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem], file_path="/path/to/index.html")
        assert "# index" in result

    def test_filepath_htm_extension_stripped(self):
        """Compact format strips .htm extension from filename"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem], file_path="/path/to/page.htm")
        assert "# page" in result

    def test_filepath_non_html_extension_kept(self):
        """Compact format keeps non-html filename as-is"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem], file_path="/path/to/component.jsx")
        assert "# component.jsx" in result

    def test_filepath_backslash_path(self):
        """Compact format handles Windows-style backslash paths"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem], file_path="C:\\project\\layout.html")
        assert "# layout" in result


class TestHtmlCompactElementClassification:
    """Cover element classification in compact formatter (lines 481-493)"""

    def test_heading_element_classification(self):
        """Compact format classifies heading elements"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="h1",
            start_line=1,
            end_line=1,
            tag_name="h1",
            attributes={},
            element_class="heading",
            language="html",
        )
        result = formatter.format([elem])
        assert "| Headings | 1 |" in result

    def test_table_element_classification(self):
        """Compact format classifies table elements"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="table",
            start_line=1,
            end_line=10,
            tag_name="table",
            attributes={},
            element_class="table",
            language="html",
        )
        result = formatter.format([elem])
        assert "| Tables | 1 |" in result

    def test_list_element_classification(self):
        """Compact format classifies list elements"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="ul",
            start_line=1,
            end_line=10,
            tag_name="ul",
            attributes={},
            element_class="list",
            language="html",
        )
        result = formatter.format([elem])
        assert "| Lists | 1 |" in result

    def test_metadata_element_classification(self):
        """Compact format classifies metadata elements"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="meta",
            start_line=1,
            end_line=1,
            tag_name="meta",
            attributes={"charset": "utf-8"},
            element_class="metadata",
            language="html",
        )
        result = formatter.format([elem])
        assert "| Metadata | 1 |" in result


class TestHtmlCompactOver20Elements:
    """Cover >20 elements truncation message (line 570)"""

    def test_more_than_20_important_elements(self):
        """Compact format shows '(N more)' when >20 important elements"""
        formatter = HtmlCompactFormatter()
        # Create 25 root-level divs (parent=None means they're "important")
        elements = []
        for i in range(25):
            elem = MarkupElement(
                name=f"div{i}",
                start_line=i * 2 + 1,
                end_line=i * 2 + 2,
                tag_name="div",
                attributes={"id": f"item{i}", "class": "box"},
                element_class="structure",
                language="html",
            )
            elements.append(elem)

        result = formatter.format(elements)
        # Should show first 20 in the table
        for i in range(20):
            assert f"#item{i}" in result
        # Should show "5 more" row
        assert "5 more" in result


class TestHtmlFormatOtherElementsNonDict:
    """Cover _format_other_elements getattr fallback (lines 295-299)"""

    def test_format_other_elements_non_dict_non_markup(self):
        """Directly call _format_other_elements with non-dict, non-MarkupElement"""
        formatter = HtmlFormatter()

        class UnknownThing:
            pass

        obj = UnknownThing()
        obj.element_type = "weird"
        obj.name = "thingo"
        obj.start_line = 5
        obj.end_line = 15
        obj.language = "nolang"

        # Call _format_other_elements directly (bypasses _element_to_dict)
        result_lines = formatter._format_other_elements([obj])
        result = "\n".join(result_lines)
        assert "weird" in result
        assert "thingo" in result
        assert "5-15" in result
        assert "nolang" in result
