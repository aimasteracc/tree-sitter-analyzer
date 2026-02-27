#!/usr/bin/env python3
"""
Tests for SecurityValidator class.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security import SecurityValidator


class TestSecurityValidator:
    """Test suite for SecurityValidator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.validator = SecurityValidator(self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.unit
    def test_validate_file_path_success(self):
        """Test successful file path validation."""
        # Arrange
        valid_path = "src/main.py"

        # Act
        is_valid, error = self.validator.validate_file_path(valid_path, self.temp_dir)

        # Assert
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    def test_validate_file_path_empty_string(self):
        """Test validation fails for empty string."""
        # Arrange
        invalid_path = ""

        # Act
        is_valid, error = self.validator.validate_file_path(invalid_path)

        # Assert
        assert not is_valid
        assert "non-empty string" in error

    @pytest.mark.unit
    def test_validate_file_path_null_bytes(self):
        """Test validation fails for null bytes."""
        # Arrange
        invalid_path = "src/main\x00.py"

        # Act
        is_valid, error = self.validator.validate_file_path(invalid_path)

        # Assert
        assert not is_valid
        assert "null bytes" in error

    @pytest.mark.unit
    def test_validate_file_path_absolute_path(self):
        """Test validation fails for absolute paths."""
        # Arrange
        invalid_path = "/etc/passwd"

        # Act
        is_valid, error = self.validator.validate_file_path(invalid_path)

        # Assert
        assert not is_valid
        assert "Absolute" in error and (
            "not allowed" in error or "within project" in error
        )

    @pytest.mark.unit
    def test_validate_file_path_windows_drive(self):
        """Test validation fails for Windows drive letters."""
        # Arrange
        invalid_path = "C:\\Windows\\System32"

        # Act
        is_valid, error = self.validator.validate_file_path(invalid_path)

        # Assert
        assert not is_valid
        assert ("drive" in error.lower() and "not allowed" in error.lower()) or (
            "absolute" in error.lower() and "project" in error.lower()
        )

    @pytest.mark.unit
    def test_validate_file_path_traversal_attack(self):
        """Test validation fails for path traversal attempts."""
        # Arrange
        traversal_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\Windows\\System32",
            "src/../../../etc/passwd",
            "src\\..\\..\\..\\Windows\\System32",
        ]

        for invalid_path in traversal_paths:
            # Act
            is_valid, error = self.validator.validate_file_path(invalid_path)

            # Assert
            assert not is_valid, f"Path should be invalid: {invalid_path}"
            assert "traversal" in error.lower()

    @pytest.mark.unit
    def test_validate_directory_path_success(self):
        """Test successful directory path validation."""
        # Arrange
        valid_dir = "src"

        # Act
        is_valid, error = self.validator.validate_directory_path(
            valid_dir, must_exist=False
        )

        # Assert
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    def test_validate_directory_path_must_exist(self):
        """Test directory validation when directory must exist."""
        # Arrange
        nonexistent_dir = "nonexistent_directory"

        # Act
        is_valid, error = self.validator.validate_directory_path(
            nonexistent_dir, must_exist=True
        )

        # Assert
        assert not is_valid
        assert "does not exist" in error

    @pytest.mark.unit
    def test_validate_regex_pattern_success(self):
        """Test successful regex pattern validation."""
        # Arrange
        safe_pattern = r"hello.*world"

        # Act
        is_valid, error = self.validator.validate_regex_pattern(safe_pattern)

        # Assert
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    def test_sanitize_input_success(self):
        """Test successful input sanitization."""
        # Arrange
        clean_input = "hello world"

        # Act
        result = self.validator.sanitize_input(clean_input)

        # Assert
        assert result == clean_input

    @pytest.mark.unit
    def test_sanitize_input_removes_control_chars(self):
        """Test input sanitization removes control characters."""
        # Arrange
        dirty_input = "hello\x00\x01world\x7f"

        # Act
        result = self.validator.sanitize_input(dirty_input)

        # Assert
        assert result == "helloworld"

    @pytest.mark.unit
    def test_sanitize_input_too_long(self):
        """Test sanitization fails for too long input."""
        # Arrange
        long_input = "a" * 2000

        # Act & Assert
        with pytest.raises(SecurityError) as exc_info:
            self.validator.sanitize_input(long_input, max_length=1000)

        assert "too long" in str(exc_info.value)

    @pytest.mark.unit
    def test_validate_glob_pattern_success(self):
        """Test successful glob pattern validation."""
        # Arrange
        safe_pattern = "*.py"

        # Act
        is_valid, error = self.validator.validate_glob_pattern(safe_pattern)

        # Assert
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    def test_validate_glob_pattern_dangerous(self):
        """Test glob pattern validation fails for dangerous patterns."""
        # Arrange
        dangerous_patterns = [
            "../*.py",
            "src///*.py",
            "src\\\\*.py",
        ]

        for pattern in dangerous_patterns:
            # Act
            is_valid, error = self.validator.validate_glob_pattern(pattern)

            # Assert
            assert not is_valid, f"Pattern should be invalid: {pattern}"
            assert "Dangerous pattern detected" in error

    @pytest.mark.unit
    def test_validator_without_project_root(self):
        """Test validator works without project root."""
        # Arrange
        validator = SecurityValidator()

        # Act
        is_valid, error = validator.validate_file_path("src/main.py")

        # Assert
        assert is_valid  # Should pass basic validation without boundary checks


