#!/usr/bin/env python3
"""
Unit tests for file_handler module.

Tests file reading functionality with encoding detection and fallback.
"""

from unittest.mock import patch

from tree_sitter_analyzer.file_handler import (
    detect_language_from_extension,
    log_error,
    log_info,
    log_warning,
    read_file_lines_range,
    read_file_partial,
    read_file_with_fallback,
)


class TestLoggingFunctions:
    """Test logging wrapper functions."""

    @patch("tree_sitter_analyzer.file_handler.logger")
    def test_log_error(self, mock_logger):
        """Test log_error function."""
        log_error("Test error message")
        mock_logger.error.assert_called_once_with("Test error message")

    @patch("tree_sitter_analyzer.file_handler.logger")
    def test_log_error_with_args(self, mock_logger):
        """Test log_error with arguments."""
        log_error("Error with %s", "arg")
        mock_logger.error.assert_called_once_with("Error with %s", "arg")

    @patch("tree_sitter_analyzer.file_handler.logger")
    def test_log_info(self, mock_logger):
        """Test log_info function."""
        log_info("Test info message")
        mock_logger.info.assert_called_once_with("Test info message")

    @patch("tree_sitter_analyzer.file_handler.logger")
    def test_log_info_with_args(self, mock_logger):
        """Test log_info with arguments."""
        log_info("Info with %s and %d", "arg", 42)
        mock_logger.info.assert_called_once_with("Info with %s and %d", "arg", 42)

    @patch("tree_sitter_analyzer.file_handler.logger")
    def test_log_warning(self, mock_logger):
        """Test log_warning function."""
        log_warning("Test warning message")
        mock_logger.warning.assert_called_once_with("Test warning message")

    @patch("tree_sitter_analyzer.file_handler.logger")
    def test_log_warning_with_kwargs(self, mock_logger):
        """Test log_warning with keyword arguments."""
        log_warning("Warning with %s", "arg", extra={"key": "value"})
        mock_logger.warning.assert_called_once_with(
            "Warning with %s", "arg", extra={"key": "value"}
        )


class TestDetectLanguageFromExtension:
    """Test detect_language_from_extension function."""

    def test_detect_java(self):
        """Test Java file detection."""
        assert detect_language_from_extension("test.java") == "java"
        assert detect_language_from_extension("/path/to/Test.java") == "java"

    def test_detect_python(self):
        """Test Python file detection."""
        assert detect_language_from_extension("test.py") == "python"
        assert detect_language_from_extension("/path/to/test.py") == "python"

    def test_detect_javascript(self):
        """Test JavaScript file detection."""
        assert detect_language_from_extension("test.js") == "javascript"
        assert detect_language_from_extension("app.js") == "javascript"

    def test_detect_typescript(self):
        """Test TypeScript file detection."""
        assert detect_language_from_extension("test.ts") == "typescript"
        assert detect_language_from_extension("app.ts") == "typescript"

    def test_detect_cpp(self):
        """Test C++ file detection."""
        assert detect_language_from_extension("test.cpp") == "cpp"
        assert detect_language_from_extension("test.hpp") == "cpp"

    def test_detect_c(self):
        """Test C file detection."""
        assert detect_language_from_extension("test.c") == "c"
        assert detect_language_from_extension("test.h") == "c"

    def test_detect_csharp(self):
        """Test C# file detection."""
        assert detect_language_from_extension("test.cs") == "csharp"

    def test_detect_go(self):
        """Test Go file detection."""
        assert detect_language_from_extension("test.go") == "go"

    def test_detect_rust(self):
        """Test Rust file detection."""
        assert detect_language_from_extension("test.rs") == "rust"

    def test_detect_ruby(self):
        """Test Ruby file detection."""
        assert detect_language_from_extension("test.rb") == "ruby"

    def test_detect_php(self):
        """Test PHP file detection."""
        assert detect_language_from_extension("test.php") == "php"

    def test_detect_kotlin(self):
        """Test Kotlin file detection."""
        assert detect_language_from_extension("test.kt") == "kotlin"

    def test_detect_scala(self):
        """Test Scala file detection."""
        assert detect_language_from_extension("test.scala") == "scala"

    def test_detect_swift(self):
        """Test Swift file detection."""
        assert detect_language_from_extension("test.swift") == "swift"

    def test_detect_unknown_extension(self):
        """Test unknown file extension."""
        assert detect_language_from_extension("test.unknown") == "unknown"
        assert detect_language_from_extension("test.txt") == "unknown"

    def test_detect_no_extension(self):
        """Test file without extension."""
        assert detect_language_from_extension("Makefile") == "unknown"
        assert detect_language_from_extension("/path/to/README") == "unknown"

    def test_detect_case_insensitive(self):
        """Test extension detection is case insensitive."""
        assert detect_language_from_extension("test.JAVA") == "java"
        assert detect_language_from_extension("test.PY") == "python"
        assert detect_language_from_extension("test.JS") == "javascript"
        assert detect_language_from_extension("test.TS") == "typescript"

    def test_detect_multiple_dots(self):
        """Test file with multiple dots in name."""
        assert detect_language_from_extension("test.min.js") == "javascript"
        assert detect_language_from_extension("test.spec.ts") == "typescript"


