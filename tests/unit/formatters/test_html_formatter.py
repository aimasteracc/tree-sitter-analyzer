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


class TestHtmlFormatterDictInput:
    """Test HtmlFormatter with dictionary element inputs (covers lines 47-57)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def test_format_dict_markup_by_tag_name(self):
        """Test dict elements with tag_name key are converted to markup"""
        elements = [
            {"tag_name": "div", "name": "container", "element_class": "structure",
             "start_line": 1, "end_line": 10, "attributes": {"id": "main"}}
        ]
        result = self.formatter.format(elements)
        assert "## HTML Elements" in result
        assert "container" in result

    def test_format_dict_markup_by_element_type(self):
        """Test dict elements with type=tag are treated as markup"""
        elements = [
            {"type": "tag", "name": "span", "element_class": "text",
             "start_line": 1, "end_line": 1, "attributes": {}}
        ]
        result = self.formatter.format(elements)
        assert "## HTML Elements" in result

    def test_format_dict_markup_by_element_element_type(self):
        """Test dict elements with type=element are treated as markup"""
        elements = [
            {"type": "element", "name": "p", "element_class": "text",
             "start_line": 2, "end_line": 5}
        ]
        result = self.formatter.format(elements)
        assert "## HTML Elements" in result

    def test_format_dict_markup_by_markup_type(self):
        """Test dict elements with type=markup are treated as markup"""
        elements = [
            {"type": "markup", "name": "article", "element_class": "structure",
             "start_line": 1, "end_line": 20}
        ]
        result = self.formatter.format(elements)
        assert "## HTML Elements" in result

    def test_format_dict_style_by_selector(self):
        """Test dict elements with selector key are converted to style"""
        elements = [
            {"selector": ".container", "name": ".container", "element_class": "layout",
             "start_line": 1, "end_line": 5, "properties": {"width": "100%"}}
        ]
        result = self.formatter.format(elements)
        assert "## CSS Rules" in result
        assert "`.container`" in result

    def test_format_dict_style_by_rule_type(self):
        """Test dict elements with type=rule are treated as style"""
        elements = [
            {"type": "rule", "name": "body", "element_class": "layout",
             "start_line": 1, "end_line": 3, "properties": {}}
        ]
        result = self.formatter.format(elements)
        assert "## CSS Rules" in result

    def test_format_dict_style_by_style_type(self):
        """Test dict elements with type=style are treated as style"""
        elements = [
            {"type": "style", "name": "#header", "element_class": "layout",
             "start_line": 1, "end_line": 5}
        ]
        result = self.formatter.format(elements)
        assert "## CSS Rules" in result

    def test_format_dict_other_elements(self):
        """Test dict elements with unknown type go to other"""
        elements = [
            {"type": "unknown", "name": "something", "start_line": 1, "end_line": 1}
        ]
        result = self.formatter.format(elements)
        assert "## Other Elements" in result

    def test_format_dict_other_with_element_type_key(self):
        """Test dict elements using element_type key"""
        elements = [
            {"element_type": "function", "name": "foo", "start_line": 10, "end_line": 20,
             "language": "javascript"}
        ]
        result = self.formatter.format(elements)
        assert "## Other Elements" in result
        assert "function" in result
        assert "foo" in result

    def test_format_mixed_dict_and_objects(self):
        """Test formatting a mix of dict and object elements"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        dict_style = {"selector": "body", "name": "body", "element_class": "layout",
                       "start_line": 10, "end_line": 15, "properties": {"margin": "0"}}
        dict_other = {"type": "unknown", "name": "misc", "start_line": 20, "end_line": 25}

        result = self.formatter.format([markup, dict_style, dict_other])
        assert "## HTML Elements" in result
        assert "## CSS Rules" in result
        assert "## Other Elements" in result


