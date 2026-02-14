"""
Shared fixtures for queries tests.

Provides common utilities for testing tree-sitter queries across different languages.
Compatible with tree-sitter 0.25+ API (QueryCursor-based).
"""

import pytest
import tree_sitter


def get_language(capsule):
    """Wrap a PyCapsule in tree_sitter.Language if needed."""
    if isinstance(capsule, tree_sitter.Language):
        return capsule
    return tree_sitter.Language(capsule)


def make_parser(lang):
    """Create a Parser for a given Language object."""
    parser = tree_sitter.Parser()
    parser.language = lang
    return parser


def compile_query(lang, query_string):
    """Compile a query string for the given language."""
    return tree_sitter.Query(lang, query_string)


def execute_query(lang, code, query_string):
    """
    Parse *code* with *lang* and run *query_string*, returning
    a list of ``(node, capture_name)`` tuples.
    """
    parser = make_parser(lang)
    tree = parser.parse(code.encode("utf-8"))
    query = compile_query(lang, query_string)

    results = []
    if hasattr(tree_sitter, "QueryCursor"):
        cursor = tree_sitter.QueryCursor(query)
        for _pattern_idx, captures_dict in cursor.matches(tree.root_node):
            for capture_name, nodes in captures_dict.items():
                for node in nodes:
                    results.append((node, capture_name))
    else:
        for _pattern_idx, captures_dict in query.matches(tree.root_node):
            for capture_name, nodes in captures_dict.items():
                for node in nodes:
                    results.append((node, capture_name))
    return results


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def query_validator():
    """Return a helper that validates a query compiles successfully."""

    def _validate(lang, query_string):
        try:
            compile_query(lang, query_string)
            return True
        except Exception as exc:
            pytest.fail(f"Query compilation failed: {exc}")

    return _validate


@pytest.fixture
def query_executor():
    """Return a helper that executes a query and returns ``(node, name)`` pairs."""
    return execute_query


@pytest.fixture
def assert_query_finds_nodes():
    """Return an assertion helper for query results."""

    def _assert(results, min_count=1):
        assert (
            len(results) >= min_count
        ), f"Expected at least {min_count} matches, got {len(results)}"

    return _assert
