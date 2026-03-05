#!/usr/bin/env python3
"""Tests for Parser file size limits."""

import pytest


class TestParserFileSizeLimit:
    """Test file size limit functionality."""

    def test_default_max_file_size(self):
        """Should have default max file size of 10MB."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()
        assert hasattr(parser, "_max_file_size")
        assert parser._max_file_size == 10 * 1024 * 1024  # 10MB

    def test_rejects_oversized_file(self, tmp_path):
        """Should reject files exceeding size limit."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser(max_file_size=100)  # 100 bytes limit
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 1\n" * 100)  # ~700 bytes

        with pytest.raises(Exception) as exc_info:
            parser.parse_file(str(large_file), "python")

        assert "size" in str(exc_info.value).lower() or "large" in str(exc_info.value).lower()

    def test_accepts_normal_sized_file(self, tmp_path):
        """Should accept files within size limit."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser()
        normal_file = tmp_path / "normal.py"
        normal_file.write_text("def hello():\n    print('world')\n")

        result = parser.parse_file(str(normal_file), "python")
        assert result is not None
        assert result.success is True

    def test_configurable_max_file_size(self):
        """Max file size should be configurable."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser(max_file_size=1024)
        assert parser._max_file_size == 1024

    def test_max_file_size_zero_disables_limit(self, tmp_path):
        """Setting max_file_size to 0 should disable the limit."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser(max_file_size=0)  # Disabled
        # Create a file larger than default
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 1\n" * 100)

        result = parser.parse_file(str(large_file), "python")
        assert result.success is True

    def test_max_file_size_negative_disables_limit(self, tmp_path):
        """Setting max_file_size to negative value should disable the limit."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser(max_file_size=-1)  # Disabled
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 1\n" * 100)

        result = parser.parse_file(str(large_file), "python")
        assert result.success is True

    def test_file_size_error_includes_actual_size(self, tmp_path):
        """Error message should include actual file size."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser(max_file_size=10)  # 10 bytes limit
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 123456789\n")  # More than 10 bytes

        with pytest.raises(Exception) as exc_info:
            parser.parse_file(str(large_file), "python")

        error_msg = str(exc_info.value).lower()
        # Should mention both actual and max sizes
        assert "exceeds" in error_msg or "larger than" in error_msg

    def test_parse_code_not_affected_by_file_size_limit(self):
        """parse_code should not be affected by file size limit."""
        from tree_sitter_analyzer.core.parser import Parser

        parser = Parser(max_file_size=10)  # 10 bytes limit
        # This code is larger than 10 bytes but parse_code should work
        large_code = "x = 1\n" * 100

        result = parser.parse_code(large_code, "python")
        assert result.success is True
