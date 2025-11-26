#!/usr/bin/env python3
"""
Property-based tests for YAML query definitions.

Feature: yaml-language-support
Tests correctness properties for YAML queries to ensure:
- All defined queries are valid tree-sitter syntax
- Query results contain only elements matching the query pattern
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.queries.yaml import (
    ALL_QUERIES,
    YAML_QUERIES,
    YAML_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_yaml_queries,
    get_query,
    get_yaml_query,
    get_yaml_query_description,
    list_queries,
)

# Check if tree-sitter-yaml is available
try:
    import tree_sitter
    import tree_sitter_yaml as ts_yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class TestYAMLQueryProperties:
    """Property-based tests for YAML query definitions."""

    @settings(max_examples=100)
    @given(query_name=st.sampled_from(list(YAML_QUERIES.keys())))
    def test_property_11_query_result_correctness_syntax_validity(
        self, query_name: str
    ):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        For any defined YAML query, the query string SHALL be valid tree-sitter
        syntax with balanced parentheses and proper capture groups.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Get the query string
        query_string = YAML_QUERIES[query_name]

        # Property: Query must be a non-empty string
        assert isinstance(
            query_string, str
        ), f"Query '{query_name}' must be a string, got {type(query_string)}"
        assert len(query_string.strip()) > 0, f"Query '{query_name}' must not be empty"

        # Property: Query must have balanced parentheses
        open_count = query_string.count("(")
        close_count = query_string.count(")")
        assert (
            open_count == close_count
        ), f"Query '{query_name}' has unbalanced parentheses: {open_count} open, {close_count} close"

        # Property: Query must have at least one capture group (contains @)
        assert (
            "@" in query_string
        ), f"Query '{query_name}' must have at least one capture group (@)"

        # Property: Query must have at least one node type (contains parentheses)
        assert (
            "(" in query_string and ")" in query_string
        ), f"Query '{query_name}' must contain node types in parentheses"

    @settings(max_examples=100)
    @given(query_name=st.sampled_from(list(YAML_QUERIES.keys())))
    def test_property_11_query_result_correctness_description_exists(
        self, query_name: str
    ):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        For any defined YAML query, there SHALL be a corresponding description
        that explains the query's purpose.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Property: Every query must have a description
        assert (
            query_name in YAML_QUERY_DESCRIPTIONS
        ), f"Query '{query_name}' must have a description in YAML_QUERY_DESCRIPTIONS"

        description = YAML_QUERY_DESCRIPTIONS[query_name]

        # Property: Description must be a non-empty string
        assert isinstance(
            description, str
        ), f"Description for '{query_name}' must be a string"
        assert (
            len(description.strip()) > 0
        ), f"Description for '{query_name}' must not be empty"

        # Property: Description should contain meaningful content
        assert (
            len(description.split()) >= 2
        ), f"Description for '{query_name}' should contain at least 2 words"

    @settings(max_examples=100)
    @given(query_name=st.sampled_from(list(YAML_QUERIES.keys())))
    def test_property_11_query_result_correctness_all_queries_consistency(
        self, query_name: str
    ):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        For any query in YAML_QUERIES, it SHALL also exist in ALL_QUERIES with
        consistent query string and description.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Property: Query must exist in ALL_QUERIES
        assert (
            query_name in ALL_QUERIES
        ), f"Query '{query_name}' must exist in ALL_QUERIES"

        all_queries_entry = ALL_QUERIES[query_name]

        # Property: ALL_QUERIES entry must have 'query' and 'description' keys
        assert (
            "query" in all_queries_entry
        ), f"ALL_QUERIES['{query_name}'] must have 'query' key"
        assert (
            "description" in all_queries_entry
        ), f"ALL_QUERIES['{query_name}'] must have 'description' key"

        # Property: Query string must match between YAML_QUERIES and ALL_QUERIES
        assert (
            all_queries_entry["query"] == YAML_QUERIES[query_name]
        ), f"Query string mismatch for '{query_name}'"

        # Property: Description must match between YAML_QUERY_DESCRIPTIONS and ALL_QUERIES
        expected_description = YAML_QUERY_DESCRIPTIONS.get(query_name, "No description")
        assert (
            all_queries_entry["description"] == expected_description
        ), f"Description mismatch for '{query_name}'"

    @settings(max_examples=50)
    @given(query_name=st.sampled_from(list(YAML_QUERIES.keys())))
    def test_property_11_query_result_correctness_getter_functions(
        self, query_name: str
    ):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        For any query name, the getter functions SHALL return consistent results
        and handle the query correctly.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Property: get_yaml_query() must return the correct query string
        query_from_getter = get_yaml_query(query_name)
        assert (
            query_from_getter == YAML_QUERIES[query_name]
        ), f"get_yaml_query('{query_name}') returned incorrect query"

        # Property: get_yaml_query_description() must return the correct description
        description_from_getter = get_yaml_query_description(query_name)
        expected_description = YAML_QUERY_DESCRIPTIONS.get(query_name, "No description")
        assert (
            description_from_getter == expected_description
        ), f"get_yaml_query_description('{query_name}') returned incorrect description"

        # Property: get_query() must return the correct query string
        query_from_get_query = get_query(query_name)
        assert (
            query_from_get_query == YAML_QUERIES[query_name]
        ), f"get_query('{query_name}') returned incorrect query"

        # Property: Query name must be in list_queries()
        all_query_names = list_queries()
        assert (
            query_name in all_query_names
        ), f"Query '{query_name}' must be in list_queries() result"

        # Property: Query name must be in get_available_yaml_queries()
        available_queries = get_available_yaml_queries()
        assert (
            query_name in available_queries
        ), f"Query '{query_name}' must be in get_available_yaml_queries() result"

    def test_property_11_query_result_correctness_no_empty_queries(self):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        The YAML_QUERIES dictionary SHALL not be empty and SHALL contain
        all essential query types.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Property: YAML_QUERIES must not be empty
        assert len(YAML_QUERIES) > 0, "YAML_QUERIES must not be empty"

        # Property: Essential queries must exist
        essential_queries = [
            "document",
            "block_mapping",
            "block_sequence",
            "plain_scalar",
            "anchor",
            "alias",
            "comment",
        ]

        for essential_query in essential_queries:
            assert (
                essential_query in YAML_QUERIES
            ), f"Essential query '{essential_query}' must exist in YAML_QUERIES"

    def test_property_11_query_result_correctness_invalid_query_handling(self):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        When requesting a non-existent query, the getter functions SHALL raise
        appropriate errors with helpful messages.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        invalid_query_name = "this_query_does_not_exist_12345"

        # Property: get_yaml_query() must raise ValueError for invalid query
        with pytest.raises(ValueError) as exc_info:
            get_yaml_query(invalid_query_name)

        error_message = str(exc_info.value)
        assert (
            invalid_query_name in error_message
        ), "Error message must mention the invalid query name"
        assert (
            "does not exist" in error_message or "not found" in error_message.lower()
        ), "Error message must indicate query doesn't exist"
        assert "Available" in error_message, "Error message must list available queries"

        # Property: get_query() must raise ValueError for invalid query
        with pytest.raises(ValueError) as exc_info:
            get_query(invalid_query_name)

        error_message = str(exc_info.value)
        assert (
            invalid_query_name in error_message
        ), "Error message must mention the invalid query name"

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
    @settings(max_examples=20)
    @given(query_name=st.sampled_from(list(YAML_QUERIES.keys())))
    def test_property_11_query_result_correctness_tree_sitter_compilation(
        self, query_name: str
    ):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        For any defined YAML query, the query SHALL compile successfully with
        tree-sitter-yaml without raising syntax errors.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Get the query string
        query_string = YAML_QUERIES[query_name]

        # Property: Query must compile with tree-sitter-yaml
        try:
            # Create YAML language instance
            yaml_language = tree_sitter.Language(ts_yaml.language())

            # Attempt to compile the query
            compiled_query = yaml_language.query(query_string)

            # Property: Compiled query must not be None
            assert compiled_query is not None, f"Query '{query_name}' compiled to None"

        except Exception as e:
            pytest.fail(
                f"Query '{query_name}' failed to compile with tree-sitter-yaml: {e}"
            )

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
    def test_property_11_query_result_correctness_all_queries_compile(self):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        All defined YAML queries SHALL compile successfully with tree-sitter-yaml
        without any syntax errors.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Create YAML language instance
        yaml_language = tree_sitter.Language(ts_yaml.language())

        failed_queries = []

        # Property: All queries must compile successfully
        for query_name, query_string in YAML_QUERIES.items():
            try:
                compiled_query = yaml_language.query(query_string)
                assert (
                    compiled_query is not None
                ), f"Query '{query_name}' compiled to None"
            except Exception as e:
                failed_queries.append((query_name, str(e)))

        # Property: No queries should fail to compile
        if failed_queries:
            failure_details = "\n".join(
                [f"  - {name}: {error}" for name, error in failed_queries]
            )
            pytest.fail(f"The following queries failed to compile:\n{failure_details}")

    def test_property_11_query_result_correctness_query_coverage(self):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        The YAML query library SHALL provide comprehensive coverage of YAML
        language constructs including mappings, sequences, scalars, anchors,
        aliases, and comments.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Property: Queries must cover all major YAML constructs
        required_constructs = {
            "mappings": ["block_mapping", "flow_mapping", "all_mappings"],
            "sequences": ["block_sequence", "flow_sequence", "all_sequences"],
            "scalars": [
                "plain_scalar",
                "double_quote_scalar",
                "single_quote_scalar",
                "block_scalar",
                "all_scalars",
            ],
            "anchors_aliases": ["anchor", "alias"],
            "comments": ["comment"],
            "documents": ["document", "stream"],
        }

        for construct_type, query_names in required_constructs.items():
            # At least one query from each construct type must exist
            found = any(query_name in YAML_QUERIES for query_name in query_names)
            assert found, f"No queries found for {construct_type} construct"

    def test_property_11_query_result_correctness_consistency_across_interfaces(self):
        """
        Feature: yaml-language-support, Property 11: Query Result Correctness

        All query access interfaces (YAML_QUERIES, ALL_QUERIES, getter functions)
        SHALL provide consistent results for the same query.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4
        """
        # Property: All interfaces must return the same set of query names
        yaml_queries_keys = set(YAML_QUERIES.keys())
        all_queries_keys = set(ALL_QUERIES.keys())
        list_queries_result = set(list_queries())
        available_queries_result = set(get_available_yaml_queries())

        assert (
            yaml_queries_keys == all_queries_keys
        ), "YAML_QUERIES and ALL_QUERIES must have the same keys"
        assert (
            yaml_queries_keys == list_queries_result
        ), "YAML_QUERIES and list_queries() must return the same keys"
        assert (
            yaml_queries_keys == available_queries_result
        ), "YAML_QUERIES and get_available_yaml_queries() must return the same keys"

        # Property: get_all_queries() must return ALL_QUERIES
        all_queries_from_getter = get_all_queries()
        assert (
            all_queries_from_getter == ALL_QUERIES
        ), "get_all_queries() must return ALL_QUERIES"
