"""Tests for PHP tree-sitter queries."""


def test_php_queries_import():
    """Test that PHP queries can be imported."""
    from tree_sitter_analyzer.queries import php

    # Verify all query constants exist
    assert hasattr(php, "PHP_CLASS_QUERY")
    assert hasattr(php, "PHP_METHOD_QUERY")
    assert hasattr(php, "PHP_FUNCTION_QUERY")
    assert hasattr(php, "PHP_PROPERTY_QUERY")
    assert hasattr(php, "PHP_NAMESPACE_QUERY")

    # Verify they are non-empty strings
    assert isinstance(php.PHP_CLASS_QUERY, str)
    assert len(php.PHP_CLASS_QUERY) > 0
    assert isinstance(php.PHP_METHOD_QUERY, str)
    assert len(php.PHP_METHOD_QUERY) > 0
    assert isinstance(php.PHP_FUNCTION_QUERY, str)
    assert len(php.PHP_FUNCTION_QUERY) > 0


def test_php_class_query_structure():
    """Test PHP class query contains expected patterns."""
    from tree_sitter_analyzer.queries.php import PHP_CLASS_QUERY

    assert "class_declaration" in PHP_CLASS_QUERY
    assert "interface_declaration" in PHP_CLASS_QUERY
    assert "trait_declaration" in PHP_CLASS_QUERY
    assert "@class.name" in PHP_CLASS_QUERY


def test_php_method_query_structure():
    """Test PHP method query contains expected patterns."""
    from tree_sitter_analyzer.queries.php import PHP_METHOD_QUERY

    assert "method_declaration" in PHP_METHOD_QUERY
    assert "@method.name" in PHP_METHOD_QUERY


def test_php_function_query_structure():
    """Test PHP function query contains expected patterns."""
    from tree_sitter_analyzer.queries.php import PHP_FUNCTION_QUERY

    assert "function_definition" in PHP_FUNCTION_QUERY
    assert "@function.name" in PHP_FUNCTION_QUERY
