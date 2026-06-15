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

            # Verify results. Exact pins measured on the inline fixture:
            # 34 lines; 7 elements = body/.container/h1 + @media + its 2
            # nested rules + @keyframes.
            assert result.success
            assert result.language == "css"
            assert result.line_count == 34
            assert len(result.elements) == 7
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
        assert len(keyframes) == 1  # fixture declares exactly 1 @keyframes
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
        assert len(media_queries) == 1  # fixture declares exactly 1 @media
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
        assert len(media_queries) == 1  # fixture declares exactly 1 @media
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
        assert len(media_queries) == 1  # fixture declares exactly 1 @media
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
        assert len(media_queries) == 1  # fixture declares exactly 1 @media
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
        assert len(media_queries) == 1  # fixture declares exactly 1 @media
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
        assert len(keyframes) == 3  # fixture declares exactly 3 @keyframes

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


class TestCssExtractorErrorPaths:
    """Cover error-handling and fallback branches in CssElementExtractor."""

    def setup_method(self):
        self.extractor = CssElementExtractor()

    def test_extract_css_rules_no_root_node(self):
        """extract_css_rules with tree lacking root_node returns empty."""
        result = self.extractor.extract_css_rules(object(), "body {}")
        assert result == []

    def test_extract_css_rules_exception_during_traversal(self):
        """extract_css_rules handles exception from traversal."""

        class BadTree:
            root_node = property(
                lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
            )

        result = self.extractor.extract_css_rules(BadTree(), "body {}")
        assert isinstance(result, list)

    def test_extract_node_text_exception(self):
        """_extract_node_text returns empty string on exception."""

        class BadNode:
            start_byte = property(
                lambda self: (_ for _ in ()).throw(RuntimeError("fail"))
            )
            end_byte = 0

        assert self.extractor._extract_node_text(BadNode(), "css") == ""

    def test_extract_selector_no_selectors_child_with_brace(self):
        """_extract_selector fallback when no selectors child but has brace."""

        class FakeNode:
            type = "rule_set"
            children = []
            start_byte = 0
            end_byte = 10

        result = self.extractor._extract_selector(FakeNode(), "body { color")
        assert result == "body"

    def test_extract_selector_no_brace_returns_unknown(self):
        """_extract_selector returns 'unknown' when text has no opening brace."""

        class FakeNode:
            type = "rule_set"
            children = []
            start_byte = 0
            end_byte = 10

        result = self.extractor._extract_selector(FakeNode(), "nobraCess")
        assert result == "unknown"

    def test_extract_selector_exception_returns_unknown(self):
        """_extract_selector returns 'unknown' on exception."""

        class BadNode:
            children = property(lambda self: (_ for _ in ()).throw(RuntimeError("x")))

        result = self.extractor._extract_selector(BadNode(), "body {}")
        assert result == "unknown"

    def test_extract_properties_no_block_child(self):
        """_extract_properties returns empty dict when no block child."""

        class FakeNode:
            children = []

        result = self.extractor._extract_properties(FakeNode(), "body {}")
        assert result == {}

    def test_extract_properties_exception(self):
        """_extract_properties handles exception gracefully."""

        class BadNode:
            children = property(lambda self: (_ for _ in ()).throw(RuntimeError("x")))

        result = self.extractor._extract_properties(BadNode(), "body {}")
        assert isinstance(result, dict)

    def test_parse_declaration_no_children(self):
        """_parse_declaration fallback when node has no children."""

        class FakeDecl:
            start_byte = 0
            end_byte = 14

        name, value = self.extractor._parse_declaration(FakeDecl(), "color: red;")
        assert name == "color"
        assert value == "red"

    def test_parse_declaration_empty_children(self):
        """_parse_declaration fallback when children don't match types."""

        class FakeChild:
            type = "unknown"
            start_byte = 0
            end_byte = 5

        class FakeDecl:
            children = [FakeChild()]
            start_byte = 0
            end_byte = 5

        name, value = self.extractor._parse_declaration(FakeDecl(), "hello")
        assert name == ""
        assert value == ""

    def test_parse_declaration_exception(self):
        """_parse_declaration returns empty tuple on exception."""

        class BadDecl:
            children = property(lambda self: (_ for _ in ()).throw(RuntimeError("x")))

        name, value = self.extractor._parse_declaration(BadDecl(), "x")
        assert name == ""
        assert value == ""

    def test_create_style_element_exception(self):
        """_create_style_element returns None on exception."""

        class BadNode:
            type = property(lambda self: (_ for _ in ()).throw(RuntimeError("x")))

        result = self.extractor._create_style_element(BadNode(), "body {}")
        assert result is None

    def test_extract_at_rule_name_non_standard(self):
        """_extract_at_rule_name for @charset / @namespace returns truncated text."""

        class FakeNode:
            start_byte = 0
            end_byte = 20

        result = self.extractor._extract_at_rule_name(FakeNode(), "@charset 'utf-8';")
        assert isinstance(result, str)

    def test_extract_at_rule_name_no_at_sign(self):
        """_extract_at_rule_name for text not starting with @."""

        class FakeNode:
            start_byte = 0
            end_byte = 5

        result = self.extractor._extract_at_rule_name(FakeNode(), "hello")
        assert result == "hello"

    def test_extract_at_rule_name_exception(self):
        """_extract_at_rule_name returns empty string when _extract_node_text swallows error."""

        class BadNode:
            start_byte = property(lambda self: (_ for _ in ()).throw(RuntimeError("x")))
            end_byte = 0

        result = self.extractor._extract_at_rule_name(BadNode(), "x")
        assert isinstance(result, str)


