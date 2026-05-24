#!/usr/bin/env python3
"""
Tests for HTML Formatter (advanced)

Tests for falsy attributes, unknown element types, non-dict elements,
compact formatter filepath handling, element classification, truncation,
and other advanced edge cases.
"""

import json

from tree_sitter_analyzer.formatters.html_formatter import (
    HtmlCompactFormatter,
    HtmlFormatter,
    HtmlJsonFormatter,
)
from tree_sitter_analyzer.models import MarkupElement


class TestHtmlFormatterFalsyAttributes:
    """Cover attribute formatting with falsy values (line 185)"""

    def test_markup_with_empty_string_attribute(self):
        """Format markup element with empty string attribute value"""
        formatter = HtmlFormatter()
        elem = MarkupElement(
            name="input",
            start_line=1,
            end_line=1,
            tag_name="input",
            attributes={"disabled": "", "type": "text"},
            element_class="form",
            language="html",
        )
        result = formatter.format([elem])
        assert "disabled" in result

    def test_markup_with_none_attribute(self):
        """Format markup element with None attribute value"""
        formatter = HtmlFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={"hidden": None, "data-x": "val"},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem])
        assert "hidden" in result

    def test_markup_with_boolean_false_attribute(self):
        """Format markup element with False attribute value"""
        formatter = HtmlFormatter()
        elem = MarkupElement(
            name="span",
            start_line=1,
            end_line=1,
            tag_name="span",
            attributes={"contenteditable": False},
            element_class="text",
            language="html",
        )
        result = formatter.format([elem])
        assert "contenteditable" in result


class TestHtmlFormatterUnknownElementType:
    """Cover getattr fallback for unknown element types (lines 295-299)"""

    def test_unknown_object_in_format(self):
        """Format with unknown object type uses getattr fallback"""
        formatter = HtmlFormatter()

        class UnknownType:
            pass

        obj = UnknownType()
        obj.element_type = "custom"
        obj.name = "my_custom"
        obj.start_line = 10
        obj.end_line = 20
        obj.language = "xml"

        result = formatter.format([obj])
        # Should appear in the "Other elements" section
        assert "custom" in result


class TestHtmlOtherElementsNonDict:
    """Cover HtmlJsonFormatter dict element handling (lines 381-393)"""

    def test_json_format_dict_with_tag_name(self):
        """JSON format dict element with tag_name"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "test_div",
            "tag_name": "div",
            "element_class": "structure",
            "start_line": 1,
            "end_line": 10,
            "attributes": {},
            "language": "html",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["markup_elements"]) == 1

    def test_json_format_dict_with_element_type_tag(self):
        """JSON format dict element with type='tag'"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "header",
            "element_type": "tag",
            "start_line": 1,
            "end_line": 5,
            "language": "html",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["markup_elements"]) == 1

    def test_json_format_dict_with_selector(self):
        """JSON format dict element with selector"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "body_rule",
            "selector": "body",
            "element_class": "layout",
            "start_line": 1,
            "end_line": 20,
            "language": "css",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["style_elements"]) == 1

    def test_json_format_dict_with_type_rule(self):
        """JSON format dict element with element_type='rule'"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "h1_rule",
            "element_type": "rule",
            "start_line": 5,
            "end_line": 10,
            "language": "css",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["style_elements"]) == 1

    def test_json_format_dict_unknown_type(self):
        """JSON format dict element with unknown type goes to other"""
        formatter = HtmlJsonFormatter()
        d = {
            "name": "custom_thing",
            "element_type": "weird_type",
            "start_line": 1,
            "end_line": 1,
            "language": "text",
        }
        result = formatter.format([d])
        parsed = json.loads(result)
        assert len(parsed["html_analysis"]["other_elements"]) == 1


class TestHtmlCompactFormatterFilepath:
    """Cover filename extraction in compact formatter (lines 455-457)"""

    def test_filepath_html_extension_stripped(self):
        """Compact format strips .html extension from filename"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem], file_path="/path/to/index.html")
        assert "# index" in result

    def test_filepath_htm_extension_stripped(self):
        """Compact format strips .htm extension from filename"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem], file_path="/path/to/page.htm")
        assert "# page" in result

    def test_filepath_non_html_extension_kept(self):
        """Compact format keeps non-html filename as-is"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem], file_path="/path/to/component.jsx")
        assert "# component.jsx" in result

    def test_filepath_backslash_path(self):
        """Compact format handles Windows-style backslash paths"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="div",
            start_line=1,
            end_line=1,
            tag_name="div",
            attributes={},
            element_class="structure",
            language="html",
        )
        result = formatter.format([elem], file_path="C:\\project\\layout.html")
        assert "# layout" in result


class TestHtmlCompactElementClassification:
    """Cover element classification in compact formatter (lines 481-493)"""

    def test_heading_element_classification(self):
        """Compact format classifies heading elements"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="h1",
            start_line=1,
            end_line=1,
            tag_name="h1",
            attributes={},
            element_class="heading",
            language="html",
        )
        result = formatter.format([elem])
        assert "| Headings | 1 |" in result

    def test_table_element_classification(self):
        """Compact format classifies table elements"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="table",
            start_line=1,
            end_line=10,
            tag_name="table",
            attributes={},
            element_class="table",
            language="html",
        )
        result = formatter.format([elem])
        assert "| Tables | 1 |" in result

    def test_list_element_classification(self):
        """Compact format classifies list elements"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="ul",
            start_line=1,
            end_line=10,
            tag_name="ul",
            attributes={},
            element_class="list",
            language="html",
        )
        result = formatter.format([elem])
        assert "| Lists | 1 |" in result

    def test_metadata_element_classification(self):
        """Compact format classifies metadata elements"""
        formatter = HtmlCompactFormatter()
        elem = MarkupElement(
            name="meta",
            start_line=1,
            end_line=1,
            tag_name="meta",
            attributes={"charset": "utf-8"},
            element_class="metadata",
            language="html",
        )
        result = formatter.format([elem])
        assert "| Metadata | 1 |" in result


class TestHtmlCompactOver20Elements:
    """Cover >20 elements truncation message (line 570)"""

    def test_more_than_20_important_elements(self):
        """Compact format shows '(N more)' when >20 important elements"""
        formatter = HtmlCompactFormatter()
        # Create 25 root-level divs (parent=None means they're "important")
        elements = []
        for i in range(25):
            elem = MarkupElement(
                name=f"div{i}",
                start_line=i * 2 + 1,
                end_line=i * 2 + 2,
                tag_name="div",
                attributes={"id": f"item{i}", "class": "box"},
                element_class="structure",
                language="html",
            )
            elements.append(elem)

        result = formatter.format(elements)
        # Should show first 20 in the table
        for i in range(20):
            assert f"#item{i}" in result
        # Should show "5 more" row
        assert "5 more" in result


class TestHtmlFormatOtherElementsNonDict:
    """Cover _format_other_elements getattr fallback (lines 295-299)"""

    def test_format_other_elements_non_dict_non_markup(self):
        """Directly call _format_other_elements with non-dict, non-MarkupElement"""
        formatter = HtmlFormatter()

        class UnknownThing:
            pass

        obj = UnknownThing()
        obj.element_type = "weird"
        obj.name = "thingo"
        obj.start_line = 5
        obj.end_line = 15
        obj.language = "nolang"

        # Call _format_other_elements directly (bypasses _element_to_dict)
        result_lines = formatter._format_other_elements([obj])
        result = "\n".join(result_lines)
        assert "weird" in result
        assert "thingo" in result
        assert "5-15" in result
        assert "nolang" in result
