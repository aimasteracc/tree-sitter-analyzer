#!/usr/bin/env python3
"""
Tests for SecurityValidator class.
"""

import os
import tempfile
from pathlib import Path

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
        assert "Absolute" in error and ("not allowed" in error or "within project" in error)

    @pytest.mark.unit
    def test_validate_file_path_windows_drive(self):
        """Test validation fails for Windows drive letters."""
        # Arrange
        invalid_path = "C:\\Windows\\System32"
        
        # Act
        is_valid, error = self.validator.validate_file_path(invalid_path)
        
        # Assert
        assert not is_valid
        assert ("drive" in error.lower() and "not allowed" in error.lower()) or ("absolute" in error.lower() and "project" in error.lower())

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
        is_valid, error = self.validator.validate_directory_path(valid_dir, must_exist=False)
        
        # Assert
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    def test_validate_directory_path_must_exist(self):
        """Test directory validation when directory must exist."""
        # Arrange
        nonexistent_dir = "nonexistent_directory"
        
        # Act
        is_valid, error = self.validator.validate_directory_path(nonexistent_dir, must_exist=True)
        
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