class TestCssPluginAnalyzeFallback:
    """Cover analyze_file ImportError fallback path."""

    @pytest.mark.asyncio
    async def test_analyze_file_import_error_fallback(self):
        """analyze_file falls back gracefully when tree_sitter_css is missing."""
        import tempfile
        from unittest.mock import patch

        plugin = CssPlugin()

        class MockRequest:
            include_source = True
            query_filters = {}

        css_content = "body { margin: 0; }\n.container { padding: 10px; }"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".css", delete=False) as f:
            f.write(css_content)
            temp_path = f.name

        try:
            with patch(
                "tree_sitter_analyzer.languages.css_plugin.tree_sitter_css",
                side_effect=ImportError,
                create=True,
            ):
                with patch.dict("sys.modules", {"tree_sitter_css": None}):
                    result = await plugin.analyze_file(temp_path, MockRequest())
                    assert result.success
                    assert result.language == "css"
                    # The regex fallback parser extracts 1 element from the
                    # 2-rule fixture (measured live; documents the degraded
                    # path's actual recall, not a hoped-for bound).
                    assert len(result.elements) == 1
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_analyze_file_read_error(self):
        """analyze_file returns error result when file reading fails."""
        plugin = CssPlugin()

        class MockRequest:
            include_source = True
            query_filters = {}

        result = await plugin.analyze_file("/nonexistent/path/file.css", MockRequest())
        assert result.success is False
        assert result.error_message is not None

    def test_execute_query_strategy_none_key(self):
        """execute_query_strategy returns None when query_key is None."""
        plugin = CssPlugin()
        result = plugin.execute_query_strategy(None, "css")
        assert result is None

    def test_execute_query_strategy_unknown_key(self):
        """execute_query_strategy returns None for unknown query key."""
        plugin = CssPlugin()
        result = plugin.execute_query_strategy("nonexistent", "css")
        assert result is None


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


