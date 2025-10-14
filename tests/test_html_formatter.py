#!/usr/bin/env python3
"""
Tests for HTML Formatter

Tests for HTML-specific formatters including HtmlFormatter, HtmlJsonFormatter,
and HtmlCompactFormatter for MarkupElement and StyleElement formatting.
"""

import json
import pytest

from tree_sitter_analyzer.formatters.html_formatter import (
    HtmlCompactFormatter,
    HtmlFormatter,
    HtmlJsonFormatter,
)
from tree_sitter_analyzer.formatters.formatter_registry import IFormatter
from tree_sitter_analyzer.models import (
    CodeElement,
    Function,
    MarkupElement,
    StyleElement,
    Variable,
)


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
                language="html"
            ),
            MarkupElement(
                name="div",
                start_line=5,
                end_line=15,
                tag_name="div",
                attributes={"class": "container", "id": "main"},
                element_class="structure",
                language="html"
            ),
            MarkupElement(
                name="h1",
                start_line=6,
                end_line=6,
                tag_name="h1",
                attributes={"class": "title"},
                element_class="heading",
                language="html"
            ),
            MarkupElement(
                name="p",
                start_line=8,
                end_line=10,
                tag_name="p",
                attributes={},
                element_class="text",
                language="html"
            ),
            MarkupElement(
                name="img",
                start_line=12,
                end_line=12,
                tag_name="img",
                attributes={"src": "image.jpg", "alt": "Test image"},
                element_class="media",
                language="html"
            )
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
                language="css"
            ),
            StyleElement(
                name=".container",
                start_line=7,
                end_line=12,
                selector=".container",
                properties={"width": "100%", "max-width": "1200px", "margin": "0 auto"},
                element_class="layout",
                language="css"
            ),
            StyleElement(
                name="h1",
                start_line=14,
                end_line=18,
                selector="h1",
                properties={"font-size": "2rem", "color": "#333", "margin-bottom": "1rem"},
                element_class="typography",
                language="css"
            )
        ]
        
        # Create other elements
        self.other_elements = [
            Function(
                name="init",
                start_line=1,
                end_line=5,
                language="javascript"
            ),
            Variable(
                name="config",
                start_line=7,
                end_line=7,
                language="javascript"
            )
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
        mixed_elements = self.markup_elements + self.style_elements + self.other_elements
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
            language="html"
        )
        
        child1 = MarkupElement(
            name="p",
            start_line=2,
            end_line=4,
            tag_name="p",
            attributes={"class": "child"},
            element_class="text",
            language="html",
            parent=parent
        )
        
        child2 = MarkupElement(
            name="span",
            start_line=5,
            end_line=7,
            tag_name="span",
            attributes={"id": "highlight"},
            element_class="text",
            language="html",
            parent=parent
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
                "class": "form-control input-lg"
            },
            element_class="form",
            language="html"
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
                "font-family": "Arial, Helvetica, sans-serif, monospace"
            },
            element_class="layout",
            language="css"
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
            language="html"
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
            language="css"
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
                language="html"
            ),
            StyleElement(
                name=".container",
                start_line=10,
                end_line=15,
                selector=".container",
                properties={"width": "100%"},
                element_class="layout",
                language="css"
            ),
            Function(
                name="init",
                start_line=20,
                end_line=25,
                language="javascript"
            )
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
            language="html"
        )
        
        child = MarkupElement(
            name="h2",
            start_line=2,
            end_line=2,
            tag_name="h2",
            attributes={"class": "title"},
            element_class="heading",
            language="html",
            parent=markup_element
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
            language="css"
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
            name="handleClick",
            start_line=15,
            end_line=20,
            language="javascript"
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
            language="html"
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
                language="html"
            ),
            MarkupElement(
                name="img",
                start_line=7,
                end_line=7,
                tag_name="img",
                attributes={"src": "image.jpg"},
                element_class="media",
                language="html"
            ),
            StyleElement(
                name=".container",
                start_line=10,
                end_line=15,
                selector=".container",
                properties={"width": "100%"},
                element_class="layout",
                language="css"
            ),
            Function(
                name="init",
                start_line=20,
                end_line=25,
                language="javascript"
            )
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
        
        # Check header
        assert "HTML ELEMENTS" in result
        assert "-" * 20 in result
        
        # Check summary
        assert "Total: 4 elements" in result
        assert "Markup: 2" in result
        assert "Style: 1" in result
        assert "Other: 1" in result
        
        # Check element lines with symbols
        assert "🏷️ div <div> #main .container [1-5]" in result
        assert "🏷️ img <img> [7-7]" in result
        assert "🎨 .container .container [10-15]" in result
        assert "📄 init function [20-25]" in result

    def test_format_markup_element_with_attributes(self):
        """Test compact formatting of MarkupElement with attributes"""
        element = MarkupElement(
            name="button",
            start_line=1,
            end_line=1,
            tag_name="button",
            attributes={"id": "submit-btn", "class": "btn-primary"},
            element_class="form",
            language="html"
        )
        
        result = self.formatter.format([element])
        
        # Check that ID and class are included
        assert "🏷️ button <button> #submit-btn .btn-primary [1-1]" in result

    def test_format_markup_element_without_attributes(self):
        """Test compact formatting of MarkupElement without attributes"""
        element = MarkupElement(
            name="br",
            start_line=1,
            end_line=1,
            tag_name="br",
            attributes={},
            element_class="text",
            language="html"
        )
        
        result = self.formatter.format([element])
        
        # Check basic format without attributes
        assert "🏷️ br <br> [1-1]" in result

    def test_format_style_element(self):
        """Test compact formatting of StyleElement"""
        element = StyleElement(
            name="#header",
            start_line=5,
            end_line=10,
            selector="#header",
            properties={"background": "blue"},
            element_class="layout",
            language="css"
        )
        
        result = self.formatter.format([element])
        
        assert "🎨 #header #header [5-10]" in result

    def test_format_other_element(self):
        """Test compact formatting of other CodeElement"""
        element = Variable(
            name="config",
            start_line=1,
            end_line=1,
            language="javascript"
        )
        
        result = self.formatter.format([element])
        
        assert "📄 config variable [1-1]" in result

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
        
        assert "Total: 6 elements" in result
        assert "Markup: 2" in result
        assert "Style: 1" in result
        assert "Other: 3" in result


class TestHtmlFormatterRegistration:
    """Test HTML formatter registration"""

    def test_html_formatters_auto_registration(self):
        """Test that HTML formatters are automatically registered"""
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
        
        available_formats = FormatterRegistry.get_available_formats()
        
        assert "html" in available_formats
        assert "html_json" in available_formats
        assert "html_compact" in available_formats

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
        assert "malformed" in result

    def test_formatter_with_none_values(self):
        """Test formatters with None values"""
        element = MarkupElement(
            name="test",
            start_line=1,
            end_line=1,
            tag_name=None,  # Explicitly None
            attributes=None,  # Explicitly None
            element_class=None  # Explicitly None
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
            language="html"
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
            language="html"
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
                "style": "background: url('image.jpg'); color: #ff0000;"
            },
            element_class="structure",
            language="html"
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