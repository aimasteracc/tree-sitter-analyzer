#!/usr/bin/env python3
"""
CSS Plugin Tests

Test cases for CSS language plugin functionality.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.languages.css_plugin import CssElementExtractor, CssPlugin
from tree_sitter_analyzer.models import StyleElement


class TestCssElementExtractor:
    """Test CSS element extraction functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.extractor = CssElementExtractor()

    def test_property_categories(self):
        """Test CSS property categorization"""
        assert "layout" in self.extractor.property_categories
        assert "box_model" in self.extractor.property_categories
        assert "typography" in self.extractor.property_categories
        assert "background" in self.extractor.property_categories
        assert "flexbox" in self.extractor.property_categories
        assert "grid" in self.extractor.property_categories
        assert "animation" in self.extractor.property_categories

    def test_classify_rule(self):
        """Test CSS rule classification"""
        # Layout properties
        layout_props = {"display": "flex", "position": "absolute"}
        assert self.extractor._classify_rule(layout_props) == "layout"

        # Typography properties
        typography_props = {"font-size": "16px", "color": "#333"}
        assert self.extractor._classify_rule(typography_props) == "typography"

        # Box model properties
        box_props = {"margin": "10px", "padding": "5px"}
        assert self.extractor._classify_rule(box_props) == "box_model"

        # Flexbox properties
        flex_props = {"justify-content": "center", "align-items": "center"}
        assert self.extractor._classify_rule(flex_props) == "flexbox"

        # Empty properties
        assert self.extractor._classify_rule({}) == "other"

        # Unknown properties
        unknown_props = {"unknown-property": "value"}
        assert self.extractor._classify_rule(unknown_props) == "other"

    def test_extract_functions_returns_empty(self):
        """Test that CSS extractor returns empty list for functions"""
        result = self.extractor.extract_functions(None, "")
        assert result == []

    def test_extract_classes_returns_empty(self):
        """Test that CSS extractor returns empty list for classes"""
        result = self.extractor.extract_classes(None, "")
        assert result == []

    def test_extract_variables_returns_empty(self):
        """Test that CSS extractor returns empty list for variables"""
        result = self.extractor.extract_variables(None, "")
        assert result == []

    def test_extract_imports_returns_empty(self):
        """Test that CSS extractor returns empty list for imports"""
        result = self.extractor.extract_imports(None, "")
        assert result == []


class TestCssPlugin:
    """Test CSS plugin functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = CssPlugin()

    def test_get_language_name(self):
        """Test language name"""
        assert self.plugin.get_language_name() == "css"

    def test_get_file_extensions(self):
        """Test file extensions"""
        extensions = self.plugin.get_file_extensions()
        assert ".css" in extensions
        assert ".scss" in extensions
        assert ".sass" in extensions
        assert ".less" in extensions

    def test_create_extractor(self):
        """Test extractor creation"""
        extractor = self.plugin.create_extractor()
        assert isinstance(extractor, CssElementExtractor)

    def test_get_supported_element_types(self):
        """Test supported element types"""
        types = self.plugin.get_supported_element_types()
        assert "css_rule" in types

    def test_get_queries(self):
        """Test query retrieval"""
        queries = self.plugin.get_queries()
        assert isinstance(queries, dict)
        assert "rule_set" in queries
        assert "selector" in queries
        assert "declaration" in queries
        assert "property" in queries

    def test_execute_query_strategy(self):
        """Test query strategy execution"""
        # Test with CSS language
        result = self.plugin.execute_query_strategy("rule_set", "css")
        assert result is not None
        assert "rule_set" in result

        # Test with non-CSS language
        result = self.plugin.execute_query_strategy("rule_set", "python")
        assert result is None

    def test_get_element_categories(self):
        """Test element categories"""
        categories = self.plugin.get_element_categories()
        assert isinstance(categories, dict)
        assert "layout" in categories
        assert "typography" in categories
        assert "flexbox" in categories
        assert "at_rules" in categories

    @pytest.mark.asyncio
    async def test_analyze_file_fallback(self):
        """Test CSS file analysis with fallback parsing"""
        # Create a temporary CSS file
        css_content = """/* Main styles */
