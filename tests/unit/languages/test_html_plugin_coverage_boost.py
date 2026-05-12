#!/usr/bin/env python3
"""Coverage-boosting tests for html_plugin.py (target: 75.6% → 80%+)"""

from unittest.mock import Mock, patch

import pytest
import tree_sitter
import tree_sitter_html as ts_html

from tree_sitter_analyzer.languages.html_plugin import (
    HtmlElementExtractor,
    HtmlPlugin,
)


class TestHtmlExtractorErrorPaths:
    """Hit exception handling paths in HtmlElementExtractor"""

    @pytest.fixture
    def extractor(self):
        return HtmlElementExtractor()

    def test_traverse_exception_handled(self, extractor):
        """_traverse_for_html_elements catches exceptions (lines 160-161)"""
        mock_node = Mock()
        mock_node.type = "element"
        mock_node.children = []
        # Make _create_markup_element raise
        with patch.object(
            extractor, "_create_markup_element", side_effect=RuntimeError("test")
        ):
            elements: list = []
            extractor._traverse_for_html_elements(mock_node, elements, "", Mock())
            assert elements == []

    def test_create_markup_exception_returns_none(self, extractor):
        """_create_markup_element returns None on exception (lines 225-227)"""
        mock_node = Mock()
        mock_node.type = "element"
        mock_node.children = []

        with patch.object(
            extractor, "_extract_tag_name", side_effect=RuntimeError("test")
        ):
            result = extractor._create_markup_element(mock_node, "", Mock())
            assert result is None

    def test_extract_tag_name_exception_returns_unknown(self, extractor):
        """_extract_tag_name returns 'unknown' on exception (lines 258-259)"""
        mock_node = Mock()
        mock_node.children = []

        with patch.object(
            extractor, "_extract_node_text", side_effect=RuntimeError("test")
        ):
            result = extractor._extract_tag_name(mock_node, "")
            assert result == "unknown"

    def test_extract_node_text_exception_returns_empty(self, extractor):
        """_extract_node_text returns '' on exception (lines 357-359)"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10

        # Make encode/decode fail
        with patch.object(
            extractor,
            "_extract_node_text",
            side_effect=RuntimeError("test"),
        ):
            pass  # Can't easily test internal exception; test via _extract_tag_name instead

        # Simpler: test via direct call with nodes lacking attributes
        bad_node = Mock()
        del bad_node.start_byte
        del bad_node.end_byte
        result = extractor._extract_node_text(bad_node, "test")
        assert result == ""

    def test_extract_attributes_exception_empty_dict(self, extractor):
        """_extract_attributes returns {} on exception (lines 290-291)"""
        mock_node = Mock()
        mock_node.children = [Mock(type="ERRONEOUS_ATTRIBUTE", children=[])]

        result = extractor._extract_attributes(mock_node, "")
        assert isinstance(result, dict)

    def test_parse_attribute_exception_empty_tuple(self, extractor):
        """_parse_attribute returns ('','') on exception (lines 336-337)"""
        mock_node = Mock()
        del mock_node.children  # Missing attr

        result = extractor._parse_attribute(mock_node, "")
        assert result == ("", "")


class TestHtmlPluginAnalyzeFile:
    """Hit ImportError fallback in analyze_file"""

    @pytest.mark.asyncio
    async def test_analyze_file_importerror_fallback(self):
        """analyze_file ImportError fallback creates basic element (lines 456-493)"""
        plugin = HtmlPlugin()

        # Write a temp HTML file
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "<html><head><title>Test</title></head><body><p>Hello</p></body></html>"
            )
            temp_path = f.name

        try:
            with patch(
                "tree_sitter_analyzer.languages.html_plugin.tree_sitter_html",
                create=True,
                side_effect=ImportError("not installed"),
            ):
                result = await plugin.analyze_file(temp_path, Mock())
                assert result.success is True
                assert result.language == "html"
                assert len(result.elements) > 0
                assert result.elements[0].tag_name == "html"
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_general_exception_returns_failure(self):
        """analyze_file general exception returns failed result (lines 491-493)"""
        plugin = HtmlPlugin()

        with patch(
            "tree_sitter_analyzer.encoding_utils.read_file_safe",
            side_effect=OSError("disk error"),
        ):
            result = await plugin.analyze_file("nonexistent.html", Mock())
            assert result.success is False
            assert "disk error" in (result.error_message or "")


def _parse_html(source: str) -> tree_sitter.Tree:
    lang = tree_sitter.Language(ts_html.language())
    parser = tree_sitter.Parser()
    parser.language = lang
    return parser.parse(source.encode("utf-8"))


class TestRealParsingPaths:
    """Use real tree-sitter parsing to hit uncovered lines."""

    @pytest.fixture
    def extractor(self):
        return HtmlElementExtractor()

    def test_extract_html_elements_basic(self, extractor):
        """Lines 123-137: extract_html_elements with real tree-sitter parse"""
        tree = _parse_html("<div><p>hello</p></div>")
        elements = extractor.extract_html_elements(tree, "<div><p>hello</p></div>")
        assert len(elements) >= 2
        tag_names = [e.tag_name for e in elements]
        assert "div" in tag_names
        assert "p" in tag_names

    def test_extract_html_elements_exception_path(self, extractor):
        """Lines 134-135: top-level exception in extract_html_elements"""
        tree = _parse_html("<div>ok</div>")
        with patch.object(
            extractor,
            "_traverse_for_html_elements",
            side_effect=RuntimeError("boom"),
        ):
            elements = extractor.extract_html_elements(tree, "<div>ok</div>")
            assert elements == []

    def test_self_closing_tag_extraction(self, extractor):
        """Lines 168-179: self_closing_tag node type"""
        tree = _parse_html("<br/>")
        elements = extractor.extract_html_elements(tree, "<br/>")
        assert len(elements) >= 1
        assert elements[0].tag_name == "br"

    def test_input_with_boolean_attribute(self, extractor):
        """Lines 295-337: boolean attribute (attribute_name only, no value)"""
        tree = _parse_html("<input disabled checked/>")
        elements = extractor.extract_html_elements(tree, "<input disabled checked/>")
        assert len(elements) >= 1
        assert "disabled" in elements[0].attributes
        assert "checked" in elements[0].attributes

    def test_input_with_unquoted_attribute_value(self, extractor):
        """Line 319: attribute_value child (not quoted_attribute_value)"""
        tree = _parse_html("<input type=text>")
        elements = extractor.extract_html_elements(tree, "<input type=text>")
        assert len(elements) >= 1
        assert elements[0].attributes.get("type") == "text"

    def test_div_with_quoted_attributes(self, extractor):
        """Lines 261-293: quoted_attribute_value parsing"""
        tree = _parse_html('<div class="container" id="main">hi</div>')
        elements = extractor.extract_html_elements(
            tree, '<div class="container" id="main">hi</div>'
        )
        assert len(elements) >= 1
        assert elements[0].attributes.get("class") == "container"
        assert elements[0].attributes.get("id") == "main"

    def test_nested_elements_with_parent(self, extractor):
        """Lines 219-221: parent.children.append"""
        code = "<div><span>inner</span></div>"
        tree = _parse_html(code)
        elements = extractor.extract_html_elements(tree, code)
        div_elems = [e for e in elements if e.tag_name == "div"]
        assert len(div_elems) >= 1
        div = div_elems[0]
        assert len(div.children) >= 1
        assert div.children[0].tag_name == "span"

    def test_classify_all_categories(self, extractor):
        """Lines 339-347: _classify_element for all categories"""
        assert extractor._classify_element("ul") == "list"
        assert extractor._classify_element("td") == "table"
        assert extractor._classify_element("script") == "metadata"
        assert extractor._classify_element("section") == "structure"
        assert extractor._classify_element("H1") == "heading"  # case-insensitive
        assert extractor._classify_element("xyz") == "unknown"

    def test_extract_tag_name_fallback_no_tag_name_child(self, extractor):
        """Lines 251-259: fallback path in _extract_tag_name"""
        # Create a mock node with children but no tag_name/start_tag children
        mock_node = Mock()
        child = Mock()
        child.type = "some_other_type"
        child.children = []
        mock_node.children = [child]

        with patch.object(
            extractor, "_extract_node_text", return_value="<custom> stuff"
        ):
            result = extractor._extract_tag_name(mock_node, "<custom> stuff")
            assert result == "custom"

    def test_extract_tag_name_fallback_no_angle_bracket(self, extractor):
        """Line 257: fallback returns 'unknown' when no angle bracket"""
        mock_node = Mock()
        child = Mock()
        child.type = "some_other_type"
        child.children = []
        mock_node.children = [child]

        with patch.object(extractor, "_extract_node_text", return_value="no angle"):
            result = extractor._extract_tag_name(mock_node, "no angle")
            assert result == "unknown"

    def test_extract_node_text_node_without_byte_attrs(self, extractor):
        """Lines 356-359: node missing start_byte/end_byte returns empty"""
        mock_node = Mock(spec=[])
        result = extractor._extract_node_text(mock_node, "some code")
        assert result == ""

    def test_create_markup_element_no_tag_name(self, extractor):
        """Line 192: _create_markup_element returns None when tag_name is falsy"""
        mock_node = Mock()
        mock_node.children = []
        mock_node.type = "element"

        with patch.object(extractor, "_extract_tag_name", return_value=""):
            result = extractor._create_markup_element(mock_node, "", None)
            assert result is None

    def test_parse_attribute_no_children_fallback(self, extractor):
        """Lines 324-333: fallback in _parse_attribute when no recognized children"""
        mock_node = Mock()
        child = Mock()
        child.type = "unknown_part"
        child.start_byte = 0
        child.end_byte = 14
        mock_node.children = [child]
        mock_node.start_byte = 0
        mock_node.end_byte = 14

        with patch.object(extractor, "_extract_node_text", return_value='href="url"'):
            name, value = extractor._parse_attribute(mock_node, 'href="url"')
            assert name == "href"
            assert value == "url"

    def test_parse_attribute_boolean_fallback(self, extractor):
        """Lines 332-333: boolean attribute fallback (no =)"""
        mock_node = Mock()
        child = Mock()
        child.type = "unknown_part"
        mock_node.children = [child]
        mock_node.start_byte = 0
        mock_node.end_byte = 8

        with patch.object(extractor, "_extract_node_text", return_value="disabled"):
            name, value = extractor._parse_attribute(mock_node, "disabled")
            assert name == "disabled"
            assert value == ""

    def test_parse_attribute_exception_returns_empty(self, extractor):
        """Lines 336-337: exception in _parse_attribute returns empty tuple"""
        mock_node = Mock()
        del mock_node.children
        result = extractor._parse_attribute(mock_node, "")
        assert result == ("", "")

    def test_extract_attributes_with_real_tree_exception(self, extractor):
        """Lines 290-291: exception in _extract_attributes"""
        mock_node = Mock()
        mock_node.children = []
        with patch.object(
            extractor, "_extract_node_text", side_effect=RuntimeError("err")
        ):
            result = extractor._extract_attributes(mock_node, "")
            assert result == {}

    def test_traverse_exception_during_create(self, extractor):
        """Lines 160-161: exception in _traverse_for_html_elements during create"""
        mock_node = Mock()
        mock_node.type = "element"
        mock_node.children = []
        elements = []

        with patch.object(
            extractor, "_create_markup_element", side_effect=RuntimeError("fail")
        ):
            extractor._traverse_for_html_elements(mock_node, elements, "", None)
            assert elements == []
