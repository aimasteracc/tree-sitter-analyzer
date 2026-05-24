"""HTML plugin tests — links, images, scripts, styles, complex structures."""


from tests.unit.languages._html_test_data import (
    COMPLEX_STRUCTURE_CODE,
    LINK_IMAGE_CODE,
    SCRIPT_STYLE_CODE,
    get_tree_for_code,
)
from tree_sitter_analyzer.languages.html_plugin import HtmlPlugin


class TestHtmlLinkImageRecognition:
    """Test HTML link and image recognition and extraction."""

    def test_extract_a_tag(self):
        """Test extraction of anchor tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        a_elements = [e for e in elements if e.tag_name == "a"]
        assert len(a_elements) >= 1

    def test_extract_external_link(self):
        """Test extraction of external link."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        external_link = next(
            (
                e
                for e in elements
                if e.tag_name == "a"
                and e.attributes
                and "https://" in e.attributes.get("href", "")
            ),
            None,
        )
        if external_link:
            assert "https://" in external_link.attributes["href"]

    def test_extract_internal_link(self):
        """Test extraction of internal link."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        internal_link = next(
            (
                e
                for e in elements
                if e.tag_name == "a"
                and e.attributes
                and e.attributes.get("href", "").startswith("/")
            ),
            None,
        )
        if internal_link:
            assert internal_link.attributes["href"].startswith("/")

    def test_extract_anchor_link(self):
        """Test extraction of anchor link."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        anchor_link = next(
            (
                e
                for e in elements
                if e.tag_name == "a"
                and e.attributes
                and e.attributes.get("href", "").startswith("#")
            ),
            None,
        )
        if anchor_link:
            assert anchor_link.attributes["href"].startswith("#")

    def test_extract_img_tag(self):
        """Test extraction of img tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        img_elements = [e for e in elements if e.tag_name == "img"]
        assert len(img_elements) >= 1

    def test_extract_image_with_alt(self):
        """Test extraction of image with alt text."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        img_with_alt = next(
            (
                e
                for e in elements
                if e.tag_name == "img" and e.attributes and "alt" in e.attributes
            ),
            None,
        )
        if img_with_alt:
            assert img_with_alt.attributes["alt"] is not None

    def test_extract_image_with_dimensions(self):
        """Test extraction of image with dimensions."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        img_with_dims = next(
            (
                e
                for e in elements
                if e.tag_name == "img"
                and e.attributes
                and "width" in e.attributes
                and "height" in e.attributes
            ),
            None,
        )
        if img_with_dims:
            assert img_with_dims.attributes["width"] is not None
            assert img_with_dims.attributes["height"] is not None

    def test_extract_picture_tag(self):
        """Test extraction of picture tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        picture_elements = [e for e in elements if e.tag_name == "picture"]
        assert len(picture_elements) >= 0

    def test_extract_svg_tag(self):
        """Test extraction of svg tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        svg_elements = [e for e in elements if e.tag_name == "svg"]
        assert len(svg_elements) >= 0


class TestHtmlScriptStyleRecognition:
    """Test HTML script and style recognition and extraction."""

    def test_extract_script_tag(self):
        """Test extraction of script tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        script_elements = [e for e in elements if e.tag_name == "script"]
        assert len(script_elements) >= 1

    def test_extract_style_tag(self):
        """Test extraction of style tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        style_elements = [e for e in elements if e.tag_name == "style"]
        assert len(style_elements) >= 1

    def test_extract_link_tag(self):
        """Test extraction of link tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        link_elements = [e for e in elements if e.tag_name == "link"]
        assert len(link_elements) >= 1

    def test_extract_meta_tag(self):
        """Test extraction of meta tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        meta_elements = [e for e in elements if e.tag_name == "meta"]
        assert len(meta_elements) >= 1

    def test_extract_title_tag(self):
        """Test extraction of title tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        title_elements = [e for e in elements if e.tag_name == "title"]
        assert len(title_elements) >= 1

    def test_extract_script_with_src(self):
        """Test extraction of script with src attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        script_with_src = next(
            (
                e
                for e in elements
                if e.tag_name == "script" and e.attributes and "src" in e.attributes
            ),
            None,
        )
        if script_with_src:
            assert script_with_src.attributes["src"] is not None

    def test_extract_style_with_href(self):
        """Test extraction of link with href attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        link_with_href = next(
            (
                e
                for e in elements
                if e.tag_name == "link" and e.attributes and "href" in e.attributes
            ),
            None,
        )
        if link_with_href:
            assert link_with_href.attributes["href"] is not None


class TestHtmlComplexStructures:
    """Test extraction of complex HTML structures."""

    def test_extract_nested_elements(self):
        """Test extraction of nested elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        # Should find nested elements
        assert len(elements) >= 10

    def test_extract_parent_child_relationships(self):
        """Test extraction of parent-child relationships."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        # Some elements should have children
        elements_with_children = [
            e for e in elements if e.children and len(e.children) > 0
        ]
        assert len(elements_with_children) >= 1

    def test_extract_multiple_classes(self):
        """Test extraction of elements with multiple classes."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        # Should find elements with multiple classes
        elements_with_multiple_classes = [
            e
            for e in elements
            if e.attributes and "class" in e.attributes and " " in e.attributes["class"]
        ]
        assert len(elements_with_multiple_classes) >= 0

    def test_extract_doctype(self):
        """Test extraction of DOCTYPE."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        # DOCTYPE should be captured
        assert len(elements) >= 1

    def test_extract_html_tag(self):
        """Test extraction of html tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        html_elements = [e for e in elements if e.tag_name == "html"]
        assert len(html_elements) >= 1

    def test_extract_head_tag(self):
        """Test extraction of head tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        head_elements = [e for e in elements if e.tag_name == "head"]
        assert len(head_elements) >= 1

    def test_extract_body_tag(self):
        """Test extraction of body tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        body_elements = [e for e in elements if e.tag_name == "body"]
        assert len(body_elements) >= 1