class TestHtmlFormatterSummary:
    """Test format_summary method (covers lines 73-91)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def test_format_summary_empty(self):
        """Test summary with empty elements"""
        result = self.formatter.format_summary({"elements": []})
        assert result == "No HTML elements found."

    def test_format_summary_with_markup_and_style(self):
        """Test summary with markup and style elements"""
        markup = MarkupElement(name="div", start_line=1, end_line=5, tag_name="div")
        style = StyleElement(name="body", start_line=10, end_line=15, selector="body")
        other = Function(name="init", start_line=20, end_line=25, language="javascript")

        result = self.formatter.format_summary({"elements": [markup, style, other]})
        assert "# HTML Analysis Summary" in result
        assert "**Total Elements:** 3" in result
        assert "- Markup Elements: 1" in result
        assert "- Style Elements: 1" in result
        assert "- Other Elements: 1" in result

    def test_format_summary_no_elements_key(self):
        """Test summary with missing elements key"""
        result = self.formatter.format_summary({})
        assert result == "No HTML elements found."


class TestHtmlFormatterStructure:
    """Test format_structure method (covers lines 93-96)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def test_format_structure_delegates_to_format(self):
        """Test that format_structure delegates to format"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format_structure({"elements": [markup]})
        assert "# HTML Structure Analysis" in result
        assert "## HTML Elements" in result


class TestHtmlFormatterAdvanced:
    """Test format_advanced method (covers lines 98-108)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def test_format_advanced_json(self):
        """Test format_advanced with json output"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format_advanced({"elements": [markup]}, output_format="json")
        data = json.loads(result)
        assert "html_analysis" in data
        assert len(data["html_analysis"]["markup_elements"]) == 1

    def test_format_advanced_non_json(self):
        """Test format_advanced with non-json output (falls back to format)"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format_advanced({"elements": [markup]}, output_format="text")
        assert "# HTML Structure Analysis" in result


class TestHtmlFormatterAnalysisResult:
    """Test format_analysis_result method (covers lines 110-131)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def _make_mock_result(self, elements):
        """Create a mock AnalysisResult object"""
        class MockResult:
            def __init__(self, elements):
                self.elements = elements
        return MockResult(elements)

    def test_format_analysis_result_full(self):
        """Test format_analysis_result with full table type"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format_analysis_result(
            self._make_mock_result([markup]), table_type="full"
        )
        assert "# HTML Structure Analysis" in result

    def test_format_analysis_result_compact(self):
        """Test format_analysis_result with compact table type"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format_analysis_result(
            self._make_mock_result([markup]), table_type="compact"
        )
        assert "## Summary" in result

    def test_format_analysis_result_json(self):
        """Test format_analysis_result with json table type"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format_analysis_result(
            self._make_mock_result([markup]), table_type="json"
        )
        data = json.loads(result)
        assert "html_analysis" in data

    def test_format_analysis_result_csv(self):
        """Test format_analysis_result with csv table type"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            attributes={"class": "container"},
            element_class="structure", language="html",
        )
        result = self.formatter.format_analysis_result(
            self._make_mock_result([markup]), table_type="csv"
        )
        assert "Name" in result
        assert "div" in result

    def test_format_analysis_result_no_elements_attr(self):
        """Test format_analysis_result with object lacking elements attr"""
        class NoElements:
            pass
        result = self.formatter.format_analysis_result(NoElements(), table_type="full")
        assert result == "No HTML elements found."


class TestHtmlFormatterFormatTable:
    """Test format_table method (covers lines 133-148)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def test_format_table_compact(self):
        """Test format_table with compact type and file_path"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format_table(
            {"elements": [markup], "file_path": "/path/to/index.html"},
            table_type="compact"
        )
        assert "## Summary" in result
        assert "index" in result

    def test_format_table_json(self):
        """Test format_table with json type"""
        style = StyleElement(
            name="body", start_line=1, end_line=5,
            selector="body", properties={"margin": "0"}, language="css",
        )
        result = self.formatter.format_table(
            {"elements": [style]}, table_type="json"
        )
        data = json.loads(result)
        assert len(data["html_analysis"]["style_elements"]) == 1

    def test_format_table_full_default(self):
        """Test format_table defaults to full format"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format_table(
            {"elements": [markup]}, table_type="full"
        )
        assert "# HTML Structure Analysis" in result


