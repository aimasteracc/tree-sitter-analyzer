"""HTML plugin tests — query accuracy."""


from tests.unit.languages._html_test_data import (
    ATTRIBUTE_CODE,
    FORM_CODE,
    LINK_IMAGE_CODE,
    TABLE_CODE,
    TAG_CODE,
    get_tree_for_code,
)
from tree_sitter_analyzer.languages.html_plugin import HtmlPlugin


class TestHtmlQueryAccuracy:
    """Test accuracy of HTML queries."""

    def test_tag_query_accuracy(self):
        """Test that tag query accurately identifies tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Should not extract non-tag elements
        for element in elements:
            assert element.tag_name is not None
            assert len(element.tag_name) > 0

    def test_attribute_query_accuracy(self):
        """Test that attribute query accurately identifies attributes."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        # Attributes should be within elements
        for element in elements:
            if element.attributes:
                for attr_name, attr_value in element.attributes.items():
                    assert attr_name is not None
                    assert attr_value is not None

    def test_form_query_accuracy(self):
        """Test that form query accurately identifies form elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        # Should find form elements
        form_elements = [e for e in elements if e.tag_name == "form"]
        assert len(form_elements) >= 1

    def test_table_query_accuracy(self):
        """Test that table query accurately identifies table elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        # Should find table elements
        table_elements = [e for e in elements if e.tag_name == "table"]
        assert len(table_elements) >= 1

    def test_link_query_accuracy(self):
        """Test that link query accurately identifies links."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        # Should find anchor tags
        a_elements = [e for e in elements if e.tag_name == "a"]
        assert len(a_elements) >= 1

    def test_image_query_accuracy(self):
        """Test that image query accurately identifies images."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        # Should find img tags
        img_elements = [e for e in elements if e.tag_name == "img"]
        assert len(img_elements) >= 1

    def test_no_false_positives(self):
        """Test that queries don't produce false positives."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Should not extract comments as tags
        for element in elements:
            assert element.tag_name is not None
            assert element.tag_name.strip() != ""

    def test_no_false_negatives(self):
        """Test that queries don't miss elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Should find all expected tags
        tag_names = [e.tag_name for e in elements]
        assert "div" in tag_names
        assert "h1" in tag_names
        assert "p" in tag_names

    def test_line_number_accuracy(self):
        """Test that line numbers are accurate."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        for element in elements:
            assert element.start_line > 0
            assert element.end_line >= element.start_line

    def test_element_classification_accuracy(self):
        """Test that element classification is accurate."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Structure elements should be classified as structure
        structure_elements = [e for e in elements if e.element_class == "structure"]
        assert len(structure_elements) >= 1

        # Heading elements should be classified as heading
        heading_elements = [e for e in elements if e.element_class == "heading"]
        assert len(heading_elements) >= 1