class TestReadFileWithFallback:
    """Test read_file_with_fallback function."""

    def test_read_existing_file(self, tmp_path):
        """Test reading an existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")

        result = read_file_with_fallback(str(test_file))
        assert result is not None
        assert result == b"Hello, World!"

    def test_read_nonexistent_file(self, tmp_path):
        """Test reading a non-existent file."""
        result = read_file_with_fallback(str(tmp_path / "nonexistent.txt"))
        assert result is None

    def test_read_file_with_encoding_detection(self, tmp_path):
        """Test reading file with encoding detection."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("こんにちは", encoding="utf-8")

        result = read_file_with_fallback(str(test_file))
        assert result is not None
        assert result.decode("utf-8") == "こんにちは"

    @patch("tree_sitter_analyzer.file_handler.read_file_safe")
    def test_read_file_exception_handling(self, mock_read, tmp_path):
        """Test exception handling when reading file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        mock_read.side_effect = Exception("Read error")

        result = read_file_with_fallback(str(test_file))
        assert result is None

    @patch("tree_sitter_analyzer.file_handler.read_file_safe")
    def test_read_file_with_different_encoding(self, mock_read, tmp_path):
        """Test reading file with different detected encoding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        mock_read.return_value = ("content", "latin-1")

        result = read_file_with_fallback(str(test_file))
        assert result is not None
        assert result == b"content"


class TestReadFilePartial:
    """Test read_file_partial function."""

    def test_read_partial_lines(self, tmp_path):
        """Test reading partial lines from file."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\nline4\nline5\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 2, 4)
        assert result == "line2\nline3\nline4\n"

    def test_read_partial_single_line(self, tmp_path):
        """Test reading a single line."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 2, 2)
        assert result == "line2\n"

    def test_read_partial_from_start(self, tmp_path):
        """Test reading from start of file."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 2)
        assert result == "line1\nline2\n"

    def test_read_partial_to_end(self, tmp_path):
        """Test reading to end of file."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 2)
        assert result == "line2\nline3\n"

    def test_read_partial_with_columns(self, tmp_path):
        """Test reading with column range."""
        test_file = tmp_path / "test.txt"
        content = "hello\nworld\npython\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 2, 1, 3)
        # First line: from column 1 to end, Second line: from start to column 3
        # Note: encoding_utils normalizes newlines to \n
        assert result == "ello\nwor"

    def test_read_partial_with_start_column_only(self, tmp_path):
        """Test reading with start column only."""
        test_file = tmp_path / "test.txt"
        content = "hello\nworld\npython\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 2, start_column=2)
        # First line: from column 2 to end, Second line: full line
        assert result == "llo\nworld"

    def test_read_partial_with_end_column_only(self, tmp_path):
        """Test reading with end column only."""
        test_file = tmp_path / "test.txt"
        content = "hello\nworld\npython\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 2, end_column=3)
        # First line: from start to column 3, Second line: from start to column 3
        assert result == "hello\nwor"

    def test_read_partial_single_line_with_columns(self, tmp_path):
        """Test reading single line with column range."""
        test_file = tmp_path / "test.txt"
        content = "hello\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 1, 1, 3)
        assert result == "el"

    def test_read_partial_nonexistent_file(self, tmp_path):
        """Test reading from non-existent file."""
        result = read_file_partial(str(tmp_path / "nonexistent.txt"), 1, 2)
        assert result is None

    def test_read_partial_invalid_start_line(self, tmp_path):
        """Test with invalid start line (zero)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n", encoding="utf-8")

        result = read_file_partial(str(test_file), 0, 1)
        assert result is None

    def test_read_partial_negative_start_line(self, tmp_path):
        """Test with negative start line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n", encoding="utf-8")

        result = read_file_partial(str(test_file), -1, 1)
        assert result is None

    def test_read_partial_invalid_range(self, tmp_path):
        """Test with invalid range (end < start)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        result = read_file_partial(str(test_file), 3, 1)
        assert result is None

    def test_read_partial_beyond_file_length(self, tmp_path):
        """Test reading beyond file length."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 10, 12)
        assert result == ""

    def test_read_partial_empty_file(self, tmp_path):
        """Test reading from empty file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("", encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 1)
        assert result == ""

    def test_read_partial_preserve_newlines(self, tmp_path):
        """Test that newlines are handled correctly."""
        test_file = tmp_path / "test.txt"
        content = "line1\r\nline2\nline3\r"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 3)
        # Note: encoding_utils normalizes newlines to \n
        # The function returns normalized newlines
        assert "line1" in result and "line2" in result

    def test_read_partial_column_beyond_line_length(self, tmp_path):
        """Test column beyond line length."""
        test_file = tmp_path / "test.txt"
        content = "hi\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 1, 5, 10)
        assert result == ""

    def test_read_partial_invalid_column_range(self, tmp_path):
        """Test with invalid column range (end < start)."""
        test_file = tmp_path / "test.txt"
        content = "hello\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 1, 3, 1)
        assert result == ""

    def test_read_partial_exception_handling(self, tmp_path):
        """Test exception handling."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n", encoding="utf-8")

        with patch(
            "tree_sitter_analyzer.file_handler.read_file_safe_streaming"
        ) as mock_stream:
            mock_stream.side_effect = Exception("Stream error")

            result = read_file_partial(str(test_file), 1, 1)
            assert result is None


