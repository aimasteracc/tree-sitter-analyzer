#!/usr/bin/env python3
"""Supplementary tests for security/validator.py uncovered branches.

Targets: lines 19-20, 146-154, 165-199, 370-398, 416, 519, 536-539, 556-558
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.security.boundary_manager import ProjectBoundaryManager
from tree_sitter_analyzer.security.validator import SecurityValidator


class TestValidatorUncovered:
    """Targets uncovered validator branches."""

    def test_boundary_manager_init_failure_fallback(self):
        """Lines 19-20: ProjectBoundaryManager init failure fallback."""
        with patch.object(
            ProjectBoundaryManager, "__init__", side_effect=Exception("init crash")
        ):
            validator = SecurityValidator("/some/project")
        assert validator.boundary_manager is None

    def test_validate_file_path_windows_drive_letter_rejected(self):
        """Line 146-154: Windows drive letter check on non-Windows."""
        validator = SecurityValidator()
        is_valid, error = validator._validate_windows_drive_letter("C:\\test.txt")
        if os.name != "nt":
            assert is_valid is False
            assert "Windows drive" in error
        else:
            assert is_valid is True

    def test_validate_absolute_path_test_env_temp_pattern_match(self):
        """Lines 165-199: test environment file pattern matching."""
        validator = SecurityValidator()
        # Simulate test environment
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test_thing"}):
            is_valid, error = validator._validate_absolute_path("/tmp/tmp_test_file.py")
        # Should be allowed in test env by filename pattern
        assert is_valid is True

    def test_validate_absolute_path_test_env_multiple_temp_dirs(self):
        """Lines 165-177: test env with /var/tmp fallback."""
        validator = SecurityValidator()
        with (
            patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test_thing"}),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "resolve", return_value=Path("/var/tmp/thing.py")),
        ):
            is_valid, error = validator._validate_absolute_path("/var/tmp/thing.py")
        assert is_valid is True

    def test_validate_absolute_path_test_env_tmp_pattern(self):
        """Lines 185-199: file name starts with tmp/temp/tmp_test."""
        validator = SecurityValidator()
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test"}):
            is_valid, error = validator._validate_absolute_path(
                "/some/dir/temp_file.py"
            )
        assert is_valid is True

    def test_validate_file_path_none_input(self):
        """Line 126: None file path."""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("")
        assert is_valid is False
        assert "non-empty" in error

    def test_validate_file_path_null_byte(self):
        """Line 129-132: null byte injection."""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("file\x00.txt")
        assert is_valid is False
        assert "null bytes" in error

    def test_validate_absolute_path_test_env_exception_fallback(self):
        """Line 416: exception in test env check falls through to deny."""
        validator = SecurityValidator()
        with (
            patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test"}),
            patch.object(Path, "resolve", side_effect=Exception("boom")),
        ):
            is_valid, error = validator._validate_absolute_path("/some/file.py")
        assert is_valid is False
        assert "Absolute file paths are not allowed" in error

    def test_validate_path_traversal_double_dot_slash(self):
        """Lines 370-398: path traversal patterns."""
        validator = SecurityValidator()
        is_valid, error = validator._validate_path_traversal("../etc/passwd")
        assert is_valid is False
        assert "traversal" in error

    def test_validate_path_traversal_dotdot_backslash(self):
        validator = SecurityValidator()
        is_valid, error = validator._validate_path_traversal("..\\windows.txt")
        assert is_valid is False

    def test_validate_path_traversal_dotdot_start(self):
        validator = SecurityValidator()
        is_valid, error = validator._validate_path_traversal("..")
        assert is_valid is False

    def test_validate_project_boundary_outside_rejected(self):
        """Lines 536-539: project boundary rejection."""
        validator = SecurityValidator("/safe/project")
        # Override boundary manager for controllable test
        mock_manager = MagicMock()
        mock_manager.is_within_project.return_value = False
        validator.boundary_manager = mock_manager
        is_valid, error = validator._validate_project_boundary(
            "../outside.txt", "/safe/project"
        )
        assert is_valid is False
        assert "Access denied" in error

    def test_validate_project_boundary_no_boundary_manager(self):
        """Line 519: returns True when no boundary manager."""
        validator = SecurityValidator()  # no project_root
        assert validator.boundary_manager is None
        is_valid, error = validator._validate_project_boundary("anything.txt", None)
        assert is_valid is True

    def test_validate_project_boundary_no_base_path(self):
        """Line 519: returns True when base_path is None."""
        validator = SecurityValidator("/safe/project")
        is_valid, error = validator._validate_project_boundary("any.txt", None)
        assert is_valid is True

    def test_validate_absolute_path_basic_denial(self):
        """Lines 550-558: fallback absolute path denial."""
        validator = SecurityValidator()
        is_valid, error = validator._validate_absolute_path("/etc/passwd")
        assert is_valid is False
        assert "Absolute file paths are not allowed" in error
