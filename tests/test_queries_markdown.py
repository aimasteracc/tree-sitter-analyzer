#!/usr/bin/env python3
"""
Markdown Query Tests

Tests for Markdown query definitions and functionality.
"""

import pytest

from tree_sitter_analyzer.queries.markdown import (
    MARKDOWN_QUERIES,
    QUERY_ALIASES,
    _get_query_description,
    get_available_queries,
    get_query,
    get_query_info,
)


class TestMarkdownQueries:
    """Test Markdown query definitions"""

    def test_markdown_queries_exist(self):
        """Test that all expected queries exist"""
        expected_queries = [
            "headers",
            "code_blocks",
            "inline_code",
            "links",
            "images",
            "lists",
            "emphasis",
            "blockquotes",
            "tables",
            "horizontal_rules",
            "html_blocks",
            "inline_html",
            "strikethrough",
            "task_lists",
            "footnotes",
            "text_content",
            "document",
            "all_elements",
        ]

        for query in expected_queries:
            assert query in MARKDOWN_QUERIES
            assert isinstance(MARKDOWN_QUERIES[query], str)
            assert len(MARKDOWN_QUERIES[query].strip()) > 0

    def test_query_aliases_exist(self):
        """Test that query aliases are properly defined"""
        expected_aliases = [
            "heading",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "code",
            "fenced_code",
            "link",
            "url",
            "image",
            "img",
            "list",
            "ul",
            "ol",
            "em",
            "strong",
            "bold",
            "italic",
            "quote",
            "blockquote",
            "table",
            "hr",
            "html",
            "strike",
            "task",
            "todo",
            "footnote",
            "text",
            "paragraph",
            "all",
            "everything",
        ]

        for alias in expected_aliases:
            assert alias in QUERY_ALIASES
            assert QUERY_ALIASES[alias] in MARKDOWN_QUERIES

    def test_get_query_direct(self):
        """Test getting queries directly"""
        query = get_query("headers")
        assert isinstance(query, str)
        assert "atx_heading" in query or "setext_heading" in query

    def test_get_query_alias(self):
        """Test getting queries via aliases"""
        query1 = get_query("headers")
        query2 = get_query("heading")
        assert query1 == query2

    def test_get_query_unknown(self):
        """Test getting unknown query raises KeyError"""
        with pytest.raises(KeyError):
            get_query("unknown_query")

    def test_get_available_queries(self):
        """Test getting list of available queries"""
        queries = get_available_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0
        assert "headers" in queries
        assert "heading" in queries  # alias
        assert sorted(queries) == queries  # Should be sorted

    def test_get_query_info_direct(self):
        """Test getting query info for direct query"""
        info = get_query_info("headers")
        assert isinstance(info, dict)
        assert info["name"] == "headers"
        assert info["actual_name"] == "headers"
        assert info["is_alias"] is False
        assert "query" in info
        assert "description" in info

    def test_get_query_info_alias(self):
        """Test getting query info for alias"""
        info = get_query_info("heading")
        assert isinstance(info, dict)
        assert info["name"] == "heading"
        assert info["actual_name"] == "headers"
        assert info["is_alias"] is True
        assert "query" in info
        assert "description" in info

    def test_get_query_info_unknown(self):
        """Test getting query info for unknown query"""
        info = get_query_info("unknown")
        assert isinstance(info, dict)
        assert "error" in info
        assert "not found" in info["error"]

    def test_query_descriptions(self):
        """Test query descriptions"""
        description = _get_query_description("headers")
        assert isinstance(description, str)
        assert len(description) > 0
        assert "heading" in description.lower()

        # Test unknown description
        description = _get_query_description("unknown")
        assert "No description available" in description


class TestMarkdownQueryContent:
    """Test the content of specific Markdown queries"""

    def test_headers_query_content(self):
        """Test headers query contains expected patterns"""
        query = get_query("headers")
        assert "atx_heading" in query
        assert "setext_heading" in query
        assert "@header" in query

    def test_code_blocks_query_content(self):
        """Test code blocks query contains expected patterns"""
        query = get_query("code_blocks")
        assert "fenced_code_block" in query
        assert "indented_code_block" in query
        assert "@code_block" in query

    def test_links_query_content(self):
        """Test links query contains expected patterns"""
        query = get_query("links")
        assert "inline" in query
        assert "@inline" in query

    def test_images_query_content(self):
        """Test images query contains expected patterns"""
        query = get_query("images")
        assert "inline" in query
        assert "@inline" in query

    def test_lists_query_content(self):
        """Test lists query contains expected patterns"""
        query = get_query("lists")
        assert "list" in query
        assert "list_item" in query
        assert "@list" in query
        assert "@list_item" in query

    def test_emphasis_query_content(self):
        """Test emphasis query contains expected patterns"""
        query = get_query("emphasis")
        assert "inline" in query
        assert "@inline" in query

    def test_blockquotes_query_content(self):
        """Test blockquotes query contains expected patterns"""
        query = get_query("blockquotes")
        assert "block_quote" in query
        assert "@blockquote" in query

    def test_tables_query_content(self):
        """Test tables query contains expected patterns"""
        query = get_query("tables")
        assert "pipe_table" in query
        assert "@table" in query

    def test_footnotes_query_content(self):
        """Test footnotes query contains expected patterns"""
        query = get_query("footnotes")
        assert "paragraph" in query
        assert "inline" in query
        assert "@paragraph" in query
        assert "@inline" in query

    def test_all_elements_query_content(self):
        """Test all_elements query contains major patterns"""
        query = get_query("all_elements")
        assert "atx_heading" in query
        assert "fenced_code_block" in query
        assert "inline" in query
        assert "list" in query
        assert "@heading" in query
        assert "@code_block" in query
        assert "@inline" in query
        assert "@list" in query


