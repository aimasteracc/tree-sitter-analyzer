#!/usr/bin/env python3
"""
Tests for query_loader module
"""

import sys

# Add project root to path
sys.path.insert(0, ".")

from tree_sitter_analyzer.query_loader import (
    QueryLoader,
    get_query,
    is_language_supported,
    list_queries,
    list_supported_languages,
    query_loader,
)


def test_query_loader_instance():
    """Test that query loader instance is properly initialized"""
    assert query_loader is not None
    assert isinstance(query_loader, QueryLoader)


def test_list_supported_languages():
    """Test listing supported languages"""
    languages = query_loader.list_supported_languages()
    assert isinstance(languages, list)

    # Should include the languages we've created query files for
    expected_languages = ["java", "javascript", "python", "typescript"]
    for lang in expected_languages:
        assert lang in languages


def test_load_language_queries_java():
    """Test loading Java queries"""
    queries = query_loader.load_language_queries("java")
    assert isinstance(queries, dict)
    assert len(queries) == 71

    # Should have common queries
    assert "functions" in queries or "method" in queries
    assert "classes" in queries or "class" in queries


def test_load_language_queries_javascript():
    """Test loading JavaScript queries"""
    queries = query_loader.load_language_queries("javascript")
    assert isinstance(queries, dict)
    assert len(queries) == 87

    # Should have expected query types
    expected_queries = ["functions", "classes", "variables", "imports"]
    for query in expected_queries:
        assert query in queries


def test_load_language_queries_python():
    """Test loading Python queries"""
    queries = query_loader.load_language_queries("python")
    assert isinstance(queries, dict)
    assert len(queries) == 88

    # Should have Python-specific queries
    expected_queries = ["functions", "classes", "imports", "decorators"]
    for query in expected_queries:
        assert query in queries


def test_load_language_queries_typescript():
    """Test loading TypeScript queries"""
    queries = query_loader.load_language_queries("typescript")
    assert isinstance(queries, dict)
    assert len(queries) == 83

    # Should have TypeScript-specific queries
    expected_queries = ["functions", "classes", "interfaces", "type_aliases"]
    for query in expected_queries:
        assert query in queries


def test_load_language_queries_unknown():
    """Test loading queries for unknown language"""
    queries = query_loader.load_language_queries("unknown_language")
    assert isinstance(queries, dict)
    assert len(queries) == 0


def test_get_query_valid():
    """Test getting a valid query"""
    # Test with Java (the `if not None` guard was a dead branch: both
    # languages ship a "functions" query, so assert the live values directly)
    java_query = query_loader.get_query("java", "functions")
    assert isinstance(java_query, str)
    assert len(java_query) == 38

    # Test with JavaScript
    js_query = query_loader.get_query("javascript", "functions")
    assert isinstance(js_query, str)
    assert len(js_query) == 658


def test_get_query_invalid():
    """Test getting an invalid query"""
    result = query_loader.get_query("java", "nonexistent_query")
    assert result is None

    result = query_loader.get_query("unknown_language", "functions")
    assert result is None


def test_get_query_description():
    """Test getting query descriptions"""
    # Test with valid query (guard removed: the description exists, pin it)
    desc = query_loader.get_query_description("javascript", "functions")
    assert desc == "Search all function declarations, expressions, and methods"

    # Test with invalid query
    desc = query_loader.get_query_description("java", "nonexistent")
    assert desc is None


def test_list_queries_for_language():
    """Test listing queries for specific languages"""
    # All four languages are supported, so the former `if supported` guard
    # was a dead branch — pin the exact per-language query counts instead.
    expected_counts = {"java": 71, "javascript": 87, "python": 88, "typescript": 83}
    for language, expected in expected_counts.items():
        assert language in query_loader.list_supported_languages()
        queries = query_loader.list_queries(language)
        assert isinstance(queries, list)
        assert len(queries) == expected


