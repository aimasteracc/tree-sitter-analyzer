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

        # Should not extract non-tag elements — exact full tag list of
        # TAG_CODE in document order (update when the fixture changes)
        assert [e.tag_name for e in elements] == [
            "div",
            "header",
            "h1",
            "nav",
            "ul",
            "li",
            "a",
            "li",
            "a",
            "li",
            "a",
            "main",
            "section",
            "h2",
            "p",
            "article",
            "h3",
            "p",
            "aside",
            "h4",
            "p",
            "footer",
            "p",
            "p",
            "strong",
            "em",
            "p",
            "mark",
            "del",
            "p",
            "ins",
            "sub",
            "p",
            "sup",
            "small",
        ]

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

        # FORM_CODE contains exactly one <form>
        form_elements = [e for e in elements if e.tag_name == "form"]
        assert len(form_elements) == 1

    def test_table_query_accuracy(self):
        """Test that table query accurately identifies table elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        # TABLE_CODE contains exactly two <table> elements
        table_elements = [e for e in elements if e.tag_name == "table"]
        assert len(table_elements) == 2

    def test_link_query_accuracy(self):
        """Test that link query accurately identifies links."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        # LINK_IMAGE_CODE contains exactly five <a> elements
        a_elements = [e for e in elements if e.tag_name == "a"]
        assert len(a_elements) == 5

    def test_image_query_accuracy(self):
        """Test that image query accurately identifies images."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        # LINK_IMAGE_CODE contains exactly four <img> elements
        img_elements = [e for e in elements if e.tag_name == "img"]
        assert len(img_elements) == 4

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

        # Exact 1-based line spans for TAG_CODE's 35 elements in document
        # order (update when the fixture changes)
        assert [e.start_line for e in elements] == [
            3,
            4,
            5,
            6,
            7,
            8,
            8,
            9,
            9,
            10,
            10,
            14,
            15,
            16,
            17,
            19,
            20,
            21,
            23,
            24,
            25,
            28,
            29,
            34,
            34,
            34,
            35,
            35,
            35,
            36,
            36,
            36,
            37,
            37,
            37,
        ]
        assert [e.end_line for e in elements] == [
            31,
            13,
            5,
            12,
            11,
            8,
            8,
            9,
            9,
            10,
            10,
            27,
            18,
            16,
            17,
            22,
            20,
            21,
            26,
            24,
            25,
            30,
            29,
            34,
            34,
            34,
            35,
            35,
            35,
            36,
            36,
            36,
            37,
            37,
            37,
        ]

    def test_element_classification_accuracy(self):
        """Test that element classification is accurate."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Exactly 8 structure elements: div, header, nav, main, section,
        # article, aside, footer
        structure_elements = [e for e in elements if e.element_class == "structure"]
        assert len(structure_elements) == 8

        # Exactly 4 heading elements: h1, h2, h3, h4
        heading_elements = [e for e in elements if e.element_class == "heading"]
        assert len(heading_elements) == 4
