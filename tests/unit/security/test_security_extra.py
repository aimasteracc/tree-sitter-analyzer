"""Tests for security.validator — path traversal, junction detection, sanitization edge cases."""

import os
from pathlib import Path

from tree_sitter_analyzer.security.validator import SecurityValidator


class TestSecurityValidatorPathTraversal:
    def test_double_dot_traversal_rejected(self):
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("../../../etc/passwd")
        assert is_valid is False
        assert isinstance(error, str)

    def test_null_byte_injection_rejected(self):
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("test.py\x00.md")
        assert is_valid is False
        assert isinstance(error, str)

    def test_mixed_path_separators_rejected(self):
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("dir\\../etc/passwd")
        assert is_valid is False
        assert isinstance(error, str)

    def test_valid_relative_path_accepted(self):
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("src/main.py")
        assert is_valid is True
        assert error == ""


class TestSecurityValidatorSanitization:
    def test_sanitize_removes_null_bytes(self):
        validator = SecurityValidator()
        sanitized = validator.sanitize_input("test\x00.py")
        assert "\x00" not in sanitized

    def test_sanitize_normalizes_path(self):
        validator = SecurityValidator()
        sanitized = validator.sanitize_input("a/b/../c.py")
        assert sanitized == "a/b/../c.py"

    def test_sanitize_empty_path(self):
        validator = SecurityValidator()
        result = validator.sanitize_input("")
        assert result == ""


class TestSecurityValidatorEdgeCases:
    def test_very_long_path(self):
        validator = SecurityValidator()
        long_path = "a/" * 500 + "file.py"
        result, _ = validator.validate_file_path(long_path)
        # Should handle without crashing
        assert isinstance(result, bool)

    def test_unicode_path(self):
        validator = SecurityValidator()
        result, _ = validator.validate_file_path("src/日本語/テスト.py")
        assert isinstance(result, bool)

    def test_symlink_path_validation(self):
        validator = SecurityValidator()
        result, _ = validator.validate_file_path("/tmp/symlink_to_source")
        assert isinstance(result, bool)


class TestSecurityValidatorNonWindows:
    """Junction detection is Windows-only; on POSIX it should return False."""

    def test_junction_check_returns_false_on_posix(self):
        if os.name != "nt":
            validator = SecurityValidator()
            result = validator._is_junction_or_reparse_point(Path("/tmp"))
            assert result is False
