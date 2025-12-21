#!/usr/bin/env python3
"""
Tests for TypeScript Tree-sitter queries.

This module tests the TypeScript query definitions and their functionality
for extracting various TypeScript language constructs.
"""

import pytest

from tree_sitter_analyzer.queries import typescript as ts_queries


class TestTypeScriptQueries:
    """Test cases for TypeScript query definitions"""

    def test_functions_query_exists(self):
        """Test that FUNCTIONS query is defined"""
        assert hasattr(ts_queries, "FUNCTIONS")
        assert isinstance(ts_queries.FUNCTIONS, str)
        assert len(ts_queries.FUNCTIONS.strip()) > 0

    def test_classes_query_exists(self):
        """Test that CLASSES query is defined"""
        assert hasattr(ts_queries, "CLASSES")
        assert isinstance(ts_queries.CLASSES, str)
        assert len(ts_queries.CLASSES.strip()) > 0

    def test_interfaces_query_exists(self):
        """Test that INTERFACES query is defined"""
        assert hasattr(ts_queries, "INTERFACES")
        assert isinstance(ts_queries.INTERFACES, str)
        assert len(ts_queries.INTERFACES.strip()) > 0

    def test_type_aliases_query_exists(self):
        """Test that TYPE_ALIASES query is defined"""
        assert hasattr(ts_queries, "TYPE_ALIASES")
        assert isinstance(ts_queries.TYPE_ALIASES, str)
        assert len(ts_queries.TYPE_ALIASES.strip()) > 0

    def test_enums_query_exists(self):
        """Test that ENUMS query is defined"""
        assert hasattr(ts_queries, "ENUMS")
        assert isinstance(ts_queries.ENUMS, str)
        assert len(ts_queries.ENUMS.strip()) > 0

    def test_variables_query_exists(self):
        """Test that VARIABLES query is defined"""
        assert hasattr(ts_queries, "VARIABLES")
        assert isinstance(ts_queries.VARIABLES, str)
        assert len(ts_queries.VARIABLES.strip()) > 0

    def test_imports_query_exists(self):
        """Test that IMPORTS query is defined"""
        assert hasattr(ts_queries, "IMPORTS")
        assert isinstance(ts_queries.IMPORTS, str)
        assert len(ts_queries.IMPORTS.strip()) > 0

    def test_exports_query_exists(self):
        """Test that EXPORTS query is defined"""
        assert hasattr(ts_queries, "EXPORTS")
        assert isinstance(ts_queries.EXPORTS, str)
        assert len(ts_queries.EXPORTS.strip()) > 0

    def test_decorators_query_exists(self):
        """Test that DECORATORS query is defined"""
        assert hasattr(ts_queries, "DECORATORS")
        assert isinstance(ts_queries.DECORATORS, str)
        assert len(ts_queries.DECORATORS.strip()) > 0

    def test_generics_query_exists(self):
        """Test that GENERICS query is defined"""
        assert hasattr(ts_queries, "GENERICS")
        assert isinstance(ts_queries.GENERICS, str)
        assert len(ts_queries.GENERICS.strip()) > 0

    def test_signatures_query_exists(self):
        """Test that SIGNATURES query is defined"""
        assert hasattr(ts_queries, "SIGNATURES")
        assert isinstance(ts_queries.SIGNATURES, str)
        assert len(ts_queries.SIGNATURES.strip()) > 0

    def test_comments_query_exists(self):
        """Test that COMMENTS query is defined"""
        assert hasattr(ts_queries, "COMMENTS")
        assert isinstance(ts_queries.COMMENTS, str)
        assert len(ts_queries.COMMENTS.strip()) > 0

    def test_all_queries_dict_exists(self):
        """Test that ALL_QUERIES dictionary is defined"""
        assert hasattr(ts_queries, "ALL_QUERIES")
        assert isinstance(ts_queries.ALL_QUERIES, dict)
        assert len(ts_queries.ALL_QUERIES) > 0

    def test_all_queries_structure(self):
        """Test the structure of ALL_QUERIES dictionary"""
        queries = ts_queries.ALL_QUERIES

        # Check that each query has required keys
        for query_name, query_data in queries.items():
            assert isinstance(query_name, str)
            assert isinstance(query_data, dict)
            assert "query" in query_data
            assert "description" in query_data
            assert isinstance(query_data["query"], str)
            assert isinstance(query_data["description"], str)
            assert len(query_data["query"].strip()) > 0
            assert len(query_data["description"].strip()) > 0

    def test_expected_queries_present(self):
        """Test that expected TypeScript queries are present"""
        expected_queries = [
            "functions",
            "classes",
            "interfaces",
            "type_aliases",
            "enums",
            "variables",
            "imports",
            "exports",
            "decorators",
            "generics",
            "signatures",
            "comments",
        ]

        queries = ts_queries.ALL_QUERIES
        for expected_query in expected_queries:
            assert (
                expected_query in queries
            ), f"Query '{expected_query}' not found in ALL_QUERIES"

    def test_functions_query_patterns(self):
        """Test that FUNCTIONS query contains expected patterns"""
        functions_query = ts_queries.FUNCTIONS

        # Should contain function declaration patterns
        assert "function_declaration" in functions_query
        assert "function_expression" in functions_query
        assert "arrow_function" in functions_query
        assert "method_definition" in functions_query

        # Should contain capture groups
        assert "@function.name" in functions_query
        assert "@function.params" in functions_query
        assert "@function.body" in functions_query

    def test_classes_query_patterns(self):
        """Test that CLASSES query contains expected patterns"""
        classes_query = ts_queries.CLASSES

        # Should contain class patterns
        assert "class_declaration" in classes_query
        assert "abstract_class_declaration" in classes_query

        # Should contain capture groups
        assert "@class.name" in classes_query
        assert "@class.body" in classes_query

    def test_interfaces_query_patterns(self):
        """Test that INTERFACES query contains expected patterns"""
        interfaces_query = ts_queries.INTERFACES

        # Should contain interface patterns
        assert "interface_declaration" in interfaces_query

        # Should contain capture groups
        assert "@interface.name" in interfaces_query
        assert "@interface.body" in interfaces_query

    def test_type_aliases_query_patterns(self):
        """Test that TYPE_ALIASES query contains expected patterns"""
        type_aliases_query = ts_queries.TYPE_ALIASES

        # Should contain type alias patterns
        assert "type_alias_declaration" in type_aliases_query

        # Should contain capture groups
        assert "@type.name" in type_aliases_query
        assert "@type.value" in type_aliases_query

    def test_enums_query_patterns(self):
        """Test that ENUMS query contains expected patterns"""
        enums_query = ts_queries.ENUMS

        # Should contain enum patterns
        assert "enum_declaration" in enums_query

        # Should contain capture groups
        assert "@enum.name" in enums_query
        assert "@enum.body" in enums_query

    def test_variables_query_patterns(self):
        """Test that VARIABLES query contains expected patterns"""
        variables_query = ts_queries.VARIABLES

        # Should contain variable patterns
        assert "variable_declaration" in variables_query
        assert "lexical_declaration" in variables_query

        # Should contain capture groups
        assert "@variable.name" in variables_query
        assert "@variable.type" in variables_query

    def test_imports_query_patterns(self):
        """Test that IMPORTS query contains expected patterns"""
        imports_query = ts_queries.IMPORTS

        # Should contain import patterns
        assert "import_statement" in imports_query

        # Should contain capture groups
        assert "@import.source" in imports_query
        assert "@import.name" in imports_query

    def test_exports_query_patterns(self):
        """Test that EXPORTS query contains expected patterns"""
        exports_query = ts_queries.EXPORTS

        # Should contain export patterns
        assert "export_statement" in exports_query

        # Should contain capture groups
        assert "@export.declaration" in exports_query

    def test_decorators_query_patterns(self):
        """Test that DECORATORS query contains expected patterns"""
        decorators_query = ts_queries.DECORATORS

        # Should contain decorator patterns
        assert "decorator" in decorators_query

        # Should contain capture groups
        assert "@decorator.name" in decorators_query

    def test_generics_query_patterns(self):
        """Test that GENERICS query contains expected patterns"""
        generics_query = ts_queries.GENERICS

        # Should contain generic patterns
        assert "type_parameters" in generics_query
        assert "type_parameter" in generics_query

        # Should contain capture groups
        assert "@generic.name" in generics_query

    def test_signatures_query_patterns(self):
        """Test that SIGNATURES query contains expected patterns"""
        signatures_query = ts_queries.SIGNATURES

        # Should contain signature patterns
        assert "property_signature" in signatures_query
        assert "method_signature" in signatures_query

        # Should contain capture groups
        assert "@property.name" in signatures_query
        assert "@method.name" in signatures_query

    def test_get_query_function(self):
        """Test the get_query function"""
        assert hasattr(ts_queries, "get_query")
        assert callable(ts_queries.get_query)

        # Test getting existing query
        functions_query = ts_queries.get_query("functions")
        assert isinstance(functions_query, str)
        assert functions_query == ts_queries.FUNCTIONS

        # Test getting non-existent query
        with pytest.raises(ValueError):
            ts_queries.get_query("nonexistent_query")

    def test_get_all_queries_function(self):
        """Test the get_all_queries function"""
        assert hasattr(ts_queries, "get_all_queries")
        assert callable(ts_queries.get_all_queries)

        all_queries = ts_queries.get_all_queries()
        assert isinstance(all_queries, dict)
        assert all_queries == ts_queries.ALL_QUERIES

    def test_list_queries_function(self):
        """Test the list_queries function"""
        assert hasattr(ts_queries, "list_queries")
        assert callable(ts_queries.list_queries)

        query_names = ts_queries.list_queries()
        assert isinstance(query_names, list)
        assert len(query_names) > 0

        # Should match keys in ALL_QUERIES
        expected_names = list(ts_queries.ALL_QUERIES.keys())
        assert set(query_names) == set(expected_names)

    def test_query_syntax_validity(self):
        """Test that queries have valid Tree-sitter syntax"""
        queries = ts_queries.ALL_QUERIES

        for query_name, query_data in queries.items():
            query_string = query_data["query"]

            # Basic syntax checks
            assert query_string.count("(") == query_string.count(
                ")"
            ), f"Unbalanced parentheses in {query_name} query"
            assert query_string.count("[") == query_string.count(
                "]"
            ), f"Unbalanced brackets in {query_name} query"
            assert query_string.count("{") == query_string.count(
                "}"
            ), f"Unbalanced braces in {query_name} query"

            # Should contain capture groups (indicated by @)
            assert "@" in query_string, f"No capture groups found in {query_name} query"

    def test_typescript_specific_features(self):
        """Test that TypeScript-specific features are covered in queries"""
        all_queries_text = " ".join(
            [q["query"] for q in ts_queries.ALL_QUERIES.values()]
        )

        # TypeScript-specific node types should be present
        typescript_features = [
            "interface_declaration",
            "type_alias_declaration",
            "enum_declaration",
            "type_parameters",
            "type_annotation",
            "abstract_class_declaration",
            "decorator",
            "property_signature",
            "method_signature",
        ]

        for feature in typescript_features:
            assert (
                feature in all_queries_text
            ), f"TypeScript feature '{feature}' not found in queries"

    def test_query_descriptions_quality(self):
        """Test that query descriptions are meaningful"""
        queries = ts_queries.ALL_QUERIES

        for query_name, query_data in queries.items():
            description = query_data["description"]

            # Description should be meaningful
            assert len(description) > 10, f"Description for {query_name} is too short"
            assert not description.lower().startswith(
                "todo"
            ), f"Description for {query_name} appears to be a placeholder"
            assert query_name.replace(
                "_", " "
            ) in description.lower() or query_name.replace(
                "_", ""
            ) in description.lower().replace(
                " ", ""
            ), f"Description for {query_name} doesn't seem to relate to the query name"

    def test_capture_group_consistency(self):
        """Test that capture groups follow consistent naming patterns"""
        queries = ts_queries.ALL_QUERIES

        # Expected capture group patterns
        expected_patterns = {
            "functions": ["@function.", "@method."],
            "classes": ["@class."],
            "interfaces": ["@interface."],
            "type_aliases": ["@type."],
            "enums": ["@enum."],
            "variables": ["@variable."],
            "imports": ["@import."],
            "exports": ["@export."],
            "decorators": ["@decorator."],
            "generics": ["@generic."],
            "signatures": ["@property.", "@method.", "@constructor."],
        }

        for query_name, patterns in expected_patterns.items():
            if query_name in queries:
                query_string = queries[query_name]["query"]
                has_expected_pattern = any(
                    pattern in query_string for pattern in patterns
                )
                assert has_expected_pattern, f"Query {query_name} doesn't contain expected capture group patterns: {patterns}"


if __name__ == "__main__":
    pytest.main([__file__])