class TestMarkdownQueryAliases:
    """Test specific query aliases"""

    def test_header_level_aliases(self):
        """Test header level aliases all point to headers"""
        for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            query = get_query(level)
            headers_query = get_query("headers")
            assert query == headers_query

    def test_code_aliases(self):
        """Test code-related aliases"""
        code_query = get_query("code_blocks")
        assert get_query("code") == code_query
        assert get_query("fenced_code") == code_query

    def test_link_aliases(self):
        """Test link-related aliases"""
        links_query = get_query("links")
        assert get_query("link") == links_query
        assert get_query("url") == links_query

    def test_image_aliases(self):
        """Test image-related aliases"""
        images_query = get_query("images")
        assert get_query("image") == images_query
        assert get_query("img") == images_query

    def test_list_aliases(self):
        """Test list-related aliases"""
        lists_query = get_query("lists")
        assert get_query("list") == lists_query
        assert get_query("ul") == lists_query
        assert get_query("ol") == lists_query

    def test_emphasis_aliases(self):
        """Test emphasis-related aliases"""
        emphasis_query = get_query("emphasis")
        assert get_query("em") == emphasis_query
        assert get_query("strong") == emphasis_query
        assert get_query("bold") == emphasis_query
        assert get_query("italic") == emphasis_query

    def test_comprehensive_aliases(self):
        """Test comprehensive aliases"""
        all_query = get_query("all_elements")
        assert get_query("all") == all_query
        assert get_query("everything") == all_query


class TestMarkdownQueryValidation:
    """Test query validation and edge cases"""

    def test_all_queries_are_strings(self):
        """Test that all queries are valid strings"""
        for _query_name, query_string in MARKDOWN_QUERIES.items():
            assert isinstance(query_string, str)
            assert len(query_string.strip()) > 0
            # Basic syntax check - should contain @ symbols for captures
            assert "@" in query_string

    def test_all_aliases_point_to_valid_queries(self):
        """Test that all aliases point to valid queries"""
        for alias, target in QUERY_ALIASES.items():
            assert target in MARKDOWN_QUERIES
            # Should be able to get the query without error
            query = get_query(alias)
            assert isinstance(query, str)

    def test_no_circular_aliases(self):
        """Test that there are no circular alias references"""
        for _alias, target in QUERY_ALIASES.items():
            # Target should not be an alias itself
            assert target not in QUERY_ALIASES

    def test_query_capture_names(self):
        """Test that queries have reasonable capture names"""
        for _query_name, query_string in MARKDOWN_QUERIES.items():
            # Should have at least one capture
            assert "@" in query_string
            # Captures should not be empty
            lines = query_string.split("\n")
            capture_lines = [line for line in lines if "@" in line]
            assert len(capture_lines) > 0

    def test_query_syntax_basics(self):
        """Test basic query syntax"""
        for query_name, query_string in MARKDOWN_QUERIES.items():
            # Should have balanced parentheses
            open_parens = query_string.count("(")
            close_parens = query_string.count(")")
            assert open_parens == close_parens, (
                f"Unbalanced parentheses in {query_name}"
            )


class TestMarkdownQueryEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_query_name(self):
        """Test handling of empty query name"""
        with pytest.raises(KeyError):
            get_query("")

    def test_none_query_name(self):
        """Test handling of None query name"""
        with pytest.raises((KeyError, TypeError)):
            get_query(None)

    def test_case_sensitivity(self):
        """Test that query names are case sensitive"""
        # Should work
        query = get_query("headers")
        assert isinstance(query, str)

        # Should fail (case sensitive)
        with pytest.raises(KeyError):
            get_query("HEADERS")

    def test_whitespace_in_query_name(self):
        """Test handling of whitespace in query names"""
        with pytest.raises(KeyError):
            get_query(" headers ")

    def test_special_characters_in_query_name(self):
        """Test handling of special characters in query names"""
        with pytest.raises(KeyError):
            get_query("headers!")

        with pytest.raises(KeyError):
            get_query("headers@test")


if __name__ == "__main__":
    pytest.main(
        [
            __file__,
            "-v",
            "--cov=tree_sitter_analyzer.queries.markdown",
            "--cov-report=term-missing",
        ]
    )
