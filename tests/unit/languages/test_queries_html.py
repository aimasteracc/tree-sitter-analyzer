#!/usr/bin/env python3
"""
Tests for HTML query module.

Tests all query patterns, utility functions, and edge cases.
"""

import pytest

from tree_sitter_analyzer.queries.html import (
    ALL_QUERIES,
    HTML_QUERIES,
    HTML_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_html_queries,
    get_html_query,
    get_html_query_description,
    get_query,
    list_queries,
)


class TestHTMLQueries:
    """Test HTML query definitions"""

    def test_html_queries_dict_exists(self):
        assert isinstance(HTML_QUERIES, dict)
        assert len(HTML_QUERIES) > 0

    def test_html_query_descriptions_dict_exists(self):
        assert isinstance(HTML_QUERY_DESCRIPTIONS, dict)
        assert len(HTML_QUERY_DESCRIPTIONS) > 0

    def test_all_queries_dict_exists(self):
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) > 0

    def test_all_queries_have_descriptions(self):
        for query_name in HTML_QUERIES.keys():
            assert query_name in HTML_QUERY_DESCRIPTIONS
            assert isinstance(HTML_QUERY_DESCRIPTIONS[query_name], str)
            assert len(HTML_QUERY_DESCRIPTIONS[query_name]) > 0

    def test_all_queries_have_query_string(self):
        for _query_name, query_string in HTML_QUERIES.items():
            assert isinstance(query_string, str)
            assert len(query_string.strip()) > 0

    def test_basic_element_queries(self):
        for key in ["element", "start_tag", "end_tag", "self_closing_tag"]:
            assert key in HTML_QUERIES

    def test_attribute_queries(self):
        for key in ["attribute", "attribute_name", "attribute_value", "class_attribute",
                     "id_attribute", "src_attribute", "href_attribute"]:
            assert key in HTML_QUERIES

    def test_text_queries(self):
        for key in ["text", "raw_text"]:
            assert key in HTML_QUERIES

    def test_comment_queries(self):
        assert "comment" in HTML_QUERIES

    def test_document_structure_queries(self):
        for key in ["doctype", "document"]:
            assert key in HTML_QUERIES

    def test_semantic_element_queries(self):
        for key in ["heading", "paragraph", "link", "image", "list", "list_item",
                     "table", "table_row", "table_cell"]:
            assert key in HTML_QUERIES

    def test_structure_element_queries(self):
        for key in ["html", "head", "body", "header", "footer", "main", "section",
                     "article", "aside", "nav", "div", "span"]:
            assert key in HTML_QUERIES

    def test_form_element_queries(self):
        for key in ["form", "input", "button", "textarea", "select", "option",
                     "label", "fieldset", "legend"]:
            assert key in HTML_QUERIES

    def test_media_element_queries(self):
        for key in ["video", "audio", "source", "track", "canvas", "svg"]:
            assert key in HTML_QUERIES

    def test_meta_element_queries(self):
        for key in ["meta", "title", "link_tag", "style", "script", "noscript", "base"]:
            assert key in HTML_QUERIES

    def test_script_and_style_queries(self):
        for key in ["script_element", "style_element"]:
            assert key in HTML_QUERIES

    def test_name_extraction_queries(self):
        for key in ["tag_name", "element_name"]:
            assert key in HTML_QUERIES

    def test_void_element_query(self):
        assert "void_element" in HTML_QUERIES


class TestGetHTMLQuery:
    """Test get_html_query function"""

    def test_get_html_query_valid(self):
        query = get_html_query("element")
        assert isinstance(query, str)
        assert len(query) > 0

    def test_get_html_query_all_defined_queries(self):
        for query_name in HTML_QUERIES.keys():
            query = get_html_query(query_name)
            assert isinstance(query, str)
            assert len(query) > 0

    def test_get_html_query_invalid(self):
        with pytest.raises(ValueError, match="does not exist"):
            get_html_query("nonexistent_query")

    def test_get_html_query_error_message(self):
        with pytest.raises(ValueError) as exc_info:
            get_html_query("invalid")
        assert "Available:" in str(exc_info.value)


