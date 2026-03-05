"""Tests for iterative tree traversal."""


class TestIterativeTreeTraversal:
    """Test iterative tree traversal to avoid stack overflow."""

    def test_parse_deeply_nested_code(self):
        """Should handle deeply nested code without stack overflow."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()

        # Create deeply nested Python code (1000 levels)
        deep_code = "x = " + "(" * 1000 + "1" + ")" * 1000

        # This should not raise RecursionError
        result = parser.parse_code(deep_code, "python")
        assert result is not None
        assert result.success is True

    def test_parse_code_with_errors(self):
        """Should handle code with syntax errors."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()

        # Code with syntax error
        code_with_error = "def foo(\n"  # Incomplete function

        result = parser.parse_code(code_with_error, "python")
        assert result is not None  # Should still parse, just with error nodes
        assert result.success is True  # Parsing succeeds, tree contains error nodes

    def test_get_parse_errors_deeply_nested(self):
        """Should extract errors from deeply nested code without stack overflow."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()

        # Create deeply nested code with an error at the end
        deep_code_with_error = "x = " + "(" * 1000 + "1" + ")" * 999 + "+"  # Missing closing paren, extra operator

        result = parser.parse_code(deep_code_with_error, "python")
        assert result is not None
        assert result.tree is not None

        # This should not raise RecursionError when finding error nodes
        errors = parser.get_parse_errors(result.tree)
        assert isinstance(errors, list)

    def test_get_parse_errors_simple(self):
        """Should extract errors from code with simple syntax errors."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()

        # Code with obvious syntax error
        code = "def foo(\n"

        result = parser.parse_code(code, "python")
        assert result.success is True
        assert result.tree is not None

        errors = parser.get_parse_errors(result.tree)
        assert len(errors) > 0
        assert errors[0]["type"] == "ERROR"

    def test_get_parse_errors_valid_code(self):
        """Should return empty list for valid code."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()

        code = "x = 1 + 2\n"

        result = parser.parse_code(code, "python")
        assert result.success is True
        assert result.tree is not None

        errors = parser.get_parse_errors(result.tree)
        assert errors == []

    def test_parse_very_deeply_nested_code(self):
        """Should handle extremely deep nesting (2000 levels) without stack overflow."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()

        # Create extremely deeply nested Python code (2000 levels)
        deep_code = "x = " + "(" * 2000 + "1" + ")" * 2000

        # This should not raise RecursionError
        result = parser.parse_code(deep_code, "python")
        assert result is not None
        assert result.success is True

        # Verify we can traverse the tree for errors without stack overflow
        if result.tree:
            errors = parser.get_parse_errors(result.tree)
            assert isinstance(errors, list)
