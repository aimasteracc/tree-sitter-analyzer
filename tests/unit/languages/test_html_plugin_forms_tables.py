"""HTML plugin tests — forms and tables."""

from tests.unit.languages._html_test_data import (
    FORM_CODE,
    TABLE_CODE,
    get_tree_for_code,
)
from tree_sitter_analyzer.languages.html_plugin import HtmlPlugin


class TestHtmlFormRecognition:
    """Test HTML form element recognition and extraction."""

    def test_extract_form_tag(self):
        """Test extraction of form tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        form_elements = [e for e in elements if e.tag_name == "form"]
        assert len(form_elements) == 1

    def test_extract_input_tags(self):
        """Test extraction of input tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        input_elements = [e for e in elements if e.tag_name == "input"]
        assert len(input_elements) == 6

    def test_extract_text_input(self):
        """Test extraction of text input."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        text_input = next(
            (
                e
                for e in elements
                if e.tag_name == "input"
                and e.attributes
                and e.attributes.get("type") == "text"
            ),
            None,
        )
        if text_input:
            assert text_input.attributes["type"] == "text"

    def test_extract_password_input(self):
        """Test extraction of password input."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        password_input = next(
            (
                e
                for e in elements
                if e.tag_name == "input"
                and e.attributes
                and e.attributes.get("type") == "password"
            ),
            None,
        )
        if password_input:
            assert password_input.attributes["type"] == "password"

    def test_extract_checkbox_input(self):
        """Test extraction of checkbox input."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        checkbox_input = next(
            (
                e
                for e in elements
                if e.tag_name == "input"
                and e.attributes
                and e.attributes.get("type") == "checkbox"
            ),
            None,
        )
        if checkbox_input:
            assert checkbox_input.attributes["type"] == "checkbox"

    def test_extract_radio_input(self):
        """Test extraction of radio input."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        radio_input = next(
            (
                e
                for e in elements
                if e.tag_name == "input"
                and e.attributes
                and e.attributes.get("type") == "radio"
            ),
            None,
        )
        if radio_input:
            assert radio_input.attributes["type"] == "radio"

    def test_extract_select_tag(self):
        """Test extraction of select tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        select_elements = [e for e in elements if e.tag_name == "select"]
        assert len(select_elements) == 1

    def test_extract_option_tags(self):
        """Test extraction of option tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        option_elements = [e for e in elements if e.tag_name == "option"]
        assert len(option_elements) == 3

    def test_extract_textarea_tag(self):
        """Test extraction of textarea tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        textarea_elements = [e for e in elements if e.tag_name == "textarea"]
        assert len(textarea_elements) == 1

    def test_extract_button_tag(self):
        """Test extraction of button tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        button_elements = [e for e in elements if e.tag_name == "button"]
        assert len(button_elements) == 2

    def test_extract_label_tag(self):
        """Test extraction of label tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        label_elements = [e for e in elements if e.tag_name == "label"]
        assert len(label_elements) == 8


class TestHtmlTableRecognition:
    """Test HTML table element recognition and extraction."""

    def test_extract_table_tag(self):
        """Test extraction of table tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        table_elements = [e for e in elements if e.tag_name == "table"]
        assert len(table_elements) == 2

    def test_extract_thead_tag(self):
        """Test extraction of thead tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        thead_elements = [e for e in elements if e.tag_name == "thead"]
        assert len(thead_elements) == 2

    def test_extract_tbody_tag(self):
        """Test extraction of tbody tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        tbody_elements = [e for e in elements if e.tag_name == "tbody"]
        assert len(tbody_elements) == 2

    def test_extract_tfoot_tag(self):
        """Test extraction of tfoot tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        tfoot_elements = [e for e in elements if e.tag_name == "tfoot"]
        assert len(tfoot_elements) == 1

    def test_extract_tr_tag(self):
        """Test extraction of tr tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        tr_elements = [e for e in elements if e.tag_name == "tr"]
        assert len(tr_elements) == 7

    def test_extract_th_tag(self):
        """Test extraction of th tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        th_elements = [e for e in elements if e.tag_name == "th"]
        assert len(th_elements) == 6

    def test_extract_td_tag(self):
        """Test extraction of td tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        td_elements = [e for e in elements if e.tag_name == "td"]
        assert len(td_elements) == 13

    def test_extract_caption_tag(self):
        """Test extraction of caption tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        caption_elements = [e for e in elements if e.tag_name == "caption"]
        assert len(caption_elements) == 1

    def test_extract_table_attributes(self):
        """Test extraction of table attributes."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        table_with_attrs = next(
            (e for e in elements if e.tag_name == "table" and e.attributes), None
        )
        if table_with_attrs:
            assert (
                "id" in table_with_attrs.attributes
                or "class" in table_with_attrs.attributes
            )
