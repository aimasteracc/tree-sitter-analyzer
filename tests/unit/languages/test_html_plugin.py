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
            assert result.line_count
            assert result.elements
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


# ---------------------------------------------------------------------------
# Tests migrated from test_html_plugin_coverage_boost.py
# ---------------------------------------------------------------------------


def _parse_html_real(source: str):
    import tree_sitter
    import tree_sitter_html as ts_html

    lang = tree_sitter.Language(ts_html.language())
    parser = tree_sitter.Parser()
    parser.language = lang
    return parser.parse(source.encode("utf-8"))


class TestHtmlExtractorBehavioral:
    """Behavioral tests for HtmlElementExtractor using real tree-sitter parsing."""

    @pytest.fixture
    def extractor(self):
        return HtmlElementExtractor()

    def test_extract_html_elements_tag_order(self, extractor):
        tree = _parse_html_real("<div><p>hello</p></div>")
        elements = extractor.extract_html_elements(tree, "<div><p>hello</p></div>")
        assert [e.tag_name for e in elements] == ["div", "p"]

    def test_self_closing_tag_yields_one_entry(self, extractor):
        """#632: element wraps self_closing_tag child; only parent captured."""
        tree = _parse_html_real("<br/>")
        elements = extractor.extract_html_elements(tree, "<br/>")
        assert [e.tag_name for e in elements] == ["br"]

    def test_input_with_boolean_attributes(self, extractor):
        """Boolean attributes (no value) are captured."""
        tree = _parse_html_real("<input disabled checked/>")
        elements = extractor.extract_html_elements(tree, "<input disabled checked/>")
        assert [e.tag_name for e in elements] == ["input"]
        assert "disabled" in elements[0].attributes
        assert "checked" in elements[0].attributes

    def test_self_closing_dedup_issue_632(self, extractor):
        """#632: self-closing tags yield exactly one entry each."""
        code = '<div><br/><input type="text"/></div>'
        tree = _parse_html_real(code)
        elements = extractor.extract_html_elements(tree, code)
        assert [e.tag_name for e in elements] == ["div", "br", "input"]
        assert elements[2].attributes == {"type": "text"}

    def test_void_element_without_slash_issue_632(self, extractor):
        """#632: void elements without slash parse as element > start_tag -> 1 entry."""
        tree = _parse_html_real("<br>")
        elements = extractor.extract_html_elements(tree, "<br>")
        assert [e.tag_name for e in elements] == ["br"]

    def test_input_with_unquoted_attribute_value(self, extractor):
        tree = _parse_html_real("<input type=text>")
        elements = extractor.extract_html_elements(tree, "<input type=text>")
        assert [e.tag_name for e in elements] == ["input"]
        assert elements[0].attributes.get("type") == "text"

    def test_div_with_quoted_attributes(self, extractor):
        code = '<div class="container" id="main">hi</div>'
        tree = _parse_html_real(code)
        elements = extractor.extract_html_elements(tree, code)
        assert [e.tag_name for e in elements] == ["div"]
        assert elements[0].attributes.get("class") == "container"
        assert elements[0].attributes.get("id") == "main"

    def test_nested_elements_parent_child_relationship(self, extractor):
        code = "<div><span>inner</span></div>"
        tree = _parse_html_real(code)
        elements = extractor.extract_html_elements(tree, code)
        div_elems = [e for e in elements if e.tag_name == "div"]
        assert len(div_elems) == 1
        assert [c.tag_name for c in div_elems[0].children] == ["span"]

    def test_classify_all_categories(self, extractor):
        assert extractor._classify_element("ul") == "list"
        assert extractor._classify_element("td") == "table"
        assert extractor._classify_element("script") == "metadata"
        assert extractor._classify_element("section") == "structure"
        assert extractor._classify_element("H1") == "heading"
        assert extractor._classify_element("xyz") == "unknown"

    def test_extract_tag_name_no_angle_bracket_returns_unknown(self, extractor):
        from unittest.mock import Mock, patch

        mock_node = Mock()
        child = Mock()
        child.type = "some_other_type"
        child.children = []
        mock_node.children = [child]
        with patch.object(extractor, "_extract_node_text", return_value="no angle"):
            result = extractor._extract_tag_name(mock_node, "no angle")
            assert result == "unknown"

    def test_extract_node_text_node_without_byte_attrs_returns_empty(self, extractor):
        from unittest.mock import Mock

        mock_node = Mock(spec=[])
        result = extractor._extract_node_text(mock_node, "some code")
        assert result == ""

    def test_create_markup_element_empty_tag_name_returns_none(self, extractor):
        from unittest.mock import Mock, patch

        mock_node = Mock()
        mock_node.children = []
        mock_node.type = "element"
        with patch.object(extractor, "_extract_tag_name", return_value=""):
            result = extractor._create_markup_element(mock_node, "", None)
            assert result is None

    def test_parse_attribute_exception_returns_empty_tuple(self, extractor):
        from unittest.mock import Mock

        mock_node = Mock()
        del mock_node.children
        result = extractor._parse_attribute(mock_node, "")
        assert result == ("", "")

    def test_extract_attributes_with_exception_returns_empty_dict(self, extractor):
        from unittest.mock import Mock, patch

        mock_node = Mock()
        mock_node.children = []
        with patch.object(
            extractor, "_extract_node_text", side_effect=RuntimeError("err")
        ):
            result = extractor._extract_attributes(mock_node, "")
            assert result == {}

    def test_traverse_exception_during_create_returns_no_elements(self, extractor):
        from unittest.mock import Mock, patch

        mock_node = Mock()
        mock_node.type = "element"
        mock_node.children = []
        elements = []
        with patch.object(
            extractor, "_create_markup_element", side_effect=RuntimeError("fail")
        ):
            extractor._traverse_for_html_elements(mock_node, elements, "", None)
            assert elements == []


