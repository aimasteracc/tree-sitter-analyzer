#!/usr/bin/env python3
"""
Tests for C++ queries module
"""

import pytest

from tree_sitter_analyzer.queries.cpp import (
    ALL_QUERIES,
    CPP_QUERIES,
    CPP_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_cpp_queries,
    get_cpp_query,
    get_cpp_query_description,
    get_query,
    list_queries,
)


class TestCppQueries:
    """Test C++ queries functionality"""

    def test_get_cpp_query_valid(self) -> None:
        """Test getting a valid C++ query"""
        query = get_cpp_query("class")
        assert query is not None
        assert "class_specifier" in query
        assert "@class" in query

    def test_get_cpp_query_invalid(self) -> None:
        """Test getting an invalid C++ query raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            get_cpp_query("nonexistent_query")

        assert "C++ query 'nonexistent_query' does not exist" in str(exc_info.value)
        assert "Available:" in str(exc_info.value)

    def test_get_cpp_query_description_valid(self) -> None:
        """Test getting description for valid query"""
        description = get_cpp_query_description("class")
        assert description == "Extract C++ class declarations"

    def test_get_cpp_query_description_invalid(self) -> None:
        """Test getting description for invalid query returns default"""
        description = get_cpp_query_description("nonexistent_query")
        assert description == "No description"

    def test_get_query_valid(self) -> None:
        """Test getting query through ALL_QUERIES interface"""
        query = get_query("class")
        assert query is not None
        assert "class_specifier" in query

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
        assert len(all_queries) > 0
        assert "class" in all_queries
        assert "query" in all_queries["class"]
        assert "description" in all_queries["class"]

    def test_list_queries(self) -> None:
        """Test listing all query names"""
        query_names = list_queries()
        assert isinstance(query_names, list)
        assert len(query_names) > 0
        assert "class" in query_names
        assert "function" in query_names

    def test_get_available_cpp_queries(self) -> None:
        """Test getting available C++ queries"""
        available_queries = get_available_cpp_queries()
        assert isinstance(available_queries, list)
        assert len(available_queries) > 0
        assert "class" in available_queries
        assert "function" in available_queries

    def test_cpp_queries_structure(self) -> None:
        """Test CPP_QUERIES dictionary structure"""
        assert isinstance(CPP_QUERIES, dict)
        assert len(CPP_QUERIES) > 0

        essential_queries = [
            "class",
            "struct",
            "enum",
            "function",
            "namespace",
            "template",
            "include",
            "variable",
        ]
        for query_name in essential_queries:
            assert query_name in CPP_QUERIES
            assert isinstance(CPP_QUERIES[query_name], str)
            assert len(CPP_QUERIES[query_name].strip()) > 0

    def test_cpp_query_descriptions_structure(self) -> None:
        """Test CPP_QUERY_DESCRIPTIONS dictionary structure"""
        assert isinstance(CPP_QUERY_DESCRIPTIONS, dict)
        assert len(CPP_QUERY_DESCRIPTIONS) > 0

        essential_queries = ["class", "function", "namespace", "template"]
        for query_name in essential_queries:
            assert query_name in CPP_QUERY_DESCRIPTIONS
            assert isinstance(CPP_QUERY_DESCRIPTIONS[query_name], str)
            assert len(CPP_QUERY_DESCRIPTIONS[query_name].strip()) > 0

    def test_all_queries_structure(self) -> None:
        """Test ALL_QUERIES dictionary structure"""
        assert isinstance(ALL_QUERIES, dict)
        assert len(ALL_QUERIES) > 0

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
        assert ALL_QUERIES["functions"]["query"] == CPP_QUERIES["function"]

        # Test methods alias
        assert "methods" in ALL_QUERIES
        assert ALL_QUERIES["methods"]["query"] == CPP_QUERIES["method"]

        # Test classes alias
        assert "classes" in ALL_QUERIES
        assert ALL_QUERIES["classes"]["query"] == CPP_QUERIES["class"]

        # Test imports alias
        assert "imports" in ALL_QUERIES
        assert ALL_QUERIES["imports"]["query"] == CPP_QUERIES["include"]

        # Test variables alias
        assert "variables" in ALL_QUERIES
        assert ALL_QUERIES["variables"]["query"] == CPP_QUERIES["variable"]

    def test_query_consistency(self) -> None:
        """Test consistency between CPP_QUERIES and ALL_QUERIES"""
        for query_name in CPP_QUERIES:
            assert query_name in ALL_QUERIES
            assert ALL_QUERIES[query_name]["query"] == CPP_QUERIES[query_name]

        for query_name in CPP_QUERY_DESCRIPTIONS:
            assert query_name in CPP_QUERIES

    def test_template_queries(self) -> None:
        """Test C++ template-specific queries"""
        assert "template" in CPP_QUERIES
        assert "template_declaration" in CPP_QUERIES["template"]

        assert "template_function" in CPP_QUERIES
        assert "function_definition" in CPP_QUERIES["template_function"]

        assert "template_class" in CPP_QUERIES
        assert "class_specifier" in CPP_QUERIES["template_class"]

        assert "template_parameter" in CPP_QUERIES
        assert "type_parameter_declaration" in CPP_QUERIES["template_parameter"]

    def test_namespace_queries(self) -> None:
        """Test C++ namespace-specific queries"""
        assert "namespace" in CPP_QUERIES
        assert "namespace_definition" in CPP_QUERIES["namespace"]

        assert "namespace_name" in CPP_QUERIES
        assert "@namespace_name" in CPP_QUERIES["namespace_name"]

        assert "using_declaration" in CPP_QUERIES
        assert "using_declaration" in CPP_QUERIES["using_declaration"]

        assert "using_directive" in CPP_QUERIES
        assert "using_directive" in CPP_QUERIES["using_directive"]

    def test_access_specifier_queries(self) -> None:
        """Test C++ access specifier queries"""
        assert "public_access" in CPP_QUERIES
        assert "#eq?" in CPP_QUERIES["public_access"]
        assert "public:" in CPP_QUERIES["public_access"]

        assert "private_access" in CPP_QUERIES
        assert "private:" in CPP_QUERIES["private_access"]

        assert "protected_access" in CPP_QUERIES
        assert "protected:" in CPP_QUERIES["protected_access"]

    def test_inheritance_queries(self) -> None:
        """Test C++ inheritance queries"""
        assert "base_class" in CPP_QUERIES
        assert "base_class_clause" in CPP_QUERIES["base_class"]

        assert "public_inheritance" in CPP_QUERIES
        assert "public" in CPP_QUERIES["public_inheritance"]

    def test_modern_cpp_queries(self) -> None:
        """Test modern C++ feature queries"""
        # Smart pointers
        assert "smart_pointer" in CPP_QUERIES
        assert "unique_ptr" in CPP_QUERIES["smart_pointer"]
        assert "shared_ptr" in CPP_QUERIES["smart_pointer"]

        # Auto type
        assert "auto_type" in CPP_QUERIES
        assert "auto" in CPP_QUERIES["auto_type"]

        # Lambda
        assert "lambda" in CPP_QUERIES
        assert "lambda_expression" in CPP_QUERIES["lambda"]

        # Range-for
        assert "range_for" in CPP_QUERIES
        assert "for_range_loop" in CPP_QUERIES["range_for"]

    def test_exception_handling_queries(self) -> None:
        """Test C++ exception handling queries"""
        assert "try_catch" in CPP_QUERIES
        assert "try_statement" in CPP_QUERIES["try_catch"]

        assert "catch_clause" in CPP_QUERIES
        assert "catch_clause" in CPP_QUERIES["catch_clause"]

        assert "throw_statement" in CPP_QUERIES
        assert "throw_statement" in CPP_QUERIES["throw_statement"]

    def test_operator_friend_queries(self) -> None:
        """Test C++ operator overloading and friend queries"""
        assert "operator_overload" in CPP_QUERIES
        assert "operator_name" in CPP_QUERIES["operator_overload"]
        assert "@operator_name" in CPP_QUERIES["operator_overload"]

        assert "friend" in CPP_QUERIES
        assert "friend_declaration" in CPP_QUERIES["friend"]

    def test_virtual_destructor_constructor_queries(self) -> None:
        """Test C++ virtual, destructor, constructor queries"""
        assert "virtual_function" in CPP_QUERIES
        assert "virtual" in CPP_QUERIES["virtual_function"]

        assert "constructor" in CPP_QUERIES
        assert "@ctor.name" in CPP_QUERIES["constructor"]

        assert "destructor" in CPP_QUERIES
        assert "destructor_name" in CPP_QUERIES["destructor"]
        assert "@dtor.name" in CPP_QUERIES["destructor"]

    def test_name_extraction_queries(self) -> None:
        """Test C++ name-only extraction queries"""
        assert "class_name" in CPP_QUERIES
        assert "@class_name" in CPP_QUERIES["class_name"]

        assert "function_name" in CPP_QUERIES
        assert "@function_name" in CPP_QUERIES["function_name"]

        assert "field_name" in CPP_QUERIES
        assert "@field_name" in CPP_QUERIES["field_name"]
