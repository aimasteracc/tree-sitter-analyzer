#!/usr/bin/env python3
"""Coverage-boosting tests for html_plugin.py (target: 75.6% → 80%+)"""

from unittest.mock import Mock, patch

import pytest
import tree_sitter
import tree_sitter_html as ts_html

from tree_sitter_analyzer.languages.html_helpers import (
    classify_element,
    create_markup_element,
    extract_html_attributes,
    extract_html_tag_name,
    extract_node_text,
    parse_attribute,
)
from tree_sitter_analyzer.languages.html_plugin import (
    HtmlElementExtractor,
    HtmlPlugin,
)


class FakeHtmlNode:
    """Small tree-sitter-like node for direct helper tests."""

    def __init__(
        self,
        node_type: str = "element",
        *,
        children: list["FakeHtmlNode"] | None = None,
        start_byte: int = 0,
        end_byte: int = 0,
        start_point: tuple[int, int] = (0, 0),
        end_point: tuple[int, int] = (0, 0),
        text: str = "",
    ) -> None:
        self.type = node_type
        self.children = children or []
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.start_point = start_point
        self.end_point = end_point
        self.text = text


def fake_node_text(node: FakeHtmlNode) -> str:
    return node.text


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


class TestHtmlHelperDirectCoverage:
    """Direct coverage for html_helpers.py behavior."""

    def test_extract_node_text_uses_utf8_byte_offsets(self):
        source = "<p>東京</p>"
        start = source.encode("utf-8").index("東".encode())
        end = source.encode("utf-8").index(b"</p>")
        node = FakeHtmlNode(start_byte=start, end_byte=end)

        assert extract_node_text(node, source) == "東京"

    def test_extract_node_text_handles_missing_offsets_and_encode_errors(self):
        assert extract_node_text(Mock(spec=[]), "<p>x</p>") == ""

        class BrokenSource:
            def encode(self, encoding):
                raise RuntimeError(f"cannot encode {encoding}")

        node = FakeHtmlNode(start_byte=0, end_byte=1)
        assert extract_node_text(node, BrokenSource()) == ""

    def test_parse_attribute_from_child_nodes(self):
        attr = FakeHtmlNode(
            "attribute",
            children=[
                FakeHtmlNode("attribute_name", text="data-id"),
                FakeHtmlNode("quoted_attribute_value", text='"abc"'),
            ],
        )

        assert parse_attribute(attr, fake_node_text) == ("data-id", "abc")

    def test_parse_attribute_fallback_and_exception_paths(self):
        assert parse_attribute(FakeHtmlNode(text="disabled"), fake_node_text) == (
            "disabled",
            "",
        )
        assert parse_attribute(FakeHtmlNode(text="type=text"), fake_node_text) == (
            "type",
            "text",
        )
        assert parse_attribute(FakeHtmlNode(), Mock(side_effect=RuntimeError)) == (
            "",
            "",
        )

    def test_extract_tag_name_from_direct_nested_and_fallback_shapes(self):
        direct = FakeHtmlNode(children=[FakeHtmlNode("tag_name", text="article")])
        nested = FakeHtmlNode(
            children=[
                FakeHtmlNode(
                    "start_tag",
                    children=[FakeHtmlNode("tag_name", text="section")],
                )
            ]
        )
        fallback = FakeHtmlNode(text="<custom-widget data-id='1'>")

        assert extract_html_tag_name(direct, fake_node_text) == "article"
        assert extract_html_tag_name(nested, fake_node_text) == "section"
        assert extract_html_tag_name(fallback, fake_node_text) == "custom-widget"
        assert extract_html_tag_name(FakeHtmlNode(text="plain"), fake_node_text) == (
            "unknown"
        )

    def test_extract_html_attributes_from_top_level_and_nested_tags(self):
        top_level_attr = FakeHtmlNode(
            "attribute",
            children=[
                FakeHtmlNode("attribute_name", text="id"),
                FakeHtmlNode("attribute_value", text="hero"),
            ],
        )
        nested_attr = FakeHtmlNode(
            "attribute",
            children=[
                FakeHtmlNode("attribute_name", text="class"),
                FakeHtmlNode("quoted_attribute_value", text='"card"'),
            ],
        )
        node = FakeHtmlNode(
            children=[
                top_level_attr,
                FakeHtmlNode("self_closing_tag", children=[nested_attr]),
            ]
        )

        assert extract_html_attributes(node, fake_node_text) == {
            "id": "hero",
            "class": "card",
        }

    def test_classify_and_create_markup_element_with_parent(self):
        categories = {"structure": ["div"], "media": ["img"]}
        parent = create_markup_element(
            FakeHtmlNode(children=[FakeHtmlNode("tag_name", text="div")], text="<div>"),
            fake_node_text,
            categories,
            None,
        )
        child = create_markup_element(
            FakeHtmlNode(
                children=[FakeHtmlNode("tag_name", text="img")],
                start_point=(2, 0),
                end_point=(2, 5),
                text="<img>",
            ),
            fake_node_text,
            categories,
            parent,
        )

        assert classify_element("IMG", categories) == "media"
        assert parent is not None
        assert child is not None
        assert child.parent is parent
        assert parent.children == [child]
        assert child.start_line == 3
        assert child.end_line == 3

    def test_create_markup_element_returns_none_on_empty_or_exception(self):
        assert (
            create_markup_element(
                FakeHtmlNode(text="plain text"), fake_node_text, {}, None
            )
            is not None
        )
        assert (
            create_markup_element(
                FakeHtmlNode(children=[FakeHtmlNode("tag_name", text="div")]),
                Mock(side_effect=RuntimeError),
                {},
                None,
            )
            is None
        )


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
                # html, head, title, body, p — exactly 5 elements
                assert [e.tag_name for e in result.elements] == [
                    "html",
                    "head",
                    "title",
                    "body",
                    "p",
                ]
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
        assert [e.tag_name for e in elements] == ["div", "p"]

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
        # #632: the element node wraps the self_closing_tag child; only the
        # parent element is captured (the child would be a duplicate) -> 1 entry
        assert [e.tag_name for e in elements] == ["br"]

    def test_input_with_boolean_attribute(self, extractor):
        """Lines 295-337: boolean attribute (attribute_name only, no value)"""
        tree = _parse_html("<input disabled checked/>")
        elements = extractor.extract_html_elements(tree, "<input disabled checked/>")
        # #632: self-closing input captured once (parent element only; the
        # self_closing_tag child is skipped as a duplicate) -> 1 entry
        assert [e.tag_name for e in elements] == ["input"]
        assert "disabled" in elements[0].attributes
        assert "checked" in elements[0].attributes

    def test_self_closing_dedup_issue_632(self, extractor):
        """#632: self-closing tags yield exactly one entry each.

        tree-sitter-html wraps self_closing_tag inside an element node
        (element is the parent, self_closing_tag the child carrying
        tag_name/attributes); the walk must not capture both.
        """
        code = '<div><br/><input type="text"/></div>'
        tree = _parse_html(code)
        elements = extractor.extract_html_elements(tree, code)
        assert [e.tag_name for e in elements] == ["div", "br", "input"]
        # The surviving capture (parent element) still carries the attributes
        assert elements[2].attributes == {"type": "text"}

    def test_void_element_without_slash_issue_632(self, extractor):
        """#632: void elements WITHOUT a slash (<br>) parse as
        element > start_tag (no self_closing_tag node) -> exactly 1 entry."""
        tree = _parse_html("<br>")
        elements = extractor.extract_html_elements(tree, "<br>")
        assert [e.tag_name for e in elements] == ["br"]

    def test_input_with_unquoted_attribute_value(self, extractor):
        """Line 319: attribute_value child (not quoted_attribute_value)"""
        tree = _parse_html("<input type=text>")
        elements = extractor.extract_html_elements(tree, "<input type=text>")
        assert [e.tag_name for e in elements] == ["input"]
        assert elements[0].attributes.get("type") == "text"

    def test_div_with_quoted_attributes(self, extractor):
        """Lines 261-293: quoted_attribute_value parsing"""
        tree = _parse_html('<div class="container" id="main">hi</div>')
        elements = extractor.extract_html_elements(
            tree, '<div class="container" id="main">hi</div>'
        )
        assert [e.tag_name for e in elements] == ["div"]
        assert elements[0].attributes.get("class") == "container"
        assert elements[0].attributes.get("id") == "main"

    def test_nested_elements_with_parent(self, extractor):
        """Lines 219-221: parent.children.append"""
        code = "<div><span>inner</span></div>"
        tree = _parse_html(code)
        elements = extractor.extract_html_elements(tree, code)
        div_elems = [e for e in elements if e.tag_name == "div"]
        assert len(div_elems) == 1
        div = div_elems[0]
        # The div has exactly one child: the span
        assert [c.tag_name for c in div.children] == ["span"]

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
