#!/usr/bin/env python3
"""
HTML Plugin Tests

Test cases for HTML language plugin functionality.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.languages.html_plugin import HtmlElementExtractor, HtmlPlugin
from tree_sitter_analyzer.models import MarkupElement


class TestHtmlElementExtractor:
    """Test HTML element extraction functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.extractor = HtmlElementExtractor()

    def test_element_categories(self):
        """Test HTML element categorization"""
        assert "structure" in self.extractor.element_categories
        assert "heading" in self.extractor.element_categories
        assert "form" in self.extractor.element_categories
        assert "media" in self.extractor.element_categories

    def test_classify_element(self):
        """Test element classification"""
        assert self.extractor._classify_element("div") == "structure"
        assert self.extractor._classify_element("h1") == "heading"
        assert self.extractor._classify_element("p") == "text"
        assert self.extractor._classify_element("img") == "media"
        assert self.extractor._classify_element("form") == "form"
        assert self.extractor._classify_element("table") == "table"
        assert self.extractor._classify_element("unknown_tag") == "unknown"

    def test_extract_functions_returns_empty(self):
        """Test that HTML extractor returns empty list for functions"""
        result = self.extractor.extract_functions(None, "")
        assert result == []

    def test_extract_classes_returns_empty(self):
        """Test that HTML extractor returns empty list for classes"""
        result = self.extractor.extract_classes(None, "")
        assert result == []

    def test_extract_variables_returns_empty(self):
        """Test that HTML extractor returns empty list for variables"""
        result = self.extractor.extract_variables(None, "")
        assert result == []

    def test_extract_imports_returns_empty(self):
        """Test that HTML extractor returns empty list for imports"""
        result = self.extractor.extract_imports(None, "")
        assert result == []


class TestHtmlPlugin:
    """Test HTML plugin functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = HtmlPlugin()

    def test_get_language_name(self):
        """Test language name"""
        assert self.plugin.get_language_name() == "html"

    def test_get_file_extensions(self):
        """Test file extensions"""
        extensions = self.plugin.get_file_extensions()
        assert ".html" in extensions
        assert ".htm" in extensions
        assert ".xhtml" in extensions

    def test_create_extractor(self):
        """Test extractor creation"""
        extractor = self.plugin.create_extractor()
        assert isinstance(extractor, HtmlElementExtractor)

    def test_get_supported_element_types(self):
        """Test supported element types"""
        types = self.plugin.get_supported_element_types()
        assert "html_element" in types

    def test_get_queries(self):
        """Test query retrieval"""
        queries = self.plugin.get_queries()
        assert isinstance(queries, dict)
        assert "element" in queries
        assert "attribute" in queries
        assert "text" in queries

    def test_execute_query_strategy(self):
        """Test query strategy execution"""
        # Test with HTML language
        result = self.plugin.execute_query_strategy("element", "html")
        assert result is not None
        assert "element" in result

        # Test with non-HTML language
        result = self.plugin.execute_query_strategy("element", "python")
        assert result is None

    def test_get_element_categories(self):
        """Test element categories"""
        categories = self.plugin.get_element_categories()
        assert isinstance(categories, dict)
        assert "structure" in categories
        assert "heading" in categories
        assert "form" in categories

    @pytest.mark.asyncio
    async def test_analyze_file_fallback(self):
        """Test HTML file analysis with fallback parsing"""
        # Create a temporary HTML file
        html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <h1>Hello World</h1>
    <p>This is a test paragraph.</p>
    <div class="container">
        <span>Test content</span>
    </div>
</body>
</html>"""

        # Create a mock request
        class MockRequest:
            def __init__(self):
                self.include_source = True
                self.query_filters = {}

        request = MockRequest()

        # Create temporary file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html_content)
            temp_path = f.name

        try:
            # Analyze the file
            result = await self.plugin.analyze_file(temp_path, request)

            # Verify results
            assert result.success
            assert result.language == "html"
            assert result.line_count > 0
            assert len(result.elements) > 0
            assert result.source_code == html_content

            # Check that we have at least one element
            assert any(isinstance(elem, MarkupElement) for elem in result.elements)

        finally:
            # Clean up
            Path(temp_path).unlink()


class TestHtmlIntegration:
    """Integration tests for HTML plugin"""

    def test_markup_element_creation(self):
        """Test MarkupElement creation"""
        element = MarkupElement(
            name="div",
            start_line=1,
            end_line=3,
            raw_text='<div class="test">content</div>',
            language="html",
            tag_name="div",
            attributes={"class": "test"},
            parent=None,
            children=[],
            element_class="structure",
        )

        assert element.name == "div"
        assert element.tag_name == "div"
        assert element.attributes["class"] == "test"
        assert element.element_class == "structure"
        assert element.language == "html"

    def test_markup_element_summary(self):
        """Test MarkupElement summary generation"""
        element = MarkupElement(
            name="h1",
            start_line=5,
            end_line=5,
            raw_text="<h1>Title</h1>",
            language="html",
            tag_name="h1",
            attributes={},
            parent=None,
            children=[],
            element_class="heading",
        )

        summary = element.to_summary_item()
        assert summary["name"] == "h1"
        assert summary["tag_name"] == "h1"
        assert summary["type"] == "html_element"
        assert summary["element_class"] == "heading"
        assert summary["lines"]["start"] == 5
        assert summary["lines"]["end"] == 5

    def test_nested_elements(self):
        """Test nested HTML elements"""
        parent = MarkupElement(
            name="div",
            start_line=1,
            end_line=5,
            raw_text="<div><p>content</p></div>",
            language="html",
            tag_name="div",
            attributes={},
            parent=None,
            children=[],
            element_class="structure",
        )

        child = MarkupElement(
            name="p",
            start_line=2,
            end_line=2,
            raw_text="<p>content</p>",
            language="html",
            tag_name="p",
            attributes={},
            parent=parent,
            children=[],
            element_class="text",
        )

        parent.children.append(child)

        assert len(parent.children) == 1
        assert parent.children[0] == child
        assert child.parent == parent


if __name__ == "__main__":
    pytest.main([__file__])
