#!/usr/bin/env python3
"""
Comprehensive tests for CSS query module

This test module provides comprehensive coverage for the CSS queries module,
testing all query patterns, utility functions, and edge cases.
"""

import pytest

from tree_sitter_analyzer.queries.css import (
    ALL_QUERIES,
    CSS_QUERIES,
    CSS_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_css_queries,
    get_css_query,
    get_css_query_description,
    get_query,
    list_queries,
)


class TestCSSQueries:
    """Test CSS query definitions"""

    def test_css_queries_dict_exists(self):
        """Test that CSS_QUERIES dictionary exists"""
        assert isinstance(CSS_QUERIES, dict)
        assert len(CSS_QUERIES) > 0

    def test_css_query_descriptions_dict_exists(self):
        """Test that CSS_QUERY_DESCRIPTIONS dictionary exists"""
        assert isinstance(CSS_QUERY_DESCRIPTIONS, dict)
        assert len(CSS_QUERY_DESCRIPTIONS) > 0

    def test_all_queries_dict_exists(self):
        """Test that ALL_QUERIES dictionary exists"""
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) > 0

    def test_all_queries_have_descriptions(self):
        """Test that all queries in CSS_QUERIES have descriptions"""
        for query_name in CSS_QUERIES.keys():
            assert query_name in CSS_QUERY_DESCRIPTIONS
            assert isinstance(CSS_QUERY_DESCRIPTIONS[query_name], str)
            assert len(CSS_QUERY_DESCRIPTIONS[query_name]) > 0

    def test_all_queries_have_query_string(self):
        """Test that all queries have non-empty query strings"""
        for _query_name, query_string in CSS_QUERIES.items():
            assert isinstance(query_string, str)
            assert len(query_string.strip()) > 0

    def test_basic_rule_queries(self):
        """Test basic rule queries exist"""
        assert "rule_set" in CSS_QUERIES
        assert "rule" in CSS_QUERIES
        assert "declaration" in CSS_QUERIES
        assert "property" in CSS_QUERIES
        assert "property_name" in CSS_QUERIES
        assert "property_value" in CSS_QUERIES

    def test_selector_queries(self):
        """Test selector-related queries exist"""
        assert "selector" in CSS_QUERIES
        assert "selectors" in CSS_QUERIES
        assert "class_selector" in CSS_QUERIES
        assert "id_selector" in CSS_QUERIES
        assert "tag_selector" in CSS_QUERIES
        assert "universal_selector" in CSS_QUERIES
        assert "attribute_selector" in CSS_QUERIES
        assert "pseudo_class_selector" in CSS_QUERIES
        assert "pseudo_element_selector" in CSS_QUERIES
        assert "descendant_selector" in CSS_QUERIES
        assert "child_selector" in CSS_QUERIES
        assert "sibling_selector" in CSS_QUERIES
        assert "adjacent_sibling_selector" in CSS_QUERIES

    def test_at_rule_queries(self):
        """Test at-rule queries exist"""
        assert "at_rule" in CSS_QUERIES
        assert "import_statement" in CSS_QUERIES
        assert "media_statement" in CSS_QUERIES
        assert "charset_statement" in CSS_QUERIES
        assert "namespace_statement" in CSS_QUERIES
        assert "keyframes_statement" in CSS_QUERIES
        assert "supports_statement" in CSS_QUERIES
        assert "page_statement" in CSS_QUERIES
        assert "font_face_statement" in CSS_QUERIES

    def test_media_query_queries(self):
        """Test media query-related queries exist"""
        assert "media_query" in CSS_QUERIES
        assert "media_feature" in CSS_QUERIES
        assert "media_type" in CSS_QUERIES

    def test_value_queries(self):
        """Test value-related queries exist"""
        assert "string_value" in CSS_QUERIES
        assert "integer_value" in CSS_QUERIES
        assert "float_value" in CSS_QUERIES
        assert "color_value" in CSS_QUERIES
        assert "call_expression" in CSS_QUERIES
        assert "function_name" in CSS_QUERIES
        assert "arguments" in CSS_QUERIES

    def test_css_function_queries(self):
        """Test CSS function queries exist"""
        assert "url" in CSS_QUERIES
        assert "calc" in CSS_QUERIES
        assert "var" in CSS_QUERIES
        assert "rgb" in CSS_QUERIES
        assert "rgba" in CSS_QUERIES
        assert "hsl" in CSS_QUERIES
        assert "hsla" in CSS_QUERIES

    def test_unit_queries(self):
        """Test unit-related queries exist"""
        assert "dimension" in CSS_QUERIES
        assert "percentage" in CSS_QUERIES
        assert "unit" in CSS_QUERIES

    def test_layout_property_queries(self):
        """Test layout property queries exist"""
        assert "display" in CSS_QUERIES
        assert "position" in CSS_QUERIES
        assert "float" in CSS_QUERIES
        assert "clear" in CSS_QUERIES
        assert "overflow" in CSS_QUERIES
        assert "visibility" in CSS_QUERIES
        assert "z_index" in CSS_QUERIES

    def test_box_model_queries(self):
        """Test box model property queries exist"""
        assert "width" in CSS_QUERIES
        assert "height" in CSS_QUERIES
        assert "margin" in CSS_QUERIES
        assert "padding" in CSS_QUERIES
        assert "border" in CSS_QUERIES
        assert "box_sizing" in CSS_QUERIES

    def test_typography_queries(self):
        """Test typography property queries exist"""
        assert "font" in CSS_QUERIES
        assert "color" in CSS_QUERIES
        assert "text" in CSS_QUERIES
        assert "line_height" in CSS_QUERIES
        assert "letter_spacing" in CSS_QUERIES
        assert "word_spacing" in CSS_QUERIES

    def test_background_queries(self):
        """Test background property queries exist"""
        assert "background" in CSS_QUERIES

    def test_flexbox_queries(self):
        """Test flexbox property queries exist"""
        assert "flex" in CSS_QUERIES
        assert "justify_content" in CSS_QUERIES
        assert "align_items" in CSS_QUERIES
        assert "align_content" in CSS_QUERIES

    def test_grid_queries(self):
        """Test grid property queries exist"""
        assert "grid" in CSS_QUERIES

    def test_animation_queries(self):
        """Test animation property queries exist"""
        assert "animation" in CSS_QUERIES
        assert "transition" in CSS_QUERIES
        assert "transform" in CSS_QUERIES

    def test_comment_queries(self):
        """Test comment queries exist"""
        assert "comment" in CSS_QUERIES

    def test_custom_property_queries(self):
        """Test custom property (CSS variable) queries exist"""
        assert "custom_property" in CSS_QUERIES

    def test_important_queries(self):
        """Test !important queries exist"""
        assert "important" in CSS_QUERIES

    def test_keyframe_queries(self):
        """Test keyframe-related queries exist"""
        assert "keyframe_block" in CSS_QUERIES
        assert "keyframe_block_list" in CSS_QUERIES
        assert "from" in CSS_QUERIES
        assert "to" in CSS_QUERIES

    def test_name_extraction_queries(self):
        """Test name extraction queries exist"""
        assert "class_name" in CSS_QUERIES
        assert "id_name" in CSS_QUERIES
        assert "tag_name" in CSS_QUERIES