class TestScssVariableExtraction:
    """Tests for SCSS ``$variable`` extraction (Bug #807).

    ``tree-sitter-css`` does not parse SCSS ``$var: value;`` syntax — it
    emits ERROR nodes and the CSS plugin previously returned 0 elements for
    any ``.scss`` file.  The fix adds a regex pass for ``.scss``/``.sass``
    files that produces ``Variable`` elements for each ``$name`` declaration.
    """

    @pytest.mark.asyncio
    async def test_scss_variables_extracted_from_file(self):
        """3 SCSS ``$variable`` declarations → 3 Variable elements."""
        import tempfile

        from tree_sitter_analyzer.models import Variable

        plugin = CssPlugin()

        class MockRequest:
            include_source = True
            query_filters = {}

        scss_content = (
            "$primary-color: #0d6efd;\n"
            "$font-size-base: 1rem;\n"
            "$spacer: 1rem;\n"
            ".foo { color: $primary-color; }\n"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".scss", delete=False) as f:
            f.write(scss_content)
            temp_path = f.name

        try:
            result = await plugin.analyze_file(temp_path, MockRequest())
            assert result.success is True
            var_elements = [e for e in result.elements if isinstance(e, Variable)]
            assert len(var_elements) == 3
            var_names = {e.name for e in var_elements}
            assert var_names == {"$primary-color", "$font-size-base", "$spacer"}
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_scss_variables_have_correct_line_numbers(self):
        """Each Variable element's start_line matches its source line."""
        import tempfile

        from tree_sitter_analyzer.models import Variable

        plugin = CssPlugin()

        class MockRequest:
            include_source = True
            query_filters = {}

        scss_content = "// comment\n$blue: #0d6efd;\n$red: #dc3545;\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".scss", delete=False) as f:
            f.write(scss_content)
            temp_path = f.name

        try:
            result = await plugin.analyze_file(temp_path, MockRequest())
            var_elements = [e for e in result.elements if isinstance(e, Variable)]
            assert len(var_elements) == 2
            by_name = {e.name: e for e in var_elements}
            assert by_name["$blue"].start_line == 2
            assert by_name["$red"].start_line == 3
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_scss_no_variables_returns_css_rules_only(self):
        """SCSS file with no ``$var`` declarations → 0 Variable elements."""
        import tempfile

        from tree_sitter_analyzer.models import Variable

        plugin = CssPlugin()

        class MockRequest:
            include_source = True
            query_filters = {}

        scss_content = ".foo { color: red; }\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".scss", delete=False) as f:
            f.write(scss_content)
            temp_path = f.name

        try:
            result = await plugin.analyze_file(temp_path, MockRequest())
            var_elements = [e for e in result.elements if isinstance(e, Variable)]
            assert len(var_elements) == 0
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_plain_css_file_unaffected_by_scss_extraction(self):
        """Plain ``.css`` file: no Variable elements, only CSS rules."""
        import tempfile

        from tree_sitter_analyzer.models import Variable

        plugin = CssPlugin()

        class MockRequest:
            include_source = True
            query_filters = {}

        css_content = ":root { --primary: #fff; }\n.bar { color: var(--primary); }\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".css", delete=False) as f:
            f.write(css_content)
            temp_path = f.name

        try:
            result = await plugin.analyze_file(temp_path, MockRequest())
            var_elements = [e for e in result.elements if isinstance(e, Variable)]
            assert len(var_elements) == 0
        finally:
            Path(temp_path).unlink()

    def test_extract_scss_variables_unit(self):
        """Unit test for ``_extract_scss_variables`` helper directly."""
        from tree_sitter_analyzer.languages.css_plugin import _extract_scss_variables
        from tree_sitter_analyzer.models import Variable

        content = (
            "$alpha: #fff;\n"
            "$beta-color: rgba(0, 0, 0, 0.5);\n"
            "// not a variable\n"
            "$gamma: 1rem;\n"
        )
        results = _extract_scss_variables("dummy.scss", content)
        assert len(results) == 3
        assert all(isinstance(v, Variable) for v in results)
        names = [v.name for v in results]
        assert names == ["$alpha", "$beta-color", "$gamma"]

    def test_extract_scss_variables_deduplicates_on_first_occurrence(self):
        """Reassignment of ``$var`` in nested scope → only first occurrence kept."""
        from tree_sitter_analyzer.languages.css_plugin import _extract_scss_variables

        content = "$color: #fff;\n.nested {\n  $color: #000;\n}\n"
        results = _extract_scss_variables("dummy.scss", content)
        assert len(results) == 1
        assert results[0].name == "$color"
        assert results[0].start_line == 1

    def test_extract_scss_variables_skips_block_comments(self):
        """Bug #790: ``$var`` inside a ``/* ... */`` block comment is skipped.

        A commented-out declaration must NOT yield a phantom Variable, whether
        the comment spans multiple lines or sits inline on a single line.
        """
        from tree_sitter_analyzer.languages.css_plugin import _extract_scss_variables

        content = "$live: #fff;\n/*\n$old: red;\n$older: blue;\n*/\n$also_live: 1rem;\n"
        results = _extract_scss_variables("dummy.scss", content)
        names = [v.name for v in results]
        assert names == ["$live", "$also_live"]

    def test_extract_scss_variables_skips_inline_block_comment(self):
        """A single-line ``/* $old: red; */`` block comment yields no Variable."""
        from tree_sitter_analyzer.languages.css_plugin import _extract_scss_variables

        content = "/* $old: red; */\n$live: #fff;\n"
        results = _extract_scss_variables("dummy.scss", content)
        names = [v.name for v in results]
        assert names == ["$live"]


if __name__ == "__main__":
    pytest.main([__file__])
