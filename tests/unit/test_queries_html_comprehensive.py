#!/usr/bin/env python3
"""
Comprehensive tests for HTML query module

This test module provides comprehensive coverage for the HTML queries module,
testing all query patterns, utility functions, and edge cases.
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
        """Test that HTML_QUERIES dictionary exists"""
        assert isinstance(HTML_QUERIES, dict)
        assert len(HTML_QUERIES) > 0

    def test_html_query_descriptions_dict_exists(self):
        """Test that HTML_QUERY_DESCRIPTIONS dictionary exists"""
        assert isinstance(HTML_QUERY_DESCRIPTIONS, dict)
        assert len(HTML_QUERY_DESCRIPTIONS) > 0

    def test_all_queries_dict_exists(self):
        """Test that ALL_QUERIES dictionary exists"""
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) > 0

    def test_all_queries_have_descriptions(self):
        """Test that all queries in HTML_QUERIES have descriptions"""
        for query_name in HTML_QUERIES.keys():
            assert query_name in HTML_QUERY_DESCRIPTIONS
            assert isinstance(HTML_QUERY_DESCRIPTIONS[query_name], str)
            assert len(HTML_QUERY_DESCRIPTIONS[query_name]) > 0

    def test_all_queries_have_query_string(self):
        """Test that all queries have non-empty query strings"""
        for _query_name, query_string in HTML_QUERIES.items():
            assert isinstance(query_string, str)
            assert len(query_string.strip()) > 0

    def test_basic_element_queries(self):
        """Test basic element queries exist"""
        assert "element" in HTML_QUERIES
        assert "start_tag" in HTML_QUERIES
        assert "end_tag" in HTML_QUERIES
        assert "self_closing_tag" in HTML_QUERIES

    def test_attribute_queries(self):
        """Test attribute-related queries exist"""
        assert "attribute" in HTML_QUERIES
        assert "attribute_name" in HTML_QUERIES
        assert "attribute_value" in HTML_QUERIES
        assert "class_attribute" in HTML_QUERIES
        assert "id_attribute" in HTML_QUERIES
        assert "src_attribute" in HTML_QUERIES
        assert "href_attribute" in HTML_QUERIES

    def test_text_queries(self):
        """Test text-related queries exist"""
        assert "text" in HTML_QUERIES
        assert "raw_text" in HTML_QUERIES

    def test_comment_queries(self):
        """Test comment queries exist"""
        assert "comment" in HTML_QUERIES

    def test_document_structure_queries(self):
        """Test document structure queries exist"""
        assert "doctype" in HTML_QUERIES
        assert "document" in HTML_QUERIES

    def test_semantic_element_queries(self):
        """Test semantic element queries exist"""
        assert "heading" in HTML_QUERIES
        assert "paragraph" in HTML_QUERIES
        assert "link" in HTML_QUERIES
        assert "image" in HTML_QUERIES
        assert "list" in HTML_QUERIES
        assert "list_item" in HTML_QUERIES
        assert "table" in HTML_QUERIES
        assert "table_row" in HTML_QUERIES
        assert "table_cell" in HTML_QUERIES

    def test_structure_element_queries(self):
        """Test structure element queries exist"""
        assert "html" in HTML_QUERIES
        assert "head" in HTML_QUERIES
        assert "body" in HTML_QUERIES
        assert "header" in HTML_QUERIES
        assert "footer" in HTML_QUERIES
        assert "main" in HTML_QUERIES
        assert "section" in HTML_QUERIES
        assert "article" in HTML_QUERIES
        assert "aside" in HTML_QUERIES
        assert "nav" in HTML_QUERIES
        assert "div" in HTML_QUERIES
        assert "span" in HTML_QUERIES

    def test_form_element_queries(self):
        """Test form element queries exist"""
        assert "form" in HTML_QUERIES
        assert "input" in HTML_QUERIES
        assert "button" in HTML_QUERIES
        assert "textarea" in HTML_QUERIES
        assert "select" in HTML_QUERIES
        assert "option" in HTML_QUERIES
        assert "label" in HTML_QUERIES
        assert "fieldset" in HTML_QUERIES
        assert "legend" in HTML_QUERIES

    def test_media_element_queries(self):
        """Test media element queries exist"""
        assert "video" in HTML_QUERIES
        assert "audio" in HTML_QUERIES
        assert "source" in HTML_QUERIES
        assert "track" in HTML_QUERIES
        assert "canvas" in HTML_QUERIES
        assert "svg" in HTML_QUERIES

    def test_meta_element_queries(self):
        """Test meta element queries exist"""
        assert "meta" in HTML_QUERIES
        assert "title" in HTML_QUERIES
        assert "link_tag" in HTML_QUERIES
        assert "style" in HTML_QUERIES
        assert "script" in HTML_QUERIES
        assert "noscript" in HTML_QUERIES
        assert "base" in HTML_QUERIES

    def test_script_and_style_queries(self):
        """Test script and style element queries exist"""
        assert "script_element" in HTML_QUERIES
        assert "style_element" in HTML_QUERIES

    def test_name_extraction_queries(self):
        """Test name extraction queries exist"""
        assert "tag_name" in HTML_QUERIES
        assert "element_name" in HTML_QUERIES

    def test_void_element_query(self):
        """Test void element query exists"""
        assert "void_element" in HTML_QUERIES


class TestGetHTMLQuery:
    """Test get_html_query function"""

    def test_get_html_query_valid(self):
        """Test getting a valid HTML query"""
        query = get_html_query("element")
        assert isinstance(query, str)
        assert len(query) > 0

    def test_get_html_query_all_defined_queries(self):
        """Test getting all defined queries"""
        for query_name in HTML_QUERIES.keys():
            query = get_html_query(query_name)
            assert isinstance(query, str)
            assert len(query) > 0

    def test_get_html_query_invalid(self):
        """Test getting an invalid query raises ValueError"""
        with pytest.raises(ValueError, match="does not exist"):
            get_html_query("nonexistent_query")

    def test_get_html_query_error_message(self):
        """Test error message contains available queries"""
        with pytest.raises(ValueError) as exc_info:
            get_html_query("invalid")
        assert "Available:" in str(exc_info.value)


class TestGetHTMLQueryDescription:
    """Test get_html_query_description function"""

    def test_get_html_query_description_valid(self):
        """Test getting a valid query description"""
        description = get_html_query_description("element")
        assert isinstance(description, str)
        assert len(description) > 0

    def test_get_html_query_description_all_queries(self):
        """Test getting descriptions for all queries"""
        for query_name in HTML_QUERIES.keys():
            description = get_html_query_description(query_name)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_get_html_query_description_invalid(self):
        """Test getting description for invalid query"""
        description = get_html_query_description("nonexistent")
        assert description == "No description"


class TestGetQuery:
    """Test get_query function"""

    def test_get_query_valid(self):
        """Test getting a query using get_query"""
        query = get_query("element")
        assert isinstance(query, str)
        assert len(query) > 0

    def test_get_query_invalid(self):
        """Test getting invalid query raises ValueError"""
        with pytest.raises(ValueError, match="not found"):
            get_query("invalid_query_name")

    def test_get_query_error_message(self):
        """Test error message contains available queries"""
        with pytest.raises(ValueError) as exc_info:
            get_query("invalid")
        assert "Available queries:" in str(exc_info.value)


class TestGetAllQueries:
    """Test get_all_queries function"""

    def test_get_all_queries_returns_dict(self):
        """Test get_all_queries returns a dictionary"""
        queries = get_all_queries()
        assert isinstance(queries, dict)
        assert len(queries) > 0

    def test_get_all_queries_structure(self):
        """Test structure of returned queries"""
        queries = get_all_queries()
        for _query_name, query_data in queries.items():
            assert isinstance(query_data, dict)
            assert "query" in query_data
            assert "description" in query_data
            assert isinstance(query_data["query"], str)
            assert isinstance(query_data["description"], str)

    def test_get_all_queries_contains_all_html_queries(self):
        """Test that all HTML_QUERIES are in the result"""
        queries = get_all_queries()
        for query_name in HTML_QUERIES.keys():
            assert query_name in queries

    def test_get_all_queries_contains_legacy_queries(self):
        """Test that legacy queries are included"""
        queries = get_all_queries()
        assert "elements" in queries
        assert "attributes" in queries
        assert "comments" in queries
        assert "text_content" in queries


class TestListQueries:
    """Test list_queries function"""

    def test_list_queries_returns_list(self):
        """Test list_queries returns a list"""
        queries = list_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_list_queries_contains_all_html_queries(self):
        """Test that all HTML queries are in the list"""
        queries = list_queries()
        for query_name in HTML_QUERIES.keys():
            assert query_name in queries

    def test_list_queries_no_duplicates(self):
        """Test that there are no duplicates in the query list"""
        queries = list_queries()
        assert len(queries) == len(set(queries))


class TestGetAvailableHTMLQueries:
    """Test get_available_html_queries function"""

    def test_get_available_html_queries_returns_list(self):
        """Test get_available_html_queries returns a list"""
        queries = get_available_html_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_get_available_html_queries_matches_html_queries(self):
        """Test that available queries match HTML_QUERIES keys"""
        queries = get_available_html_queries()
        assert set(queries) == set(HTML_QUERIES.keys())


class TestALLQueriesIntegration:
    """Test ALL_QUERIES integration"""

    def test_all_queries_format(self):
        """Test ALL_QUERIES has correct format"""
        for _query_name, query_data in ALL_QUERIES.items():
            assert isinstance(query_data, dict)
            assert "query" in query_data
            assert "description" in query_data

    def test_all_queries_query_strings_valid(self):
        """Test all query strings are valid"""
        for _query_name, query_data in ALL_QUERIES.items():
            assert isinstance(query_data["query"], str)
            assert len(query_data["query"].strip()) > 0

    def test_all_queries_descriptions_valid(self):
        """Test all descriptions are valid"""
        for _query_name, query_data in ALL_QUERIES.items():
            assert isinstance(query_data["description"], str)
            assert len(query_data["description"]) > 0


class TestLegacyQueries:
    """Test legacy query definitions"""

    def test_legacy_queries_in_all_queries(self):
        """Test that legacy queries are available in ALL_QUERIES"""
        assert "elements" in ALL_QUERIES
        assert "attributes" in ALL_QUERIES
        assert "comments" in ALL_QUERIES
        assert "text_content" in ALL_QUERIES

    def test_legacy_elements_query(self):
        """Test legacy elements query"""
        query_data = ALL_QUERIES["elements"]
        assert "query" in query_data
        assert "element" in query_data["query"].lower()

    def test_legacy_attributes_query(self):
        """Test legacy attributes query"""
        query_data = ALL_QUERIES["attributes"]
        assert "query" in query_data
        assert "attribute" in query_data["query"].lower()

    def test_legacy_comments_query(self):
        """Test legacy comments query"""
        query_data = ALL_QUERIES["comments"]
        assert "query" in query_data
        assert "comment" in query_data["query"].lower()

    def test_legacy_text_content_query(self):
        """Test legacy text_content query"""
        query_data = ALL_QUERIES["text_content"]
        assert "query" in query_data
        assert "text" in query_data["query"].lower()


class TestQueryConsistency:
    """Test consistency between different query dictionaries"""

    def test_html_queries_count(self):
        """Test that we have a substantial number of queries"""
        assert len(HTML_QUERIES) >= 50  # Should have at least 50 queries

    def test_all_queries_count(self):
        """Test ALL_QUERIES includes all HTML queries plus legacy"""
        # ALL_QUERIES should have all HTML_QUERIES plus legacy queries
        assert len(ALL_QUERIES) >= len(HTML_QUERIES)

    def test_descriptions_match_queries(self):
        """Test that every query in HTML_QUERIES has a description"""
        for query_name in HTML_QUERIES.keys():
            assert query_name in HTML_QUERY_DESCRIPTIONS


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_query_name(self):
        """Test empty query name"""
        with pytest.raises(ValueError):
            get_html_query("")

    def test_none_query_name(self):
        """Test None query name"""
        with pytest.raises((ValueError, TypeError)):
            get_html_query(None)  # type: ignore

    def test_query_strings_are_tree_sitter_compatible(self):
        """Test that query strings appear to be valid Tree-sitter syntax"""
        for query_name, query_string in HTML_QUERIES.items():
            # Basic validation: should contain @ for captures
            assert "@" in query_string, f"Query '{query_name}' missing capture syntax"

    def test_query_descriptions_not_empty(self):
        """Test that no query description is empty"""
        for _query_name, description in HTML_QUERY_DESCRIPTIONS.items():
            assert description.strip() != ""
            assert description != "No description"


class TestSpecificQueries:
    """Test specific query patterns"""

    def test_element_query_pattern(self):
        """Test element query has expected pattern"""
        query = get_html_query("element")
        assert "(element)" in query
        assert "@element" in query

    def test_attribute_query_pattern(self):
        """Test attribute query has expected pattern"""
        query = get_html_query("attribute")
        assert "(attribute" in query
        assert "@attribute" in query

    def test_class_attribute_query_pattern(self):
        """Test class attribute query uses regex matching"""
        query = get_html_query("class_attribute")
        assert "#match?" in query
        assert "class" in query

    def test_id_attribute_query_pattern(self):
        """Test id attribute query uses regex matching"""
        query = get_html_query("id_attribute")
        assert "#match?" in query
        assert "id" in query

    def test_heading_query_pattern(self):
        """Test heading query matches h1-h6"""
        query = get_html_query("heading")
        assert "h[1-6]" in query or "h1-6" in query.replace("[", "").replace("]", "")

    def test_void_element_query_pattern(self):
        """Test void element query matches expected elements"""
        query = get_html_query("void_element")
        assert "br" in query
        assert "img" in query
        assert "input" in query