class TestGetCSSQuery:
    """Test get_css_query function"""

    def test_get_css_query_valid(self):
        """Test getting a valid CSS query"""
        query = get_css_query("rule_set")
        assert isinstance(query, str)
        assert len(query) > 0

    def test_get_css_query_all_defined_queries(self):
        """Test getting all defined queries"""
        for query_name in CSS_QUERIES.keys():
            query = get_css_query(query_name)
            assert isinstance(query, str)
            assert len(query) > 0

    def test_get_css_query_invalid(self):
        """Test getting an invalid query raises ValueError"""
        with pytest.raises(ValueError, match="does not exist"):
            get_css_query("nonexistent_query")

    def test_get_css_query_error_message(self):
        """Test error message contains available queries"""
        with pytest.raises(ValueError) as exc_info:
            get_css_query("invalid")
        assert "Available:" in str(exc_info.value)


class TestGetCSSQueryDescription:
    """Test get_css_query_description function"""

    def test_get_css_query_description_valid(self):
        """Test getting a valid query description"""
        description = get_css_query_description("rule_set")
        assert isinstance(description, str)
        assert len(description) > 0

    def test_get_css_query_description_all_queries(self):
        """Test getting descriptions for all queries"""
        for query_name in CSS_QUERIES.keys():
            description = get_css_query_description(query_name)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_get_css_query_description_invalid(self):
        """Test getting description for invalid query"""
        description = get_css_query_description("nonexistent")
        assert description == "No description"


