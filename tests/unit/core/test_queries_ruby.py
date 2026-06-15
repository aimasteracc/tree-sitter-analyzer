"""Tests for Ruby tree-sitter queries."""


def test_ruby_queries_import():
    """Test that Ruby queries can be imported."""
    from tree_sitter_analyzer.queries import ruby

    # Verify all query constants exist
    assert hasattr(ruby, "RUBY_CLASS_QUERY")
    assert hasattr(ruby, "RUBY_METHOD_QUERY")
    assert hasattr(ruby, "RUBY_CONSTANT_QUERY")

    # Verify they are non-empty strings
    assert isinstance(ruby.RUBY_CLASS_QUERY, str)
    assert len(ruby.RUBY_CLASS_QUERY) == 119
    assert isinstance(ruby.RUBY_METHOD_QUERY, str)
    assert len(ruby.RUBY_METHOD_QUERY) == 274
    assert isinstance(ruby.RUBY_CONSTANT_QUERY, str)
    assert len(ruby.RUBY_CONSTANT_QUERY) == 69


def test_ruby_class_query_structure():
    """Test Ruby class query contains expected patterns."""
    from tree_sitter_analyzer.queries.ruby import RUBY_CLASS_QUERY

    assert "class" in RUBY_CLASS_QUERY
    assert "@class.name" in RUBY_CLASS_QUERY


def test_ruby_method_query_structure():
    """Test Ruby method query contains expected patterns."""
    from tree_sitter_analyzer.queries.ruby import RUBY_METHOD_QUERY

    assert "method" in RUBY_METHOD_QUERY
    assert "@method.name" in RUBY_METHOD_QUERY


def test_ruby_constant_query_structure():
    """Test Ruby constant query contains expected patterns."""
    from tree_sitter_analyzer.queries.ruby import RUBY_CONSTANT_QUERY

    assert "constant" in RUBY_CONSTANT_QUERY or "assignment" in RUBY_CONSTANT_QUERY
    assert "@" in RUBY_CONSTANT_QUERY


def test_all_queries_dict_structure():
    """Test ALL_QUERIES contains expected keys and structure."""
    from tree_sitter_analyzer.queries.ruby import ALL_QUERIES

    assert "class" in ALL_QUERIES
    assert "method" in ALL_QUERIES
    assert "require" in ALL_QUERIES
    assert "heredoc" in ALL_QUERIES
    for key, value in ALL_QUERIES.items():
        assert isinstance(value, dict), f"ALL_QUERIES[{key!r}] is not a dict"
        assert "query" in value
        assert "description" in value


def test_all_queries_aliases():
    """Test cross-language aliases point to correct entries."""
    from tree_sitter_analyzer.queries.ruby import ALL_QUERIES

    assert ALL_QUERIES["classes"] is ALL_QUERIES["class"]
    assert ALL_QUERIES["functions"] is ALL_QUERIES["method"]
    assert ALL_QUERIES["methods"] is ALL_QUERIES["method"]
    assert ALL_QUERIES["imports"] is ALL_QUERIES["require"]
    assert ALL_QUERIES["variables"] is ALL_QUERIES["instance_variable"]


def test_get_all_queries():
    """Test get_all_queries returns the full query registry."""
    from tree_sitter_analyzer.queries.ruby import ALL_QUERIES, get_all_queries

    result = get_all_queries()
    assert result is ALL_QUERIES
    assert isinstance(result, dict)
    assert len(result) == 24


def test_get_query_existing():
    """Test get_query returns query string for known names."""
    from tree_sitter_analyzer.queries.ruby import get_query

    q = get_query("class")
    assert isinstance(q, str)
    assert "class" in q


def test_get_query_alias():
    """Test get_query works with alias names."""
    from tree_sitter_analyzer.queries.ruby import get_query

    q = get_query("classes")
    assert isinstance(q, str)
    assert "class" in q


def test_get_query_not_found():
    """Test get_query raises ValueError for unknown names."""
    import pytest

    from tree_sitter_analyzer.queries.ruby import get_query

    with pytest.raises(ValueError, match="not found"):
        get_query("nonexistent_query")


def test_list_queries():
    """Test list_queries returns all query names including aliases."""
    from tree_sitter_analyzer.queries.ruby import ALL_QUERIES, list_queries

    names = list_queries()
    assert isinstance(names, list)
    assert "class" in names
    assert "classes" in names
    assert len(names) == len(ALL_QUERIES)
