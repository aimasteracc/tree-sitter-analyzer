"""Tests for C# tree-sitter queries."""


def test_csharp_queries_import():
    """Test that C# queries can be imported."""
    from tree_sitter_analyzer.queries import csharp

    assert hasattr(csharp, "CSHARP_QUERIES")
    assert isinstance(csharp.CSHARP_QUERIES, dict)
    assert csharp.CSHARP_QUERIES


def test_csharp_class_query_structure():
    """Test C# class query contains expected patterns."""
    from tree_sitter_analyzer.queries.csharp import CSHARP_QUERIES

    assert "class" in CSHARP_QUERIES
    assert "class_declaration" in CSHARP_QUERIES["class"]
    assert "@class_name" in CSHARP_QUERIES["class"]


def test_csharp_all_queries_registry():
    """Test ALL_QUERIES registry is built from CSHARP_QUERIES and CSHARP_QUERY_DESCRIPTIONS."""
    from tree_sitter_analyzer.queries.csharp import ALL_QUERIES, CSHARP_QUERIES

    assert isinstance(ALL_QUERIES, dict)
    for name in CSHARP_QUERIES:
        assert name in ALL_QUERIES
        assert "query" in ALL_QUERIES[name]
        assert "description" in ALL_QUERIES[name]


def test_csharp_all_queries_aliases():
    """Test cross-language aliases are registered."""
    from tree_sitter_analyzer.queries.csharp import ALL_QUERIES

    assert "classes" in ALL_QUERIES
    assert ALL_QUERIES["classes"] is ALL_QUERIES["class"]
    assert "functions" in ALL_QUERIES
    assert ALL_QUERIES["functions"] is ALL_QUERIES["method"]
    assert "methods" in ALL_QUERIES
    assert ALL_QUERIES["methods"] is ALL_QUERIES["method"]
    assert "imports" in ALL_QUERIES
    assert ALL_QUERIES["imports"] is ALL_QUERIES["using"]
    assert "variables" in ALL_QUERIES
    assert ALL_QUERIES["variables"] is ALL_QUERIES["field"]


def test_csharp_get_all_queries():
    """Test get_all_queries returns the full registry."""
    from tree_sitter_analyzer.queries.csharp import ALL_QUERIES, get_all_queries

    result = get_all_queries()
    assert result is ALL_QUERIES


def test_csharp_get_query():
    """Test get_query returns query strings for known names."""
    from tree_sitter_analyzer.queries.csharp import get_query

    result = get_query("class")
    assert "class_declaration" in result

    result = get_query("classes")
    assert "class_declaration" in result


def test_csharp_get_query_not_found():
    """Test get_query raises ValueError for unknown name."""
    import pytest

    from tree_sitter_analyzer.queries.csharp import get_query

    with pytest.raises(ValueError, match="not found"):
        get_query("nonexistent_query")


def test_csharp_list_queries():
    """Test list_queries returns all available query names."""
    from tree_sitter_analyzer.queries.csharp import ALL_QUERIES, list_queries

    names = list_queries()
    assert isinstance(names, list)
    assert set(names) == set(ALL_QUERIES.keys())
    assert "class" in names
    assert "method" in names
    assert "classes" in names


def test_csharp_query_descriptions():
    """Test every query has a corresponding description."""
    from tree_sitter_analyzer.queries.csharp import (
        CSHARP_QUERIES,
        CSHARP_QUERY_DESCRIPTIONS,
    )

    for name in CSHARP_QUERIES:
        assert name in CSHARP_QUERY_DESCRIPTIONS, f"Missing description for '{name}'"
        assert CSHARP_QUERY_DESCRIPTIONS[name]
