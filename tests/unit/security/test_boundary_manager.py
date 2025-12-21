#!/usr/bin/env python3
"""
Tests for ProjectBoundaryManager class.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security import ProjectBoundaryManager


class TestProjectBoundaryManager:
    """Test suite for ProjectBoundaryManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = ProjectBoundaryManager(self.temp_dir)

        # Create test directory structure
        self.test_subdir = str(Path(self.temp_dir) / "src")
        Path(self.test_subdir).mkdir(parents=True, exist_ok=True)

        self.test_file = str(Path(self.test_subdir) / "test.py")
        with open(self.test_file, "w") as f:
            f.write("# test file")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.unit
    def test_init_success(self):
        """Test successful initialization."""
        # Assert
        assert self.manager.project_root == str(Path(self.temp_dir).resolve())
        assert str(Path(self.temp_dir).resolve()) in self.manager.allowed_directories

    @pytest.mark.unit
    def test_init_empty_root(self):
        """Test initialization fails with empty root."""
        # Act & Assert
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager("")

        assert "cannot be empty" in str(exc_info.value)

    @pytest.mark.unit
    def test_init_nonexistent_root(self):
        """Test initialization fails with nonexistent root."""
        # Act & Assert
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager("/nonexistent/directory")

        assert "does not exist" in str(exc_info.value)

    @pytest.mark.unit
    def test_is_within_project_success(self):
        """Test file within project boundaries."""
        # Act
        result = self.manager.is_within_project(self.test_file)

        # Assert
        assert result is True

    @pytest.mark.unit
    def test_is_within_project_outside(self):
        """Test file outside project boundaries."""
        # Arrange
        outside_file = "/etc/passwd"

        # Act
        result = self.manager.is_within_project(outside_file)

        # Assert
        assert result is False

    @pytest.mark.unit
    def test_is_within_project_empty_path(self):
        """Test empty path is outside boundaries."""
        # Act
        result = self.manager.is_within_project("")

        # Assert
        assert result is False

    @pytest.mark.unit
    def test_add_allowed_directory_success(self):
        """Test adding allowed directory."""
        # Arrange
        new_dir = tempfile.mkdtemp()

        try:
            # Act
            self.manager.add_allowed_directory(new_dir)

            # Assert
            assert str(Path(new_dir).resolve()) in self.manager.allowed_directories

            # Test file in new directory is allowed
            test_file = str(Path(new_dir) / "test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            assert self.manager.is_within_project(test_file)

        finally:
            import shutil

            shutil.rmtree(new_dir, ignore_errors=True)

    @pytest.mark.unit
    def test_add_allowed_directory_nonexistent(self):
        """Test adding nonexistent directory fails."""
        # Act & Assert
        with pytest.raises(SecurityError) as exc_info:
            self.manager.add_allowed_directory("/nonexistent/directory")

        assert "does not exist" in str(exc_info.value)

    @pytest.mark.unit
    def test_get_relative_path_success(self):
        """Test getting relative path for file within boundaries."""
        # Act
        rel_path = self.manager.get_relative_path(self.test_file)

        # Assert
        assert rel_path is not None
        assert rel_path == str(Path("src") / "test.py")

    @pytest.mark.unit
    def test_get_relative_path_outside(self):
        """Test getting relative path for file outside boundaries."""
        # Arrange
        outside_file = "/etc/passwd"

        # Act
        rel_path = self.manager.get_relative_path(outside_file)

        # Assert
        assert rel_path is None

    @pytest.mark.unit
    def test_validate_and_resolve_path_success(self):
        """Test validating and resolving path within boundaries."""
        # Arrange
        relative_path = str(Path("src") / "test.py")

        # Act
        resolved = self.manager.validate_and_resolve_path(relative_path)

        # Assert
        assert resolved is not None
        assert resolved == str(Path(self.test_file).resolve())

    @pytest.mark.unit
    def test_validate_and_resolve_path_outside(self):
        """Test validating path outside boundaries."""
        # Arrange
        outside_path = "../../../etc/passwd"

        # Act
        resolved = self.manager.validate_and_resolve_path(outside_path)

        # Assert
        assert resolved is None

    @pytest.mark.unit
    def test_list_allowed_directories(self):
        """Test listing allowed directories."""
        # Act
        directories = self.manager.list_allowed_directories()

        # Assert
        assert isinstance(directories, set)
        assert str(Path(self.temp_dir).resolve()) in directories

    @pytest.mark.unit
    def test_is_symlink_safe_no_symlinks(self):
        """Test symlink safety check for regular file."""
        # Act
        is_safe = self.manager.is_symlink_safe(self.test_file)

        # Assert
        # On some macOS runners, the temp project root may itself live under a
        # symlinked parent (e.g., /private/var/folders -> /var/folders). Our
        # implementation considers non-existent files safe and flags only
        # symlink components that resolve outside the project. For a regular
        # file created within the project, the check should pass.
        assert is_safe in (True,)

    @pytest.mark.unit
    def test_is_symlink_safe_nonexistent(self):
        """Test symlink safety check for nonexistent file."""
        # Arrange
        nonexistent = str(Path(self.temp_dir) / "nonexistent.txt")

        # Act
        is_safe = self.manager.is_symlink_safe(nonexistent)

        # Assert
        assert is_safe in (True,)

    @pytest.mark.unit
    def test_audit_access(self):
        """Test access auditing."""
        # Act - should not raise exception
        self.manager.audit_access(self.test_file, "read")
        self.manager.audit_access("/etc/passwd", "read")

    @pytest.mark.unit
    def test_string_representation(self):
        """Test string representations."""
        # Act
        str_repr = str(self.manager)
        repr_repr = repr(self.manager)

        # Assert
        assert "ProjectBoundaryManager" in str_repr
        assert "ProjectBoundaryManager" in repr_repr
        # On Windows the temp directory may have different short/long path
        # representations in CI (e.g., C:\Users\runneradmin vs C:\Users\RUNNER~1),
        # so we only assert that at least one of the known forms appears.
        normalized = str(Path(self.temp_dir).resolve())
        assert (
            self.temp_dir in repr_repr
            or normalized in repr_repr
            or Path(normalized).name in repr_repr
        )
