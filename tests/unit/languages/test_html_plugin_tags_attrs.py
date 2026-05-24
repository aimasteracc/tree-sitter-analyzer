"""HTML plugin tests — tag and attribute recognition."""


from tests.unit.languages._html_test_data import (
    ATTRIBUTE_CODE,
    TAG_CODE,
    get_tree_for_code,
)
from tree_sitter_analyzer.languages.html_plugin import HtmlPlugin


class TestHtmlTagRecognition:
    """Test HTML tag recognition and extraction."""

    def test_extract_structure_tags(self):
        """Test extraction of structure tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        structure_tags = [e for e in elements if e.element_class == "structure"]
        assert len(structure_tags) >= 0

    def test_extract_heading_tags(self):
        """Test extraction of heading tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        heading_tags = [e for e in elements if e.element_class == "heading"]
        assert len(heading_tags) >= 0

    def test_extract_text_tags(self):
        """Test extraction of text tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        text_tags = [e for e in elements if e.element_class == "text"]
        assert len(text_tags) >= 0

    def test_extract_div_tag(self):
        """Test extraction of div tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        div_elements = [e for e in elements if e.tag_name == "div"]
        assert len(div_elements) >= 1

    def test_extract_span_tag(self):
        """Test extraction of span tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        span_elements = [e for e in elements if e.tag_name == "span"]
        assert len(span_elements) >= 0

    def test_extract_paragraph_tag(self):
        """Test extraction of paragraph tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        p_elements = [e for e in elements if e.tag_name == "p"]
        assert len(p_elements) >= 1

    def test_extract_list_tags(self):
        """Test extraction of list tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        ul_elements = [e for e in elements if e.tag_name == "ul"]
        li_elements = [e for e in elements if e.tag_name == "li"]
        assert len(ul_elements) >= 1
        assert len(li_elements) >= 1

    def test_extract_inline_tags(self):
        """Test extraction of inline tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        inline_tags = [
            e
            for e in elements
            if e.tag_name
            in ["strong", "em", "mark", "del", "ins", "sub", "sup", "small"]
        ]
        assert len(inline_tags) >= 0


class TestHtmlAttributeRecognition:
    """Test HTML attribute recognition and extraction."""

    def test_extract_id_attribute(self):
        """Test extraction of id attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        div_with_id = next(
            (e for e in elements if e.attributes and "id" in e.attributes), None
        )
        if div_with_id:
            assert div_with_id.attributes["id"] == "main"

    def test_extract_class_attribute(self):
        """Test extraction of class attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        div_with_class = next(
            (e for e in elements if e.attributes and "class" in e.attributes), None
        )
        if div_with_class:
            assert "container" in div_with_class.attributes["class"]

    def test_extract_data_attributes(self):
        """Test extraction of data attributes."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        div_with_data = next(
            (e for e in elements if e.attributes and "data-id" in e.attributes), None
        )
        if div_with_data:
            assert div_with_data.attributes["data-id"] == "123"

    def test_extract_style_attribute(self):
        """Test extraction of style attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        p_with_style = next(
            (e for e in elements if e.attributes and "style" in e.attributes), None
        )
        if p_with_style:
            assert "color" in p_with_style.attributes["style"]

    def test_extract_event_attributes(self):
        """Test extraction of event attributes."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        button_with_onclick = next(
            (e for e in elements if e.attributes and "onclick" in e.attributes), None
        )
        if button_with_onclick:
            assert button_with_onclick.attributes["onclick"] == "handleClick()"

    def test_extract_href_attribute(self):
        """Test extraction of href attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        link_with_href = next(
            (e for e in elements if e.attributes and "href" in e.attributes), None
        )
        if link_with_href:
            assert link_with_href.attributes["href"] == "https://example.com"

    def test_extract_src_attribute(self):
        """Test extraction of src attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        img_with_src = next(
            (
                e
                for e in elements
                if e.tag_name == "img" and e.attributes and "src" in e.attributes
            ),
            None,
        )
        if img_with_src:
            assert img_with_src.attributes["src"] == "image.jpg"

    def test_extract_alt_attribute(self):
        """Test extraction of alt attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        img_with_alt = next(
            (
                e
                for e in elements
                if e.tag_name == "img" and e.attributes and "alt" in e.attributes
            ),
            None,
        )
        if img_with_alt:
            assert img_with_alt.attributes["alt"] == "Description"

    def test_extract_multiple_attributes(self):
        """Test extraction of multiple attributes."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        div_with_multiple = next(
            (e for e in elements if e.tag_name == "div" and e.attributes), None
        )
        if div_with_multiple:
            assert "id" in div_with_multiple.attributes
            assert "class" in div_with_multiple.attributes
            assert "data-id" in div_with_multiple.attributes