class TestHtmlFormatterOtherElements:
    """Test _format_other_elements (covers lines 277-305 non-dict branch)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def test_format_other_elements_dict(self):
        """Test _format_other_elements with dict elements"""
        elements = [
            {"element_type": "function", "name": "doStuff", "start_line": 1,
             "end_line": 10, "language": "javascript"}
        ]
        lines = self.formatter._format_other_elements(elements)
        output = "\n".join(lines)
        assert "| function | doStuff | 1-10 | javascript |" in output

    def test_format_other_elements_non_dict(self):
        """Test _format_other_elements with non-dict object elements"""
        func = Function(name="init", start_line=1, end_line=5, language="javascript")
        # _element_to_dict is called in format() but _format_other_elements can
        # receive objects too
        elements = [func]
        lines = self.formatter._format_other_elements(elements)
        output = "\n".join(lines)
        assert "init" in output
        assert "javascript" in output


class TestHtmlFormatterAttributeBoolean:
    """Test attribute formatting edge case (covers line 185)"""

    def setup_method(self):
        self.formatter = HtmlFormatter()

    def test_format_markup_element_with_boolean_attribute(self):
        """Test element with attribute that has empty string value (boolean attr)"""
        element = MarkupElement(
            name="input", start_line=1, end_line=1, tag_name="input",
            attributes={"disabled": "", "type": "text"},
            element_class="form", language="html",
        )
        result = self.formatter.format([element])
        # Boolean attribute (empty value) should appear without ="value"
        assert "disabled" in result
        assert 'type="text"' in result


class TestHtmlJsonFormatterDicts:
    """Test HtmlJsonFormatter with dict elements (covers lines 379-397)"""

    def setup_method(self):
        self.formatter = HtmlJsonFormatter()

    def test_format_dict_with_tag_name(self):
        """Test dict with tag_name key goes to markup_elements"""
        elements = [
            {"tag_name": "div", "name": "container", "start_line": 1, "end_line": 5}
        ]
        result = self.formatter.format(elements)
        data = json.loads(result)
        assert len(data["html_analysis"]["markup_elements"]) == 1

    def test_format_dict_with_element_type_tag(self):
        """Test dict with type=element goes to markup_elements"""
        elements = [{"type": "element", "name": "span"}]
        result = self.formatter.format(elements)
        data = json.loads(result)
        assert len(data["html_analysis"]["markup_elements"]) == 1

    def test_format_dict_with_selector(self):
        """Test dict with selector key goes to style_elements"""
        elements = [
            {"selector": ".container", "name": ".container", "start_line": 1, "end_line": 5}
        ]
        result = self.formatter.format(elements)
        data = json.loads(result)
        assert len(data["html_analysis"]["style_elements"]) == 1

    def test_format_dict_with_style_type(self):
        """Test dict with type=style goes to style_elements"""
        elements = [{"type": "style", "name": "h1"}]
        result = self.formatter.format(elements)
        data = json.loads(result)
        assert len(data["html_analysis"]["style_elements"]) == 1

    def test_format_dict_other(self):
        """Test dict with unknown type goes to other_elements"""
        elements = [{"type": "unknown", "name": "misc"}]
        result = self.formatter.format(elements)
        data = json.loads(result)
        assert len(data["html_analysis"]["other_elements"]) == 1


class TestHtmlCompactFormatterFilePath:
    """Test HtmlCompactFormatter file_path handling (covers lines 453-457)"""

    def setup_method(self):
        self.formatter = HtmlCompactFormatter()

    def test_format_with_html_file_path(self):
        """Test filename extraction from .html path"""
        element = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format([element], file_path="/path/to/index.html")
        assert "# index" in result

    def test_format_with_htm_file_path(self):
        """Test filename extraction from .htm path"""
        element = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format([element], file_path="page.htm")
        assert "# page" in result

    def test_format_with_backslash_path(self):
        """Test filename extraction from Windows-style path"""
        element = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format([element], file_path="C:\\web\\site.html")
        assert "# site" in result

    def test_format_with_no_file_path(self):
        """Test default filename when no path provided"""
        element = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        result = self.formatter.format([element])
        assert "# comprehensive_sample" in result

    def test_compact_all_element_classes(self):
        """Test compact formatter categorizes all element classes"""
        elements = [
            MarkupElement(name="html", start_line=1, end_line=100, tag_name="html",
                          element_class="structure", language="html"),
            MarkupElement(name="h1", start_line=5, end_line=5, tag_name="h1",
                          element_class="heading", language="html"),
            MarkupElement(name="p", start_line=10, end_line=12, tag_name="p",
                          element_class="text", language="html"),
            MarkupElement(name="input", start_line=15, end_line=15, tag_name="input",
                          element_class="form", language="html"),
            MarkupElement(name="img", start_line=20, end_line=20, tag_name="img",
                          element_class="media", language="html"),
            MarkupElement(name="table", start_line=25, end_line=30, tag_name="table",
                          element_class="table", language="html"),
            MarkupElement(name="ul", start_line=35, end_line=40, tag_name="ul",
                          element_class="list", language="html"),
            MarkupElement(name="meta", start_line=2, end_line=2, tag_name="meta",
                          element_class="metadata", language="html"),
            MarkupElement(name="custom", start_line=50, end_line=55, tag_name="custom",
                          element_class="custom", language="html"),
        ]
        result = self.formatter.format(elements)
        assert "| Structure | 1 |" in result
        assert "| Headings | 1 |" in result
        assert "| Text | 1 |" in result
        assert "| Forms | 1 |" in result
        assert "| Media | 1 |" in result
        assert "| Tables | 1 |" in result
        assert "| Lists | 1 |" in result
        assert "| Metadata | 1 |" in result
        assert "| Other | 1 |" in result

    def test_compact_more_than_20_important_elements(self):
        """Test compact formatter limits to 20 top-level elements"""
        elements = []
        for i in range(25):
            elements.append(MarkupElement(
                name=f"section{i}", start_line=i * 10, end_line=i * 10 + 5,
                tag_name="section", element_class="structure", language="html",
            ))
        result = self.formatter.format(elements)
        assert "more)" in result

    def test_compact_structural_tags_included(self):
        """Test that important structural tags appear in top-level elements even with parent"""
        parent = MarkupElement(
            name="html", start_line=1, end_line=100, tag_name="html",
            element_class="structure", language="html",
        )
        body = MarkupElement(
            name="body", start_line=5, end_line=95, tag_name="body",
            element_class="structure", language="html", parent=parent,
        )
        parent.children = [body]
        result = self.formatter.format([parent, body])
        # body is a structural tag, should still appear
        assert "`body`" in result or "`html`" in result


class TestHtmlCsvFormatter:
    """Test HtmlCsvFormatter (covers lines 577-675)"""

    def setup_method(self):
        from tree_sitter_analyzer.formatters.html_formatter import HtmlCsvFormatter
        self.formatter = HtmlCsvFormatter()

    def test_get_format_name(self):
        """Test CSV formatter format name"""
        assert self.formatter.get_format_name() == "html_csv"

    def test_format_markup_element(self):
        """Test CSV formatting of MarkupElement"""
        element = MarkupElement(
            name="div", start_line=1, end_line=10, tag_name="div",
            attributes={"class": "container", "id": "main"},
            element_class="structure", language="html",
        )
        result = self.formatter.format([element])
        assert "Name" in result  # Header
        assert "div" in result
        assert "structure" in result
        assert "class=container" in result

    def test_format_markup_element_empty_attr_value(self):
        """Test CSV formatting with boolean attribute (empty value)"""
        element = MarkupElement(
            name="input", start_line=1, end_line=1, tag_name="input",
            attributes={"disabled": "", "type": "text"},
            element_class="form", language="html",
        )
        result = self.formatter.format([element])
        assert "disabled" in result
        assert "type=text" in result

    def test_format_style_element(self):
        """Test CSV formatting of StyleElement"""
        element = StyleElement(
            name=".container", start_line=1, end_line=5,
            selector=".container",
            properties={"width": "100%", "margin": "0"},
            element_class="layout", language="css",
        )
        result = self.formatter.format([element])
        assert ".container" in result
        assert "layout" in result
        assert "width:100%" in result

    def test_format_dict_element(self):
        """Test CSV formatting of dict element"""
        element = {
            "name": "test", "tag_name": "div",
            "element_class": "structure",
            "start_line": 1, "end_line": 5,
            "attributes": {"class": "main"},
            "children_count": 3, "language": "html",
        }
        result = self.formatter.format([element])
        assert "test" in result
        assert "div" in result

    def test_format_generic_element(self):
        """Test CSV formatting of generic CodeElement (else branch)"""
        func = Function(
            name="handleClick", start_line=10, end_line=20, language="javascript"
        )
        result = self.formatter.format([func])
        assert "handleClick" in result
        assert "javascript" in result

    def test_format_empty_list(self):
        """Test CSV formatting of empty list"""
        result = self.formatter.format([])
        # Should have header only
        assert "Name" in result
        lines = result.strip().split("\n")
        assert len(lines) == 1  # Header only

    def test_format_mixed_elements(self):
        """Test CSV formatting of mixed element types"""
        markup = MarkupElement(
            name="div", start_line=1, end_line=5, tag_name="div",
            element_class="structure", language="html",
        )
        style = StyleElement(
            name="body", start_line=10, end_line=15, selector="body",
            properties={"margin": "0"}, element_class="layout", language="css",
        )
        dict_elem = {"name": "test", "selector": "h1", "start_line": 20, "end_line": 25}
        func = Function(name="init", start_line=30, end_line=35, language="javascript")

        result = self.formatter.format([markup, style, dict_elem, func])
        lines = result.strip().split("\n")
        assert len(lines) == 5  # Header + 4 data rows

    def test_format_style_no_properties(self):
        """Test CSV formatting of StyleElement with no properties"""
        element = StyleElement(
            name="*", start_line=1, end_line=1, selector="*",
            properties={}, element_class="layout", language="css",
        )
        result = self.formatter.format([element])
        assert "*" in result


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