class TestGetQuery:
    """Test get_query function"""

    def test_get_query_valid(self):
        """Test getting a query using get_query"""
        query = get_query("rule_set")
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

    def test_get_all_queries_contains_all_css_queries(self):
        """Test that all CSS_QUERIES are in the result"""
        queries = get_all_queries()
        for query_name in CSS_QUERIES.keys():
            assert query_name in queries

    def test_get_all_queries_contains_legacy_queries(self):
        """Test that legacy queries are included"""
        queries = get_all_queries()
        assert "rules" in queries
        assert "selectors" in queries
        assert "declarations" in queries
        assert "comments" in queries
        assert "at_rules" in queries


class TestListQueries:
    """Test list_queries function"""

    def test_list_queries_returns_list(self):
        """Test list_queries returns a list"""
        queries = list_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_list_queries_contains_all_css_queries(self):
        """Test that all CSS queries are in the list"""
        queries = list_queries()
        for query_name in CSS_QUERIES.keys():
            assert query_name in queries

    def test_list_queries_no_duplicates(self):
        """Test that there are no duplicates in the query list"""
        queries = list_queries()
        assert len(queries) == len(set(queries))


class TestGetAvailableCSSQueries:
    """Test get_available_css_queries function"""

    def test_get_available_css_queries_returns_list(self):
        """Test get_available_css_queries returns a list"""
        queries = get_available_css_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_get_available_css_queries_matches_css_queries(self):
        """Test that available queries match CSS_QUERIES keys"""
        queries = get_available_css_queries()
        assert set(queries) == set(CSS_QUERIES.keys())


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
        assert "rules" in ALL_QUERIES
        assert "selectors" in ALL_QUERIES
        assert "declarations" in ALL_QUERIES
        assert "comments" in ALL_QUERIES
        assert "at_rules" in ALL_QUERIES

    def test_legacy_rules_query(self):
        """Test legacy rules query"""
        query_data = ALL_QUERIES["rules"]
        assert "query" in query_data
        assert "rule" in query_data["query"].lower()

    def test_legacy_selectors_query(self):
        """Test legacy selectors query"""
        query_data = ALL_QUERIES["selectors"]
        assert "query" in query_data
        assert "selector" in query_data["query"].lower()

    def test_legacy_declarations_query(self):
        """Test legacy declarations query"""
        query_data = ALL_QUERIES["declarations"]
        assert "query" in query_data
        assert "declaration" in query_data["query"].lower()

    def test_legacy_comments_query(self):
        """Test legacy comments query"""
        query_data = ALL_QUERIES["comments"]
        assert "query" in query_data
        assert "comment" in query_data["query"].lower()

    def test_legacy_at_rules_query(self):
        """Test legacy at_rules query"""
        query_data = ALL_QUERIES["at_rules"]
        assert "query" in query_data
        assert "at_rule" in query_data["query"].lower()


class TestQueryConsistency:
    """Test consistency between different query dictionaries"""

    def test_css_queries_count(self):
        """Test that we have a substantial number of queries"""
        assert len(CSS_QUERIES) >= 80  # Should have at least 80 queries

    def test_all_queries_count(self):
        """Test ALL_QUERIES includes all CSS queries plus legacy"""
        # ALL_QUERIES should have all CSS_QUERIES plus legacy queries
        assert len(ALL_QUERIES) >= len(CSS_QUERIES)

    def test_descriptions_match_queries(self):
        """Test that every query in CSS_QUERIES has a description"""
        for query_name in CSS_QUERIES.keys():
            assert query_name in CSS_QUERY_DESCRIPTIONS


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_query_name(self):
        """Test empty query name"""
        with pytest.raises(ValueError):
            get_css_query("")

    def test_none_query_name(self):
        """Test None query name"""
        with pytest.raises((ValueError, TypeError)):
            get_css_query(None)  # type: ignore

    def test_query_strings_are_tree_sitter_compatible(self):
        """Test that query strings appear to be valid Tree-sitter syntax"""
        for query_name, query_string in CSS_QUERIES.items():
            # Basic validation: should contain @ for captures
            assert "@" in query_string, f"Query '{query_name}' missing capture syntax"

    def test_query_descriptions_not_empty(self):
        """Test that no query description is empty"""
        for _query_name, description in CSS_QUERY_DESCRIPTIONS.items():
            assert description.strip() != ""
            assert description != "No description"


