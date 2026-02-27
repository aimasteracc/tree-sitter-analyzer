#!/usr/bin/env python3
"""
Tests for CSS query module.

Tests all query patterns, utility functions, and edge cases.
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
        assert isinstance(CSS_QUERIES, dict)
        assert len(CSS_QUERIES) > 0

    def test_css_query_descriptions_dict_exists(self):
        assert isinstance(CSS_QUERY_DESCRIPTIONS, dict)
        assert len(CSS_QUERY_DESCRIPTIONS) > 0

    def test_all_queries_dict_exists(self):
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) > 0

    def test_all_queries_have_descriptions(self):
        for query_name in CSS_QUERIES.keys():
            assert query_name in CSS_QUERY_DESCRIPTIONS
            assert isinstance(CSS_QUERY_DESCRIPTIONS[query_name], str)
            assert len(CSS_QUERY_DESCRIPTIONS[query_name]) > 0

    def test_all_queries_have_query_string(self):
        for _query_name, query_string in CSS_QUERIES.items():
            assert isinstance(query_string, str)
            assert len(query_string.strip()) > 0

    def test_basic_rule_queries(self):
        for key in ["rule_set", "rule", "declaration", "property", "property_name", "property_value"]:
            assert key in CSS_QUERIES

    def test_selector_queries(self):
        for key in ["selector", "selectors", "class_selector", "id_selector", "tag_selector",
                     "universal_selector", "attribute_selector", "pseudo_class_selector",
                     "pseudo_element_selector", "descendant_selector", "child_selector",
                     "sibling_selector", "adjacent_sibling_selector"]:
            assert key in CSS_QUERIES

    def test_at_rule_queries(self):
        for key in ["at_rule", "import_statement", "media_statement", "charset_statement",
                     "namespace_statement", "keyframes_statement", "supports_statement",
                     "page_statement", "font_face_statement"]:
            assert key in CSS_QUERIES

    def test_media_query_queries(self):
        for key in ["media_query", "media_feature", "media_type"]:
            assert key in CSS_QUERIES

    def test_value_queries(self):
        for key in ["string_value", "integer_value", "float_value", "color_value",
                     "call_expression", "function_name", "arguments"]:
            assert key in CSS_QUERIES

    def test_css_function_queries(self):
        for key in ["url", "calc", "var", "rgb", "rgba", "hsl", "hsla"]:
            assert key in CSS_QUERIES

    def test_unit_queries(self):
        for key in ["dimension", "percentage", "unit"]:
            assert key in CSS_QUERIES

    def test_layout_property_queries(self):
        for key in ["display", "position", "float", "clear", "overflow", "visibility", "z_index"]:
            assert key in CSS_QUERIES

    def test_box_model_queries(self):
        for key in ["width", "height", "margin", "padding", "border", "box_sizing"]:
            assert key in CSS_QUERIES

    def test_typography_queries(self):
        for key in ["font", "color", "text", "line_height", "letter_spacing", "word_spacing"]:
            assert key in CSS_QUERIES

    def test_background_queries(self):
        assert "background" in CSS_QUERIES

    def test_flexbox_queries(self):
        for key in ["flex", "justify_content", "align_items", "align_content"]:
            assert key in CSS_QUERIES

    def test_grid_queries(self):
        assert "grid" in CSS_QUERIES

    def test_animation_queries(self):
        for key in ["animation", "transition", "transform"]:
            assert key in CSS_QUERIES

    def test_comment_queries(self):
        assert "comment" in CSS_QUERIES

    def test_custom_property_queries(self):
        assert "custom_property" in CSS_QUERIES

    def test_important_queries(self):
        assert "important" in CSS_QUERIES

    def test_keyframe_queries(self):
        for key in ["keyframe_block", "keyframe_block_list", "from", "to"]:
            assert key in CSS_QUERIES

    def test_name_extraction_queries(self):
        for key in ["class_name", "id_name", "tag_name"]:
            assert key in CSS_QUERIES


class TestGetCSSQuery:
    """Test get_css_query function"""

    def test_get_css_query_valid(self):
        query = get_css_query("rule_set")
        assert isinstance(query, str)
        assert len(query) > 0

    def test_get_css_query_all_defined_queries(self):
        for query_name in CSS_QUERIES.keys():
            query = get_css_query(query_name)
            assert isinstance(query, str)
            assert len(query) > 0

    def test_get_css_query_invalid(self):
        with pytest.raises(ValueError, match="does not exist"):
            get_css_query("nonexistent_query")

    def test_get_css_query_error_message(self):
        with pytest.raises(ValueError) as exc_info:
            get_css_query("invalid")
        assert "Available:" in str(exc_info.value)


class TestGetCSSQueryDescription:
    """Test get_css_query_description function"""

    def test_get_css_query_description_valid(self):
        description = get_css_query_description("rule_set")
        assert isinstance(description, str)
        assert len(description) > 0

    def test_get_css_query_description_all_queries(self):
        for query_name in CSS_QUERIES.keys():
            description = get_css_query_description(query_name)
            assert isinstance(description, str)
            assert len(description) > 0

    def test_get_css_query_description_invalid(self):
        description = get_css_query_description("nonexistent")
        assert description == "No description"


class TestGetQuery:
    """Test get_query function"""

    def test_get_query_valid(self):
        query = get_query("rule_set")
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

    def test_get_all_queries_contains_all_css_queries(self):
        queries = get_all_queries()
        for query_name in CSS_QUERIES.keys():
            assert query_name in queries

    def test_get_all_queries_contains_legacy_queries(self):
        queries = get_all_queries()
        for key in ["rules", "selectors", "declarations", "comments", "at_rules"]:
            assert key in queries


class TestListQueries:
    """Test list_queries function"""

    def test_list_queries_returns_list(self):
        queries = list_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_list_queries_contains_all_css_queries(self):
        queries = list_queries()
        for query_name in CSS_QUERIES.keys():
            assert query_name in queries

    def test_list_queries_no_duplicates(self):
        queries = list_queries()
        assert len(queries) == len(set(queries))


class TestGetAvailableCSSQueries:
    """Test get_available_css_queries function"""

    def test_get_available_css_queries_returns_list(self):
        queries = get_available_css_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_get_available_css_queries_matches_css_queries(self):
        queries = get_available_css_queries()
        assert set(queries) == set(CSS_QUERIES.keys())


class TestQueryConsistency:
    """Test consistency between different query dictionaries"""

    def test_css_queries_count(self):
        assert len(CSS_QUERIES) >= 80

    def test_all_queries_count(self):
        assert len(ALL_QUERIES) >= len(CSS_QUERIES)

    def test_descriptions_match_queries(self):
        for query_name in CSS_QUERIES.keys():
            assert query_name in CSS_QUERY_DESCRIPTIONS


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_query_name(self):
        with pytest.raises(ValueError):
            get_css_query("")

    def test_none_query_name(self):
        with pytest.raises((ValueError, TypeError)):
            get_css_query(None)  # type: ignore

    def test_query_strings_are_tree_sitter_compatible(self):
        for query_name, query_string in CSS_QUERIES.items():
            assert "@" in query_string, f"Query '{query_name}' missing capture syntax"

    def test_query_descriptions_not_empty(self):
        for _query_name, description in CSS_QUERY_DESCRIPTIONS.items():
            assert description.strip() != ""
            assert description != "No description"


class TestSpecificQueries:
    """Test specific query patterns"""

    def test_rule_set_query_pattern(self):
        query = get_css_query("rule_set")
        assert "(rule_set)" in query
        assert "@rule_set" in query

    def test_declaration_query_pattern(self):
        query = get_css_query("declaration")
        assert "(declaration" in query
        assert "property" in query
        assert "value" in query

    def test_class_selector_query_pattern(self):
        query = get_css_query("class_selector")
        assert "(class_selector)" in query
        assert "@class_selector" in query

    def test_id_selector_query_pattern(self):
        query = get_css_query("id_selector")
        assert "(id_selector)" in query
        assert "@id_selector" in query

    def test_media_statement_query_pattern(self):
        query = get_css_query("media_statement")
        assert "(media_statement)" in query
        assert "@media_statement" in query

    def test_url_function_query_pattern(self):
        query = get_css_query("url")
        assert "#match?" in query
        assert "url" in query

    def test_custom_property_query_pattern(self):
        query = get_css_query("custom_property")
        assert "#match?" in query
        assert "--" in query

    def test_important_query_pattern(self):
        query = get_css_query("important")
        assert "!" in query
        assert "important" in query


class TestPropertyQueries:
    """Test specific property queries"""

    def test_display_property_query(self):
        query = get_css_query("display")
        assert "display" in query
        assert "#match?" in query

    def test_position_property_query(self):
        query = get_css_query("position")
        assert "position" in query
        assert "#match?" in query

    def test_flex_property_query(self):
        query = get_css_query("flex")
        assert "flex" in query
        assert "#match?" in query

    def test_grid_property_query(self):
        query = get_css_query("grid")
        assert "grid" in query
        assert "#match?" in query

    def test_animation_property_query(self):
        query = get_css_query("animation")
        assert "animation" in query
        assert "#match?" in query

    def test_transform_property_query(self):
        query = get_css_query("transform")
        assert "transform" in query
        assert "#match?" in query


class TestColorFunctionQueries:
    """Test color function queries"""

    def test_rgb_function_query(self):
        query = get_css_query("rgb")
        assert "rgb" in query
        assert "#match?" in query

    def test_rgba_function_query(self):
        query = get_css_query("rgba")
        assert "rgba" in query
        assert "#match?" in query

    def test_hsl_function_query(self):
        query = get_css_query("hsl")
        assert "hsl" in query
        assert "#match?" in query

    def test_hsla_function_query(self):
        query = get_css_query("hsla")
        assert "hsla" in query
        assert "#match?" in query