class TestValidatorEdgeCases:
    """Tests for edge cases and additional code paths merged from variant files."""

    @pytest.mark.unit
    def test_validate_file_path_none(self):
        """Test validation fails for None path."""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path(None)
        assert not is_valid
        assert "non-empty" in error

    @pytest.mark.unit
    def test_validate_file_path_non_string(self):
        """Test validation fails for non-string path."""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path(123)
        assert not is_valid
        assert "non-empty" in error

    @pytest.mark.unit
    def test_validate_file_path_exception_handling(self):
        """Test validation handles internal exceptions gracefully."""
        validator = SecurityValidator()
        with patch.object(
            validator,
            "_validate_windows_drive_letter",
            side_effect=Exception("Test error"),
        ):
            is_valid, error = validator.validate_file_path("test.py")
            assert not is_valid
            assert "Validation error" in error

    @pytest.mark.unit
    def test_validate_file_path_symlink(self):
        """Test validation detects symbolic links."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target.txt"
            target.touch()
            symlink = Path(temp_dir) / "link.txt"
            try:
                symlink.symlink_to(target)
                validator = SecurityValidator()
                is_valid, error = validator.validate_file_path(str(symlink))
                assert not is_valid
                assert "symbolic link" in error.lower()
            except OSError:
                pytest.skip("Symlink creation not supported")

    @pytest.mark.unit
    def test_sanitize_input_html_tags(self):
        """Test input sanitization strips HTML tags."""
        validator = SecurityValidator()
        result = validator.sanitize_input("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "alert" in result

    @pytest.mark.unit
    def test_sanitize_input_dangerous_chars(self):
        """Test input sanitization strips dangerous characters."""
        validator = SecurityValidator()
        result = validator.sanitize_input('test"><script>alert')
        assert ">" not in result
        assert "'" not in result

    @pytest.mark.unit
    def test_sanitize_input_non_string(self):
        """Test sanitization raises SecurityError for non-string input."""
        validator = SecurityValidator()
        with pytest.raises(SecurityError):
            validator.sanitize_input(123)

    @pytest.mark.unit
    def test_validate_path_alias(self):
        """Test validate_path alias method delegates correctly."""
        validator = SecurityValidator()
        is_valid, error = validator.validate_path("src/main.py")
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    def test_is_safe_path_valid(self):
        """Test is_safe_path returns True for safe path."""
        validator = SecurityValidator()
        assert validator.is_safe_path("src/main.py") is True

    @pytest.mark.unit
    def test_is_safe_path_invalid(self):
        """Test is_safe_path returns False for unsafe path."""
        validator = SecurityValidator()
        assert validator.is_safe_path("../etc/passwd") is False