class TestSpecificQueries:
    """Test specific query patterns"""

    def test_rule_set_query_pattern(self):
        """Test rule_set query has expected pattern"""
        query = get_css_query("rule_set")
        assert "(rule_set)" in query
        assert "@rule_set" in query

    def test_declaration_query_pattern(self):
        """Test declaration query has expected pattern"""
        query = get_css_query("declaration")
        assert "(declaration" in query
        assert "property" in query
        assert "value" in query

    def test_class_selector_query_pattern(self):
        """Test class selector query"""
        query = get_css_query("class_selector")
        assert "(class_selector)" in query
        assert "@class_selector" in query

    def test_id_selector_query_pattern(self):
        """Test id selector query"""
        query = get_css_query("id_selector")
        assert "(id_selector)" in query
        assert "@id_selector" in query

    def test_media_statement_query_pattern(self):
        """Test media statement query"""
        query = get_css_query("media_statement")
        assert "(media_statement)" in query
        assert "@media_statement" in query

    def test_url_function_query_pattern(self):
        """Test url() function query"""
        query = get_css_query("url")
        assert "#match?" in query
        assert "url" in query

    def test_calc_function_query_pattern(self):
        """Test calc() function query"""
        query = get_css_query("calc")
        assert "#match?" in query
        assert "calc" in query

    def test_var_function_query_pattern(self):
        """Test var() function query"""
        query = get_css_query("var")
        assert "#match?" in query
        assert "var" in query

    def test_custom_property_query_pattern(self):
        """Test custom property (CSS variable) query"""
        query = get_css_query("custom_property")
        assert "#match?" in query
        assert "--" in query

    def test_important_query_pattern(self):
        """Test !important query"""
        query = get_css_query("important")
        assert "!" in query
        assert "important" in query


class TestPropertyQueries:
    """Test specific property queries"""

    def test_display_property_query(self):
        """Test display property query"""
        query = get_css_query("display")
        assert "display" in query
        assert "#match?" in query

    def test_position_property_query(self):
        """Test position property query"""
        query = get_css_query("position")
        assert "position" in query
        assert "#match?" in query

    def test_flex_property_query(self):
        """Test flex property query"""
        query = get_css_query("flex")
        assert "flex" in query
        assert "#match?" in query

    def test_grid_property_query(self):
        """Test grid property query"""
        query = get_css_query("grid")
        assert "grid" in query
        assert "#match?" in query

    def test_animation_property_query(self):
        """Test animation property query"""
        query = get_css_query("animation")
        assert "animation" in query
        assert "#match?" in query

    def test_transform_property_query(self):
        """Test transform property query"""
        query = get_css_query("transform")
        assert "transform" in query
        assert "#match?" in query


class TestColorFunctionQueries:
    """Test color function queries"""

    def test_rgb_function_query(self):
        """Test rgb() function query"""
        query = get_css_query("rgb")
        assert "rgb" in query
        assert "#match?" in query

    def test_rgba_function_query(self):
        """Test rgba() function query"""
        query = get_css_query("rgba")
        assert "rgba" in query
        assert "#match?" in query

    def test_hsl_function_query(self):
        """Test hsl() function query"""
        query = get_css_query("hsl")
        assert "hsl" in query
        assert "#match?" in query

    def test_hsla_function_query(self):
        """Test hsla() function query"""
        query = get_css_query("hsla")
        assert "hsla" in query
        assert "#match?" in query