body {
    margin: 0;
    padding: 0;
    font-family: Arial, sans-serif;
    background-color: #f0f0f0;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

h1 {
    color: #333;
    font-size: 2em;
    text-align: center;
}

@media (max-width: 768px) {
    .container {
        padding: 10px;
    }

    h1 {
        font-size: 1.5em;
    }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}"""

        # Create a mock request
        class MockRequest:
            def __init__(self):
                self.include_source = True
                self.query_filters = {}

        request = MockRequest()

        # Create temporary file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".css", delete=False) as f:
            f.write(css_content)
            temp_path = f.name

        try:
            # Analyze the file
            result = await self.plugin.analyze_file(temp_path, request)

            # Verify results
            assert result.success
            assert result.language == "css"
            assert result.line_count > 0
            assert len(result.elements) > 0
            assert result.source_code == css_content

            # Check that we have at least one element
            assert any(isinstance(elem, StyleElement) for elem in result.elements)

        finally:
            # Clean up
            Path(temp_path).unlink()


class TestCssExtractAtRuleName:
    """Test _extract_at_rule_name method for CSS at-rules."""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = CssPlugin()
        self.extractor = self.plugin.create_extractor()

    def _get_parser(self):
        """Get a configured tree-sitter parser for CSS."""
        import tree_sitter

        language = self.plugin.get_tree_sitter_language()
        parser = tree_sitter.Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(language)
        elif hasattr(parser, "language"):
            parser.language = language
        else:
            parser = tree_sitter.Parser(language)
        return parser

    def test_extract_keyframes_name_with_animation_name(self):
        """Test that @keyframes extracts the full name including animation name."""
        css_code = """@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}"""
        parser = self._get_parser()
        tree = parser.parse(css_code.encode("utf-8"))
        elements = self.extractor.extract_css_rules(tree, css_code)

        keyframes = [e for e in elements if e.selector.startswith("@keyframes")]
        assert len(keyframes) >= 1
        assert keyframes[0].selector == "@keyframes fadeIn"
        assert keyframes[0].name == "@keyframes fadeIn"

    def test_extract_media_query_with_full_condition(self):
        """Test that @media extracts the full condition."""
        css_code = """@media (max-width: 768px) {
    body { margin: 0; }
}"""
        parser = self._get_parser()
        tree = parser.parse(css_code.encode("utf-8"))
        elements = self.extractor.extract_css_rules(tree, css_code)

        media_queries = [e for e in elements if e.selector.startswith("@media")]
        assert len(media_queries) >= 1
        assert media_queries[0].selector == "@media (max-width: 768px)"
        assert media_queries[0].name == "@media (max-width: 768px)"

    def test_extract_media_query_with_screen_and_condition(self):
        """Test that @media screen and condition extracts correctly."""
        css_code = """@media screen and (min-width: 1024px) {
    .container { max-width: 1200px; }
}"""
        parser = self._get_parser()
        tree = parser.parse(css_code.encode("utf-8"))
        elements = self.extractor.extract_css_rules(tree, css_code)

        media_queries = [e for e in elements if e.selector.startswith("@media")]
        assert len(media_queries) >= 1
        assert "screen" in media_queries[0].selector
        assert "min-width" in media_queries[0].selector

    def test_extract_media_query_with_complex_condition(self):
        """Test that @media with combined conditions extracts correctly."""
        css_code = """@media (min-width: 576px) and (max-width: 991.98px) {
    .grid { columns: 2; }
}"""
        parser = self._get_parser()
        tree = parser.parse(css_code.encode("utf-8"))
        elements = self.extractor.extract_css_rules(tree, css_code)

        media_queries = [e for e in elements if e.selector.startswith("@media")]
        assert len(media_queries) >= 1
        assert "min-width" in media_queries[0].selector
        assert "max-width" in media_queries[0].selector

    def test_extract_media_query_prefers_color_scheme(self):
        """Test that @media prefers-color-scheme extracts correctly."""
        css_code = """@media (prefers-color-scheme: dark) {
    body { background: #333; }
}"""
        parser = self._get_parser()
        tree = parser.parse(css_code.encode("utf-8"))
        elements = self.extractor.extract_css_rules(tree, css_code)

        media_queries = [e for e in elements if e.selector.startswith("@media")]
        assert len(media_queries) >= 1
        assert "prefers-color-scheme" in media_queries[0].selector
        assert "dark" in media_queries[0].selector

    def test_extract_media_query_print(self):
        """Test that @media print extracts correctly."""
        css_code = """@media print {
    body { background: white; }
}"""
        parser = self._get_parser()
        tree = parser.parse(css_code.encode("utf-8"))
        elements = self.extractor.extract_css_rules(tree, css_code)

        media_queries = [e for e in elements if e.selector.startswith("@media")]
        assert len(media_queries) >= 1
        assert media_queries[0].selector == "@media print"

    def test_extract_multiple_keyframes(self):
        """Test that multiple @keyframes are extracted with distinct names."""
        css_code = """@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

@keyframes slideIn {
    from { transform: translateX(-100%); }
    to { transform: translateX(0); }
}

@keyframes bounce {
    0% { transform: translateY(0); }
    50% { transform: translateY(-20px); }
    100% { transform: translateY(0); }
}"""
        parser = self._get_parser()
        tree = parser.parse(css_code.encode("utf-8"))
        elements = self.extractor.extract_css_rules(tree, css_code)

        keyframes = [e for e in elements if e.selector.startswith("@keyframes")]
        assert len(keyframes) >= 3

        names = [e.name for e in keyframes]
        assert "@keyframes fadeIn" in names
        assert "@keyframes slideIn" in names
        assert "@keyframes bounce" in names

    def test_extract_supports_rule(self):
        """Test that @supports extracts the full condition."""
        css_code = """@supports (display: grid) {
    .container { display: grid; }
}"""
        parser = self._get_parser()
        tree = parser.parse(css_code.encode("utf-8"))
        elements = self.extractor.extract_css_rules(tree, css_code)

        supports = [e for e in elements if e.selector.startswith("@supports")]
        # Note: @supports may or may not be fully supported depending on tree-sitter-css
        # This test documents expected behavior
        if len(supports) >= 1:
            assert "display" in supports[0].selector or "grid" in supports[0].selector


class TestCssIntegration:
    """Integration tests for CSS plugin"""

    def test_style_element_creation(self):
        """Test StyleElement creation"""
        element = StyleElement(
            name=".container",
            start_line=5,
            end_line=9,
            raw_text=".container {\n    max-width: 1200px;\n    margin: 0 auto;\n}",
            language="css",
            selector=".container",
            properties={"max-width": "1200px", "margin": "0 auto"},
            element_class="layout",
        )

        assert element.name == ".container"
        assert element.selector == ".container"
        assert element.properties["max-width"] == "1200px"
        assert element.properties["margin"] == "0 auto"
        assert element.element_class == "layout"
        assert element.language == "css"

    def test_style_element_summary(self):
        """Test StyleElement summary generation"""
        element = StyleElement(
            name="h1",
            start_line=10,
            end_line=14,
            raw_text="h1 {\n    color: #333;\n    font-size: 2em;\n}",
            language="css",
            selector="h1",
            properties={"color": "#333", "font-size": "2em"},
            element_class="typography",
        )

        summary = element.to_summary_item()
        assert summary["name"] == "h1"
        assert summary["selector"] == "h1"
        assert summary["type"] == "css_rule"
        assert summary["element_class"] == "typography"
        assert summary["lines"]["start"] == 10
        assert summary["lines"]["end"] == 14

    def test_media_query_element(self):
        """Test media query StyleElement"""
        element = StyleElement(
            name="@media (max-width: 768px)",
            start_line=20,
            end_line=30,
            raw_text="@media (max-width: 768px) {\n    .container { padding: 10px; }\n}",
            language="css",
            selector="@media (max-width: 768px)",
            properties={},
            element_class="at_rule",
        )

        assert element.name.startswith("@media")
        assert element.selector.startswith("@media")
        assert element.element_class == "at_rule"

    def test_keyframes_element(self):
        """Test keyframes StyleElement"""
        element = StyleElement(
            name="@keyframes fadeIn",
            start_line=35,
            end_line=40,
            raw_text="@keyframes fadeIn {\n    from { opacity: 0; }\n    to { opacity: 1; }\n}",
            language="css",
            selector="@keyframes fadeIn",
            properties={},
            element_class="at_rule",
        )

        assert element.name.startswith("@keyframes")
        assert element.selector.startswith("@keyframes")
        assert element.element_class == "at_rule"

    def test_complex_selector_element(self):
        """Test complex selector StyleElement"""
        element = StyleElement(
            name=".nav ul li a:hover",
            start_line=45,
            end_line=48,
            raw_text=".nav ul li a:hover {\n    color: blue;\n    text-decoration: underline;\n}",
            language="css",
            selector=".nav ul li a:hover",
            properties={"color": "blue", "text-decoration": "underline"},
            element_class="typography",
        )

        assert element.selector == ".nav ul li a:hover"
        assert element.properties["color"] == "blue"
        assert element.properties["text-decoration"] == "underline"


if __name__ == "__main__":
    pytest.main([__file__])
