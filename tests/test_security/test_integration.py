#!/usr/bin/env python3
"""
Integration tests for security module.
"""

import os
import tempfile

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security import (
    ProjectBoundaryManager,
    RegexSafetyChecker,
    SecurityValidator,
)


class TestSecurityIntegration:
    """Integration test suite for security module."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = os.path.join(self.temp_dir, "project")
        os.makedirs(self.project_root, exist_ok=True)

        # Create test file structure
        self.src_dir = os.path.join(self.project_root, "src")
        os.makedirs(self.src_dir, exist_ok=True)

        self.test_file = os.path.join(self.src_dir, "main.py")
        with open(self.test_file, "w") as f:
            f.write("print('Hello, World!')")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.integration
    def test_complete_security_workflow(self):
        """Test complete security validation workflow."""
        # Arrange
        validator = SecurityValidator(self.project_root)

        # Act & Assert - Valid file path
        is_valid, error = validator.validate_file_path("src/main.py", self.project_root)
        assert is_valid
        assert error == ""

        # Act & Assert - Invalid path traversal
        is_valid, error = validator.validate_file_path(
            "../../../etc/passwd", self.project_root
        )
        assert not is_valid
        assert "traversal" in error.lower()

        # Act & Assert - Valid regex
        is_valid, error = validator.validate_regex_pattern(r"hello.*world")
        assert is_valid
        assert error == ""

        # Act & Assert - Dangerous regex
        is_valid, error = validator.validate_regex_pattern(r"(.+)+")
        assert not is_valid
        assert "dangerous" in error.lower()

    @pytest.mark.integration
    def test_boundary_manager_integration(self):
        """Test boundary manager integration with validator."""
        # Arrange
        boundary_manager = ProjectBoundaryManager(self.project_root)
        validator = SecurityValidator(self.project_root)

        # Act & Assert - File within boundaries
        assert boundary_manager.is_within_project(self.test_file)
        is_valid, _ = validator.validate_file_path("src/main.py", self.project_root)
        assert is_valid

        # Act & Assert - File outside boundaries
        outside_file = os.path.join(self.temp_dir, "outside.txt")
        with open(outside_file, "w") as f:
            f.write("outside content")

        assert not boundary_manager.is_within_project(outside_file)

    @pytest.mark.integration
    def test_regex_checker_integration(self):
        """Test regex checker integration with validator."""
        # Arrange
        checker = RegexSafetyChecker()
        validator = SecurityValidator()

        # Test safe pattern
        safe_pattern = r"[a-zA-Z0-9]+"
        is_safe, _ = checker.validate_pattern(safe_pattern)
        assert is_safe

        compiled = checker.create_safe_pattern(safe_pattern)
        assert compiled is not None

        # Test dangerous pattern
        dangerous_pattern = r"(.+)+"
        is_safe, _ = checker.validate_pattern(dangerous_pattern)
        assert not is_safe

        compiled = checker.create_safe_pattern(dangerous_pattern)
        assert compiled is None

    @pytest.mark.integration
    def test_security_exceptions_integration(self):
        """Test security exceptions are properly raised."""
        # Arrange
        validator = SecurityValidator()

        # Test SecurityError for input sanitization
        with pytest.raises(SecurityError) as exc_info:
            validator.sanitize_input("a" * 2000, max_length=100)

        assert "too long" in str(exc_info.value)

        # Test boundary manager exceptions
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager("")

        assert "cannot be empty" in str(exc_info.value)

    @pytest.mark.integration
    def test_multi_directory_boundary_control(self):
        """Test boundary control with multiple allowed directories."""
        # Arrange
        boundary_manager = ProjectBoundaryManager(self.project_root)

        # Add additional allowed directory
        extra_dir = os.path.join(self.temp_dir, "extra")
        os.makedirs(extra_dir, exist_ok=True)
        boundary_manager.add_allowed_directory(extra_dir)

        # Create file in extra directory
        extra_file = os.path.join(extra_dir, "extra.txt")
        with open(extra_file, "w") as f:
            f.write("extra content")

        # Act & Assert
        assert boundary_manager.is_within_project(self.test_file)  # Original project
        assert boundary_manager.is_within_project(extra_file)  # Extra directory

        # File outside both directories should be rejected
        outside_file = os.path.join(self.temp_dir, "outside.txt")
        with open(outside_file, "w") as f:
            f.write("outside content")

        assert not boundary_manager.is_within_project(outside_file)

    @pytest.mark.integration
    def test_comprehensive_path_validation(self):
        """Test comprehensive path validation with all security layers."""
        # Arrange
        validator = SecurityValidator(self.project_root)

        # Test cases with expected results
        test_cases = [
            # (path, base_path, should_be_valid, error_keyword)
            ("src/main.py", self.project_root, True, ""),
            ("", None, False, "non-empty"),
            ("src/test\x00.py", None, False, "null"),
            ("/etc/passwd", None, False, "Absolute"),
            ("C:\\Windows\\System32", None, False, "absolute"),
            ("../../../etc/passwd", None, False, "traversal"),
            ("src/../../../etc/passwd", None, False, "traversal"),
        ]

        for path, base_path, should_be_valid, error_keyword in test_cases:
            # Act
            is_valid, error = validator.validate_file_path(path, base_path)

            # Assert
            if should_be_valid:
                assert is_valid, f"Path should be valid: {path}"
                assert error == ""
            else:
                assert not is_valid, f"Path should be invalid: {path}"
                if error_keyword:
                    assert (
                        error_keyword.lower() in error.lower()
                    ), f"Expected '{error_keyword}' in error: {error}"

    @pytest.mark.integration
    def test_regex_performance_and_safety(self):
        """Test regex performance monitoring and safety checks."""
        # Arrange
        checker = RegexSafetyChecker()

        # Test performance with potentially slow patterns
        test_patterns = [
            (r"hello.*world", True),  # Fast and safe
            (r"(.+)+", False),  # Dangerous ReDoS pattern
            (r"(.*)*", False),  # Another dangerous pattern
            (r"[a-zA-Z0-9]+", True),  # Safe character class
            (r"(?=.*)", True),  # Lookahead (should be safe for short strings)
        ]

        for pattern, should_be_safe in test_patterns:
            # Act
            is_safe, error = checker.validate_pattern(pattern)

            # Assert
            if should_be_safe:
                assert is_safe, f"Pattern should be safe: {pattern}, error: {error}"
            else:
                assert not is_safe, f"Pattern should be dangerous: {pattern}"

    @pytest.mark.integration
    def test_audit_logging_integration(self):
        """Test audit logging functionality."""
        # Arrange
        boundary_manager = ProjectBoundaryManager(self.project_root)

        # Act - should not raise exceptions
        boundary_manager.audit_access(self.test_file, "read")
        boundary_manager.audit_access("/etc/passwd", "write")
        boundary_manager.audit_access("src/main.py", "analyze")

        # Assert - just verify no exceptions were raised
        assert True

    @pytest.mark.integration
    def test_symlink_safety_comprehensive(self):
        """Test comprehensive symlink safety checks."""
        # Arrange
        boundary_manager = ProjectBoundaryManager(self.project_root)

        # Test regular file (should be safe)
        assert boundary_manager.is_symlink_safe(self.test_file)

        # Test nonexistent file (should be safe)
        nonexistent = os.path.join(self.project_root, "nonexistent.txt")
        assert boundary_manager.is_symlink_safe(nonexistent)

        # Test directory (should be safe)
        assert boundary_manager.is_symlink_safe(self.src_dir)
