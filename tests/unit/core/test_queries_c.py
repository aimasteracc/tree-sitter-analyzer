#!/usr/bin/env python3
"""
Tests for C queries module
"""

import pytest

from tree_sitter_analyzer.queries.c import (
    ALL_QUERIES,
    C_QUERIES,
    C_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_c_queries,
    get_c_query,
    get_c_query_description,
    get_query,
    list_queries,
)


class TestCQueries:
    """Test C queries functionality"""

    def test_get_c_query_valid(self) -> None:
        """Test getting a valid C query"""
        query = get_c_query("function")
        assert query is not None
        assert "function_definition" in query
        assert "@function" in query

    def test_get_c_query_invalid(self) -> None:
        """Test getting an invalid C query raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            get_c_query("nonexistent_query")

        assert "C query 'nonexistent_query' does not exist" in str(exc_info.value)
        assert "Available:" in str(exc_info.value)

    def test_get_c_query_description_valid(self) -> None:
        """Test getting description for valid query"""
        description = get_c_query_description("function")
        assert description == "Extract C function definitions"

    def test_get_c_query_description_invalid(self) -> None:
        """Test getting description for invalid query returns default"""
        description = get_c_query_description("nonexistent_query")
        assert description == "No description"

    def test_get_query_valid(self) -> None:
        """Test getting query through ALL_QUERIES interface"""
        query = get_query("function")
        assert query is not None
        assert "function_definition" in query

    def test_get_query_invalid(self) -> None:
        """Test getting invalid query through ALL_QUERIES interface"""
        with pytest.raises(ValueError) as exc_info:
            get_query("nonexistent_query")

        assert "Query 'nonexistent_query' not found" in str(exc_info.value)
        assert "Available queries:" in str(exc_info.value)

    def test_get_all_queries(self) -> None:
        """Test getting all queries"""
        all_queries = get_all_queries()
        assert isinstance(all_queries, dict)
        assert len(all_queries) == 54
        assert "function" in all_queries
        assert "query" in all_queries["function"]
        assert "description" in all_queries["function"]

    def test_list_queries(self) -> None:
        """Test listing all query names"""
        query_names = list_queries()
        assert isinstance(query_names, list)
        assert len(query_names) == 54
        assert "function" in query_names
        assert "struct" in query_names

    def test_get_available_c_queries(self) -> None:
        """Test getting available C queries"""
        available_queries = get_available_c_queries()
        assert isinstance(available_queries, list)
        assert len(available_queries) == 49
        assert "function" in available_queries
        assert "struct" in available_queries

    def test_c_queries_structure(self) -> None:
        """Test C_QUERIES dictionary structure"""
        assert isinstance(C_QUERIES, dict)
        assert len(C_QUERIES) == 49

        # Exact stripped lengths (update when query strings change)
        essential_query_lens = {
            "function": 31,
            "struct": 26,
            "enum": 22,
            "variable": 23,
            "include": 26,
            "define": 21,
            "typedef": 26,
            "if_statement": 28,
        }
        for query_name, expected_len in essential_query_lens.items():
            assert query_name in C_QUERIES
            assert isinstance(C_QUERIES[query_name], str)
            assert len(C_QUERIES[query_name].strip()) == expected_len

    def test_c_query_descriptions_structure(self) -> None:
        """Test C_QUERY_DESCRIPTIONS dictionary structure"""
        assert isinstance(C_QUERY_DESCRIPTIONS, dict)
        assert len(C_QUERY_DESCRIPTIONS) == 49

        # Exact stripped lengths (update when descriptions change)
        essential_description_lens = {
            "function": 30,
            "struct": 29,
            "enum": 27,
            "variable": 31,
            "include": 28,
        }
        for query_name, expected_len in essential_description_lens.items():
            assert query_name in C_QUERY_DESCRIPTIONS
            assert isinstance(C_QUERY_DESCRIPTIONS[query_name], str)
            assert len(C_QUERY_DESCRIPTIONS[query_name].strip()) == expected_len

    def test_all_queries_structure(self) -> None:
        """Test ALL_QUERIES dictionary structure"""
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) == 54

        for query_data in ALL_QUERIES.values():
            assert isinstance(query_data, dict)
            assert "query" in query_data
            assert "description" in query_data
            assert isinstance(query_data["query"], str)
            assert isinstance(query_data["description"], str)

    def test_query_aliases(self) -> None:
        """Test that query aliases work correctly"""
        # Test functions alias
        assert "functions" in ALL_QUERIES
        functions_query = ALL_QUERIES["functions"]["query"]
        function_query = C_QUERIES["function"]
        assert functions_query == function_query

        # Test classes alias
        assert "classes" in ALL_QUERIES
        classes_query = ALL_QUERIES["classes"]["query"]
        struct_query = C_QUERIES["struct"]
        assert classes_query == struct_query

        # Test imports alias
        assert "imports" in ALL_QUERIES
        imports_query = ALL_QUERIES["imports"]["query"]
        include_query = C_QUERIES["include"]
        assert imports_query == include_query

        # Test variables alias
        assert "variables" in ALL_QUERIES
        variables_query = ALL_QUERIES["variables"]["query"]
        variable_query = C_QUERIES["variable"]
        assert variables_query == variable_query

    def test_query_consistency(self) -> None:
        """Test consistency between C_QUERIES and ALL_QUERIES"""
        # All C_QUERIES should be in ALL_QUERIES
        for query_name in C_QUERIES:
            assert query_name in ALL_QUERIES
            assert ALL_QUERIES[query_name]["query"] == C_QUERIES[query_name]

        # All queries in C_QUERY_DESCRIPTIONS should have corresponding queries
        for query_name in C_QUERY_DESCRIPTIONS:
            assert query_name in C_QUERIES

    def test_specific_c_queries(self) -> None:
        """Test specific C query patterns"""
        # Static function
        assert "static_function" in C_QUERIES
        assert "#eq?" in C_QUERIES["static_function"]
        assert "static" in C_QUERIES["static_function"]

        # Preprocessor directives
        assert "include" in C_QUERIES
        assert "preproc_include" in C_QUERIES["include"]

        assert "define" in C_QUERIES
        assert "preproc_def" in C_QUERIES["define"]

        assert "ifdef" in C_QUERIES
        assert "preproc_ifdef" in C_QUERIES["ifdef"]

        # Control flow
        assert "if_statement" in C_QUERIES
        assert "if_statement" in C_QUERIES["if_statement"]

        assert "for_statement" in C_QUERIES
        assert "for_statement" in C_QUERIES["for_statement"]

        assert "while_statement" in C_QUERIES
        assert "while_statement" in C_QUERIES["while_statement"]

        assert "switch_statement" in C_QUERIES
        assert "switch_statement" in C_QUERIES["switch_statement"]

        assert "goto_statement" in C_QUERIES
        assert "goto_statement" in C_QUERIES["goto_statement"]

    def test_pointer_and_array_types(self) -> None:
        """Test pointer and array type queries"""
        assert "pointer_type" in C_QUERIES
        assert "pointer_declarator" in C_QUERIES["pointer_type"]

        assert "array_type" in C_QUERIES
        assert "array_declarator" in C_QUERIES["array_type"]

    def test_string_and_comment_queries(self) -> None:
        """Test string literal and comment queries"""
        assert "string_literal" in C_QUERIES
        assert "string_literal" in C_QUERIES["string_literal"]

        assert "comment" in C_QUERIES
        assert "comment" in C_QUERIES["comment"]

        assert "block_comment" in C_QUERIES
        assert "#match?" in C_QUERIES["block_comment"]

        assert "line_comment" in C_QUERIES
        assert "#match?" in C_QUERIES["line_comment"]

    def test_function_call_queries(self) -> None:
        """Test function call queries"""
        assert "function_call" in C_QUERIES
        assert "call_expression" in C_QUERIES["function_call"]

        assert "function_call_name" in C_QUERIES
        assert "identifier" in C_QUERIES["function_call_name"]
        assert "@function_call_name" in C_QUERIES["function_call_name"]

    def test_sizeof_and_cast_queries(self) -> None:
        """Test sizeof and cast expression queries"""
        assert "sizeof" in C_QUERIES
        assert "sizeof_expression" in C_QUERIES["sizeof"]

        assert "cast" in C_QUERIES
        assert "cast_expression" in C_QUERIES["cast"]