class TestGetHTMLQueryDescription:
    """Test get_html_query_description function"""

    def test_get_html_query_description_valid(self):
        description = get_html_query_description("element")
        assert isinstance(description, str)
        assert len(description) > 0

    def test_get_html_query_description_all_queries(self):
        for query_name in HTML_QUERIES.keys():
            description = get_html_query_description(query_name)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_get_html_query_description_invalid(self):
        description = get_html_query_description("nonexistent")
        assert description == "No description"


class TestGetQuery:
    """Test get_query function"""

    def test_get_query_valid(self):
        query = get_query("element")
        assert isinstance(query, str)
        assert len(query) > 0

    def test_get_query_invalid(self):
        with pytest.raises(ValueError, match="not found"):
            get_query("invalid_query_name")

    def test_get_query_error_message(self):
        with pytest.raises(ValueError) as exc_info:
            get_query("invalid")
        assert "Available queries:" in str(exc_info.value)


class TestGetAllQueries:
    """Test get_all_queries function"""

    def test_get_all_queries_returns_dict(self):
        queries = get_all_queries()
        assert isinstance(queries, dict)
        assert len(queries) > 0

    def test_get_all_queries_structure(self):
        queries = get_all_queries()
        for _query_name, query_data in queries.items():
            assert isinstance(query_data, dict)
            assert "query" in query_data
            assert "description" in query_data

    def test_get_all_queries_contains_all_html_queries(self):
        queries = get_all_queries()
        for query_name in HTML_QUERIES.keys():
            assert query_name in queries

    def test_get_all_queries_contains_legacy_queries(self):
        queries = get_all_queries()
        for key in ["elements", "attributes", "comments", "text_content"]:
            assert key in queries


class TestListQueries:
    """Test list_queries function"""

    def test_list_queries_returns_list(self):
        queries = list_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_list_queries_contains_all_html_queries(self):
        queries = list_queries()
        for query_name in HTML_QUERIES.keys():
            assert query_name in queries

    def test_list_queries_no_duplicates(self):
        queries = list_queries()
        assert len(queries) == len(set(queries))


class TestGetAvailableHTMLQueries:
    """Test get_available_html_queries function"""

    def test_get_available_html_queries_returns_list(self):
        queries = get_available_html_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_get_available_html_queries_matches_html_queries(self):
        queries = get_available_html_queries()
        assert set(queries) == set(HTML_QUERIES.keys())


class TestQueryConsistency:
    """Test consistency between different query dictionaries"""

    def test_html_queries_count(self):
        assert len(HTML_QUERIES) >= 50

    def test_all_queries_count(self):
        assert len(ALL_QUERIES) >= len(HTML_QUERIES)

    def test_descriptions_match_queries(self):
        for query_name in HTML_QUERIES.keys():
            assert query_name in HTML_QUERY_DESCRIPTIONS


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_query_name(self):
        with pytest.raises(ValueError):
            get_html_query("")

    def test_none_query_name(self):
        with pytest.raises((ValueError, TypeError)):
            get_html_query(None)  # type: ignore

    def test_query_strings_are_tree_sitter_compatible(self):
        for query_name, query_string in HTML_QUERIES.items():
            assert "@" in query_string, f"Query '{query_name}' missing capture syntax"

    def test_query_descriptions_not_empty(self):
        for _query_name, description in HTML_QUERY_DESCRIPTIONS.items():
            assert description.strip() != ""
            assert description != "No description"


class TestSpecificQueries:
    """Test specific query patterns"""

    def test_element_query_pattern(self):
        query = get_html_query("element")
        assert "(element)" in query
        assert "@element" in query

    def test_attribute_query_pattern(self):
        query = get_html_query("attribute")
        assert "(attribute" in query
        assert "@attribute" in query

    def test_class_attribute_query_pattern(self):
        query = get_html_query("class_attribute")
        assert "#match?" in query
        assert "class" in query

    def test_id_attribute_query_pattern(self):
        query = get_html_query("id_attribute")
        assert "#match?" in query
        assert "id" in query

    def test_heading_query_pattern(self):
        query = get_html_query("heading")
        assert "h[1-6]" in query or "h1-6" in query.replace("[", "").replace("]", "")

    def test_void_element_query_pattern(self):
        query = get_html_query("void_element")
        assert "br" in query
        assert "img" in query
        assert "input" in query
