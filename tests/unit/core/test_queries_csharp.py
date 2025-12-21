"""Tests for C# tree-sitter queries."""


def test_csharp_queries_import():
    """Test that C# queries can be imported."""
    from tree_sitter_analyzer.queries import csharp

    # Verify query dictionary exists
    assert hasattr(csharp, "CSHARP_QUERIES")
    assert isinstance(csharp.CSHARP_QUERIES, dict)
    assert len(csharp.CSHARP_QUERIES) > 0


def test_csharp_class_query_structure():
    """Test C# class query contains expected patterns."""
    from tree_sitter_analyzer.queries.csharp import CSHARP_QUERIES

    assert "class" in CSHARP_QUERIES
    assert "class_declaration" in CSHARP_QUERIES["class"]
    assert "@class_name" in CSHARP_QUERIES["class"]