class TestHtmlHelpersBehavioral:
    """Behavioral tests for html_helpers functions."""

    def test_parse_attribute_from_child_nodes(self):
        from tree_sitter_analyzer.languages.html_helpers import parse_attribute

        class FakeNode:
            def __init__(self, node_type="", *, children=None, text=""):
                self.type = node_type
                self.children = children or []
                self.text = text

        def fake_text(node):
            return node.text

        attr = FakeNode(
            "attribute",
            children=[
                FakeNode("attribute_name", text="data-id"),
                FakeNode("quoted_attribute_value", text='"abc"'),
            ],
        )
        assert parse_attribute(attr, fake_text) == ("data-id", "abc")

    def test_extract_html_tag_name_from_direct_and_nested(self):
        from tree_sitter_analyzer.languages.html_helpers import extract_html_tag_name

        class FakeNode:
            def __init__(self, node_type="", *, children=None, text=""):
                self.type = node_type
                self.children = children or []
                self.text = text

        def fake_text(node):
            return node.text

        direct = FakeNode(children=[FakeNode("tag_name", text="article")])
        nested = FakeNode(
            children=[
                FakeNode("start_tag", children=[FakeNode("tag_name", text="section")])
            ]
        )
        assert extract_html_tag_name(direct, fake_text) == "article"
        assert extract_html_tag_name(nested, fake_text) == "section"

    def test_classify_element_media_category(self):
        from tree_sitter_analyzer.languages.html_helpers import classify_element

        categories = {"structure": ["div"], "media": ["img"]}
        assert classify_element("IMG", categories) == "media"

    def test_create_markup_element_parent_child_linking(self):
        from tree_sitter_analyzer.languages.html_helpers import create_markup_element

        class FakeNode:
            def __init__(
                self,
                node_type="element",
                *,
                children=None,
                start_point=(0, 0),
                end_point=(0, 0),
                text="",
            ):
                self.type = node_type
                self.children = children or []
                self.start_point = start_point
                self.end_point = end_point
                self.text = text

        def fake_text(node):
            return node.text

        categories = {"structure": ["div"], "media": ["img"]}
        parent = create_markup_element(
            FakeNode(children=[FakeNode("tag_name", text="div")], text="<div>"),
            fake_text,
            categories,
            None,
        )
        child = create_markup_element(
            FakeNode(
                children=[FakeNode("tag_name", text="img")],
                start_point=(2, 0),
                end_point=(2, 5),
                text="<img>",
            ),
            fake_text,
            categories,
            parent,
        )
        assert parent is not None
        assert child is not None
        assert child.parent is parent
        assert parent.children == [child]
        assert child.start_line == 3
        assert child.end_line == 3


if __name__ == "__main__":
    pytest.main([__file__])