class TestReadFileLinesRange:
    """Test read_file_lines_range function."""

    def test_read_lines_range(self, tmp_path):
        """Test reading lines range."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\nline4\nline5\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_lines_range(str(test_file), 2, 4)
        assert result == "line2\nline3\nline4\n"

    def test_read_lines_range_to_end(self, tmp_path):
        """Test reading lines range to end."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_lines_range(str(test_file), 2)
        assert result == "line2\nline3\n"

    def test_read_lines_range_single_line(self, tmp_path):
        """Test reading single line."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_lines_range(str(test_file), 2, 2)
        assert result == "line2\n"

    def test_read_lines_range_nonexistent_file(self, tmp_path):
        """Test reading from non-existent file."""
        result = read_file_lines_range(str(tmp_path / "nonexistent.txt"), 1, 2)
        assert result is None

    def test_read_lines_range_invalid_start(self, tmp_path):
        """Test with invalid start line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content\n", encoding="utf-8")

        result = read_file_lines_range(str(test_file), 0, 1)
        assert result is None

    def test_read_lines_range_invalid_range(self, tmp_path):
        """Test with invalid range."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\n", encoding="utf-8")

        result = read_file_lines_range(str(test_file), 2, 1)
        assert result is None

    def test_read_lines_range_beyond_file(self, tmp_path):
        """Test reading beyond file length."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_lines_range(str(test_file), 5, 10)
        assert result == ""


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_read_partial_large_file(self, tmp_path):
        """Test reading from large file."""
        test_file = tmp_path / "large.txt"
        lines = [f"line{i}\n" for i in range(1000)]
        test_file.write_text("".join(lines), encoding="utf-8")

        # Read middle section - adjust for 0-based indexing
        result = read_file_partial(str(test_file), 501, 506)
        assert result == "line500\nline501\nline502\nline503\nline504\nline505\n"

    def test_read_partial_unicode_content(self, tmp_path):
        """Test reading Unicode content."""
        test_file = tmp_path / "unicode.txt"
        content = "こんにちは\n世界\nPython\n"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 2)
        assert result == "こんにちは\n世界\n"

    def test_detect_language_path_with_spaces(self):
        """Test language detection with spaces in path."""
        assert detect_language_from_extension("path with spaces/test.py") == "python"

    def test_detect_language_special_characters(self):
        """Test language detection with special characters."""
        assert detect_language_from_extension("test-file_v2.0.py") == "python"
        assert detect_language_from_extension("test@file.js") == "javascript"


class TestIntegration:
    """Integration tests for file_handler module."""

    def test_full_workflow(self, tmp_path):
        """Test complete workflow: detect language and read file."""
        # Create test file
        test_file = tmp_path / "test.py"
        content = "def hello():\n    print('Hello, World!')\n"
        test_file.write_text(content, encoding="utf-8")

        # Detect language
        language = detect_language_from_extension(str(test_file))
        assert language == "python"

        # Read file with fallback
        bytes_content = read_file_with_fallback(str(test_file))
        assert bytes_content is not None
        assert bytes_content.decode("utf-8") == content

        # Read partial content
        partial = read_file_partial(str(test_file), 1, 2)
        assert partial == "def hello():\n    print('Hello, World!')\n"

    def test_multiple_partial_reads(self, tmp_path):
        """Test multiple partial reads from same file."""
        test_file = tmp_path / "test.txt"
        content = "line1\nline2\nline3\nline4\nline5\n"
        test_file.write_text(content, encoding="utf-8")

        # Read different sections
        result1 = read_file_partial(str(test_file), 1, 2)
        result2 = read_file_partial(str(test_file), 3, 4)
        result3 = read_file_partial(str(test_file), 5, 5)

        assert result1 == "line1\nline2\n"
        assert result2 == "line3\nline4\n"
        assert result3 == "line5\n"

    def test_read_partial_with_columns_and_newlines(self, tmp_path):
        """Test column extraction with different newline types."""
        test_file = tmp_path / "test.txt"
        content = "abc\r\ndef\nghi\r"
        test_file.write_text(content, encoding="utf-8")

        result = read_file_partial(str(test_file), 1, 3, 1, 2)
        # Note: encoding_utils normalizes newlines to \n
        # Check that we get content from specified column range
        assert "bc" in result or "de" in result or "hi" in result
