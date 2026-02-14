"""Tests for Kotlin language queries."""

import pytest

try:
    import tree_sitter_kotlin

    KOTLIN_AVAILABLE = True
except ImportError:
    KOTLIN_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import kotlin as kotlin_queries


def _lang():
    return get_language(tree_sitter_kotlin.language())


SAMPLE_KOTLIN_CODE = """
package com.example

import java.util.List

class Calculator(val name: String) {
    fun add(a: Int, b: Int): Int = a + b
    fun subtract(a: Int, b: Int): Int = a - b
}

interface Shape {
    fun area(): Double
    fun perimeter(): Double
}

data class Point(val x: Double, val y: Double)

enum class Direction {
    NORTH, SOUTH, EAST, WEST
}

fun greet(name: String): String {
    return "Hello, $name"
}

object Singleton {
    val instance = "unique"
}

val MAX_SIZE = 100
var count = 0
"""

# Keys to test individually
KOTLIN_KEYS_TO_TEST = [
    "package",
    "class",
    "function",
    "object",
    "annotation",
]


def _get_query(module, key):
    """Get query string from ALL_QUERIES."""
    all_q = module.ALL_QUERIES
    if key not in all_q:
        return None
    entry = all_q[key]
    return entry["query"] if isinstance(entry, dict) else entry


@pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not available")
class TestKotlinQueriesSyntax:
    """Test that Kotlin queries compile successfully."""

    def test_all_queries_dict_compilable_count(self):
        import tree_sitter

        lang = _lang()
        all_q = kotlin_queries.ALL_QUERIES
        assert len(all_q) > 0
        compiled, failed = 0, 0
        for _name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed)
        assert (
            ratio >= 0.5
        ), f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"

    @pytest.mark.parametrize("key", KOTLIN_KEYS_TO_TEST)
    def test_individual_query_compiles(self, key, query_validator):
        qstr = _get_query(kotlin_queries, key)
        if qstr is None:
            pytest.skip(f"Key {key} not in ALL_QUERIES")
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not available")
class TestKotlinQueriesFunctionality:
    """Test that Kotlin queries return expected results."""

    def test_package_query_finds_package(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_KOTLIN_CODE, _get_query(kotlin_queries, "package")
        )
        assert len(results) >= 1

    def test_class_query_finds_classes(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_KOTLIN_CODE, _get_query(kotlin_queries, "class")
        )
        assert len(results) >= 4  # Calculator, Shape, Point, Direction

    def test_function_query_finds_functions(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_KOTLIN_CODE, _get_query(kotlin_queries, "function")
        )
        assert len(results) >= 5  # add, subtract, area, perimeter, greet

    def test_object_query_finds_objects(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_KOTLIN_CODE, _get_query(kotlin_queries, "object")
        )
        assert len(results) >= 1

    def test_class_query_includes_data_classes(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_KOTLIN_CODE, _get_query(kotlin_queries, "class")
        )
        assert len(results) >= 3


@pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not available")
class TestKotlinQueriesEdgeCases:
    """Test Kotlin queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", _get_query(kotlin_queries, "class"))
        assert len(results) == 0

    def test_comments_only_returns_no_class_matches(self, query_executor):
        code = "// comment only\n"
        results = query_executor(_lang(), code, _get_query(kotlin_queries, "class"))
        assert len(results) == 0

    def test_single_package(self, query_executor):
        code = "package com.example"
        results = query_executor(_lang(), code, _get_query(kotlin_queries, "package"))
        assert len(results) >= 1

    def test_empty_class(self, query_executor):
        code = "class Empty"
        results = query_executor(_lang(), code, _get_query(kotlin_queries, "class"))
        assert len(results) >= 1

    def test_top_level_function(self, query_executor):
        code = "fun main() {}"
        results = query_executor(_lang(), code, _get_query(kotlin_queries, "function"))
        assert len(results) >= 1

    def test_lambda_query(self, query_executor):
        code = "val fn = { x: Int -> x * 2 }"
        results = query_executor(_lang(), code, _get_query(kotlin_queries, "lambda"))
        assert len(results) >= 1


@pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="tree-sitter-kotlin not available")
class TestKotlinQueriesHelpers:
    """Test helper functions in the kotlin queries module."""

    def test_get_query_valid(self):
        all_q = kotlin_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = kotlin_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            kotlin_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = kotlin_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = kotlin_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_kotlin_query_valid(self):
        available = kotlin_queries.get_available_kotlin_queries()
        if available:
            result = kotlin_queries.get_kotlin_query(available[0])
            assert isinstance(result, str | dict)

    def test_get_kotlin_query_invalid_raises(self):
        with pytest.raises(ValueError):
            kotlin_queries.get_kotlin_query("__nonexistent__")

    def test_get_kotlin_query_description(self):
        available = kotlin_queries.get_available_kotlin_queries()
        if available:
            desc = kotlin_queries.get_kotlin_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_kotlin_query_description_unknown(self):
        desc = kotlin_queries.get_kotlin_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_kotlin_queries(self):
        result = kotlin_queries.get_available_kotlin_queries()
        assert isinstance(result, list)
        assert len(result) > 0
