"""Token optimizer module tests.

Unit tests for the TokenOptimizer class.

Features:
    - Comment removal
    - Whitespace optimization
    - Multi-level optimization

Architecture:
    - TokenOptimizer: Core class for token optimization
    - Language-specific optimization strategies

Usage:
    pytest v2/tests/unit/test_token_optimizer.py -v

Performance Characteristics:
    - Time: O(n) where n is number of lines
    - Space: O(1) additional space

Thread Safety:
    - Thread-safe: Yes (immutable operations)

Dependencies:
    - External: pytest
    - Internal: token_optimizer module

Error Handling:
    - 3 custom exceptions

Note:
    Tests follow TDD Red-Green-Refactor pattern

Example:
    ```python
    optimizer = TokenOptimizer()
    result = optimizer.optimize(code, "python", level=2)
    ```
"""

import pytest

from tree_sitter_analyzer_v2.core.token_optimizer import (
    InvalidLanguageError,
    OptimizationError,
    TokenOptimizer,
    TokenOptimizerBaseError,
)


class TestTokenOptimizer:
    """Test TokenOptimizer class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.optimizer = TokenOptimizer()

    # =========================================================================
    # Red Phase Tests - These should FAIL initially
    # =========================================================================

    def test_remove_python_comments_success(self) -> None:
        """Test removing Python comments successfully."""
        input_code = """def hello():
    # 这是一个注释
    print("hello")
    # 另一行注释
"""
        result = self.optimizer.remove_comments(input_code, "python")
        assert "# 这是一个注释" not in result
        assert "# 另一行注释" not in result
        assert 'print("hello")' in result

    def test_remove_javascript_comments_success(self) -> None:
        """Test removing JavaScript comments."""
        input_code = """// 这是一个单行注释
function hello() {
    /* 多行注释 */
    console.log("hello");
}
"""
        result = self.optimizer.remove_comments(input_code, "javascript")
        assert "// 这是一个单行注释" not in result
        assert "/* 多行注释 */" not in result
        assert 'console.log("hello")' in result

    def test_remove_empty_lines_success(self) -> None:
        """Test removing empty lines."""
        input_code = """def hello():


    print("hello")


"""
        result = self.optimizer.remove_empty_lines(input_code)
        assert "\n\n" not in result
        assert 'print("hello")' in result

    def test_compress_whitespace_success(self) -> None:
        """Test compressing whitespace between tokens."""
        input_code = """def hello(    arg1,    arg2 ):
    x =    1
"""
        result = self.optimizer.compress_whitespace(input_code)
        # Should compress multiple spaces to single, but preserve indentation
        assert "arg1,    arg2" not in result  # No multiple spaces in args
        assert "x =    1" not in result  # No multiple spaces around operators

    def test_optimize_python_level_1(self) -> None:
        """Test Python optimization level 1 (remove empty lines)."""
        input_code = """def hello():


    print("hello")


"""
        result = self.optimizer.optimize(input_code, "python", level=1)
        assert "\n\n" not in result

    def test_optimize_python_level_2(self) -> None:
        """Test Python optimization level 2 (remove empty lines + comments)."""
        input_code = """def hello():
    # 注释
    print("hello")
"""
        result = self.optimizer.optimize(input_code, "python", level=2)
        assert "# 注释" not in result
        assert 'print("hello")' in result

    def test_optimize_javascript_level_2(self) -> None:
        """Test JavaScript optimization level 2."""
        input_code = """// 单行注释
function hello() {
    /* 多行注释 */
    return 1;
}
"""
        result = self.optimizer.optimize(input_code, "javascript", level=2)
        assert "// 单行注释" not in result
        assert "/* 多行注释 */" not in result

    def test_empty_file_returns_empty(self) -> None:
        """Test empty file returns empty string."""
        result = self.optimizer.remove_comments("", "python")
        assert result == ""

    def test_file_with_only_comments_returns_empty(self) -> None:
        """Test file with only comments returns empty string."""
        input_code = """# 这只是注释
