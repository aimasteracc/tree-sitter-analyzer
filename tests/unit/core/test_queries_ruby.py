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
    assert len(ruby.RUBY_CLASS_QUERY) > 0
    assert isinstance(ruby.RUBY_METHOD_QUERY, str)
    assert len(ruby.RUBY_METHOD_QUERY) > 0
    assert isinstance(ruby.RUBY_CONSTANT_QUERY, str)
    assert len(ruby.RUBY_CONSTANT_QUERY) > 0


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