def test_get_common_queries():
    """Test getting common queries across languages"""
    common = query_loader.get_common_queries()
    assert isinstance(common, list)
    assert len(common) == 4

    # Common queries should exist in multiple languages; pin the exact
    # per-query language counts (sorted) instead of a loose >= 2 bound.
    lang_counts = sorted(
        sum(
            1
            for lang in query_loader.list_supported_languages()
            if query_name in query_loader.list_queries(lang)
        )
        for query_name in common
    )
    assert lang_counts == [12, 13, 13, 13]


def test_is_language_supported_function():
    """Test standalone is_language_supported function"""
    assert is_language_supported("java")
    assert is_language_supported("javascript")
    assert is_language_supported("python")
    assert is_language_supported("typescript")
    assert not is_language_supported("unknown")


def test_get_all_queries_for_language():
    """Test getting all queries with descriptions"""
    # All three languages are supported (former guard was a dead branch);
    # pin exact query counts and the exact minimum query-string length.
    expected = {"java": (71, 34), "javascript": (87, 20), "python": (88, 28)}
    for language, (expected_count, expected_min_len) in expected.items():
        assert query_loader.is_language_supported(language)
        all_queries = query_loader.get_all_queries_for_language(language)
        assert isinstance(all_queries, dict)
        assert len(all_queries) == expected_count

        lengths = []
        for _query_name, (query_string, description) in all_queries.items():
            assert isinstance(query_string, str)
            assert isinstance(description, str)
            lengths.append(len(query_string))
        assert min(lengths) == expected_min_len


def test_refresh_cache():
    """Test cache refresh functionality"""
    # Start from a clean cache so the pinned count is order-independent
    query_loader.refresh_cache()

    # Load some queries first
    query_loader.load_language_queries("java")
    query_loader.load_language_queries("javascript")

    # Cache should have exactly the two languages just loaded
    assert len(query_loader._loaded_queries) == 2

    # Refresh cache
    query_loader.refresh_cache()

    # Cache should be empty
    assert len(query_loader._loaded_queries) == 0
    assert len(query_loader._query_modules) == 0


def test_convenience_functions():
    """Test convenience functions"""
    # get_query function
    query = get_query("javascript", "functions")
    if query is not None:
        assert isinstance(query, str)

    # list_queries function
    queries = list_queries("python")
    assert isinstance(queries, list)

    # list_supported_languages function
    languages = list_supported_languages()
    assert isinstance(languages, list)
    assert "java" in languages


def test_load_language_queries_import_error(mocker):
    """Test handling of import errors when loading queries"""
    mock_import = mocker.patch("importlib.import_module")
    mock_import.side_effect = ImportError("Module not found")

    # Should handle gracefully and return empty dict
    queries = query_loader.load_language_queries("test_language")
    assert queries == {}


def test_load_language_queries_missing_attributes(mocker):
    """Test handling when query module lacks expected attributes"""
    mock_module = mocker.MagicMock()
    # Remove expected attributes
    if hasattr(mock_module, "get_all_queries"):
        del mock_module.get_all_queries
    if hasattr(mock_module, "ALL_QUERIES"):
        del mock_module.ALL_QUERIES

    mock_import = mocker.patch("importlib.import_module")
    mock_import.return_value = mock_module

    queries = query_loader.load_language_queries("test_language")
    assert queries == {}


# Edge cases and error conditions tests
def test_empty_language_name():
    """Test handling of empty language names"""
    assert query_loader.get_query("", "functions") is None
    assert query_loader.list_queries("") == []
    assert not query_loader.is_language_supported("")


def test_none_parameters():
    """Test handling of None parameters"""
    assert query_loader.get_query(None, "functions") is None
    assert query_loader.get_query("java", None) is None
    assert query_loader.list_queries(None) == []


def test_caching_behavior():
    """Test that queries are properly cached"""
    # Clear cache
    query_loader.refresh_cache()

    # First load should populate cache
    queries1 = query_loader.load_language_queries("java")
    assert "java" in query_loader._loaded_queries

    # Second load should use cache
    queries2 = query_loader.load_language_queries("java")
    assert queries1 is queries2  # Should be same object from cache