# 另一行注释
# 第三行注释
"""
        result = self.optimizer.remove_comments(input_code, "python")
        assert result.strip() == ""

    def test_preserve_code_structure(self) -> None:
        """Test that code structure is preserved after optimization."""
        input_code = '''class MyClass:
    def method(self, arg1: int, arg2: str) -> bool:
        """Docstring."""
        # Comment
        return True
'''
        result = self.optimizer.optimize(input_code, "python", level=2)
        # Check structure preserved
        assert "class MyClass:" in result
        assert "def method(" in result
        assert "return True" in result
        # Check comments removed
        assert "# Comment" not in result
        # Note: level 2 does not remove docstrings, only comments

    def test_get_statistics(self) -> None:
        """Test getting optimization statistics."""
        stats = self.optimizer.get_statistics()
        assert "total_calls" in stats
        assert "total_time" in stats
        assert "errors" in stats
        assert "avg_time" in stats

    def test_invalid_language_raises_error(self) -> None:
        """Test invalid language raises InvalidLanguageError."""
        with pytest.raises(InvalidLanguageError):
            self.optimizer.remove_comments("code", "invalid_lang")

    def test_none_input_raises_error(self) -> None:
        """Test None input raises OptimizationError."""
        with pytest.raises(OptimizationError):
            self.optimizer.remove_comments(None, "python")  # type: ignore


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestTokenOptimizerEdgeCases:
    """Test edge cases and integration scenarios."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.optimizer = TokenOptimizer()

    def test_large_file_performance(self) -> None:
        """Test performance on large file (>10000 lines)."""
        # Generate large file
        lines = ["def func():"] + ["    # comment"] * 10000 + ["    pass"]
        input_code = "\n".join(lines)

        import time

        start = time.perf_counter()
        result = self.optimizer.remove_comments(input_code, "python")
        elapsed = time.perf_counter() - start

        # Should process in less than 1 second
        assert elapsed < 1.0
        # Comments should be removed
        assert "# comment" not in result
        # Function structure preserved
        assert "def func():" in result
        assert "pass" in result

    def test_nested_block_comments(self) -> None:
        """Test handling of nested block comments (Python only)."""
        input_code = '''# 外层注释
def func():
    # 内层注释
    """docstring"""
    # 另一个注释
    pass
'''
        result = self.optimizer.remove_comments(input_code, "python")
        # All # comments should be removed
        assert "# 外层注释" not in result
        assert "# 内层注释" not in result
        assert "# 另一个注释" not in result
        # Code should be preserved
        assert "def func():" in result
        assert "pass" in result

    def test_special_files_not_modified(self) -> None:
        """Test that JSON/YAML files are not modified."""
        json_input = '{"key": "value", "array": [1, 2, 3]}'
        result = self.optimizer.remove_comments(json_input, "json")
        assert result == json_input

        yaml_input = """key: value
array:
  - 1
  - 2
  - 3
"""
        result = self.optimizer.remove_comments(yaml_input, "yaml")
        assert result == yaml_input

    def test_optimization_levels_summary(self) -> None:
        """Test summary of optimization levels."""
        summary = self.optimizer.get_optimization_summary()
        assert "levels" in summary
        assert "1" in summary["levels"]
        assert "2" in summary["levels"]
        assert "3" in summary["levels"]
        assert "4" in summary["levels"]
        # Check that level 3 mentions docstrings
        level3_desc = summary["levels"]["3"]
        assert "docstring" in level3_desc.lower()

    def test_exception_hierarchy(self) -> None:
        """Test that all exceptions inherit from TokenOptimizerBaseError."""
        assert issubclass(InvalidLanguageError, TokenOptimizerBaseError)
        assert issubclass(OptimizationError, TokenOptimizerBaseError)
        # Verify base error inherits from Exception
        assert issubclass(TokenOptimizerBaseError, Exception)

    def test_optimize_level_3_removes_docstrings(self) -> None:
        """Test level 3 optimization removes docstrings."""
        input_code = '''def hello():
    """This is a docstring."""
    print("hello")
'''
        result = self.optimizer.optimize(input_code, "python", level=3)
        assert "This is a docstring" not in result
        assert 'print("hello")' in result

    def test_optimize_level_4_full_compression(self) -> None:
        """Test level 4 optimization does full compression."""
        input_code = """def hello():
    # comment
    x =    1
    print("hello")
"""
        result = self.optimizer.optimize(input_code, "python", level=4)
        assert "# comment" not in result
        # Multiple spaces should be compressed
        assert "x = 1" in result

    def test_optimize_invalid_level_raises_error(self) -> None:
        """Test invalid optimization level raises OptimizationError."""
        with pytest.raises(OptimizationError):
            self.optimizer.optimize("code", "python", level=0)
        with pytest.raises(OptimizationError):
            self.optimizer.optimize("code", "python", level=5)

    def test_java_comment_removal(self) -> None:
        """Test Java comment removal (double slash language)."""
        input_code = """// Java comment
public class Hello {
    /* block comment */
    public void main() {
        System.out.println("hello"); // inline
    }
}
"""
        result = self.optimizer.remove_comments(input_code, "java")
        assert "// Java comment" not in result
        assert "/* block comment */" not in result
        assert "public class Hello" in result

    def test_url_in_hash_comment_preserved(self) -> None:
        """Test that URLs with hash are not treated as comments."""
        input_code = 'url = "https://example.com"  # this is a comment'
        result = self.optimizer.remove_comments(input_code, "python")
        assert "https://example.com" in result

    def test_compress_whitespace_empty_string(self) -> None:
        """Test compress_whitespace with empty string."""
        result = self.optimizer.compress_whitespace("")
        assert result == ""

    def test_remove_empty_lines_empty_string(self) -> None:
        """Test remove_empty_lines with empty string."""
        result = self.optimizer.remove_empty_lines("")
        assert result == ""

    def test_statistics_after_operations(self) -> None:
        """Test statistics are updated after operations."""
        self.optimizer.remove_comments("# comment\ncode", "python")
        stats = self.optimizer.get_statistics()
        assert stats["total_calls"] >= 1
        assert stats["total_time"] > 0
        assert stats["lines_processed"] > 0

    def test_multiline_block_comment_javascript(self) -> None:
        """Test multi-line block comment removal in JavaScript."""
        input_code = """function hello() {
    /*
     * This is a multi-line
     * block comment
     */
    return 1;
}
"""
        result = self.optimizer.remove_comments(input_code, "javascript")
        assert "multi-line" not in result
        assert "block comment" not in result
        assert "return 1;" in result

    def test_none_input_compress_whitespace_raises_error(self) -> None:
        """Test None input to compress_whitespace raises OptimizationError."""
        with pytest.raises(OptimizationError):
            self.optimizer.compress_whitespace(None)  # type: ignore

    def test_none_input_remove_empty_lines_raises_error(self) -> None:
        """Test None input to remove_empty_lines raises OptimizationError."""
        with pytest.raises(OptimizationError):
            self.optimizer.remove_empty_lines(None)  # type: ignore
