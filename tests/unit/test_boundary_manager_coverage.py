#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.security.boundary_manager module

Comprehensive tests for ProjectBoundaryManager class.
"""

import os
from pathlib import Path

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security.boundary_manager import ProjectBoundaryManager


class TestProjectBoundaryManagerInit:
    """Tests for ProjectBoundaryManager initialization"""

    def test_init_with_valid_path(self, tmp_path):
        """Test initialization with valid path"""
        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.project_root == str(tmp_path.resolve())
        assert str(tmp_path.resolve()) in manager.allowed_directories

    def test_init_with_empty_path_raises_error(self):
        """Test initialization with empty path raises SecurityError"""
        with pytest.raises(SecurityError, match="Project root cannot be empty"):
            ProjectBoundaryManager("")

    def test_init_with_none_path_raises_error(self):
        """Test initialization with None raises SecurityError"""
        with pytest.raises(SecurityError, match="Project root cannot be empty"):
            ProjectBoundaryManager(None)

    def test_init_with_nonexistent_path_raises_error(self):
        """Test initialization with nonexistent path raises SecurityError"""
        with pytest.raises(SecurityError, match="Project root does not exist"):
            ProjectBoundaryManager("/nonexistent/path/that/does/not/exist")

    def test_init_with_file_path_raises_error(self, tmp_path):
        """Test initialization with file path raises SecurityError"""
        file_path = tmp_path / "test_file.txt"
        file_path.write_text("test")

        with pytest.raises(SecurityError, match="Project root is not a directory"):
            ProjectBoundaryManager(str(file_path))

    def test_init_with_invalid_type_raises_error(self, tmp_path):
        """Test initialization with invalid type raises SecurityError"""
        # Passing a Path object directly instead of string
        with pytest.raises(SecurityError, match="Invalid project root type"):
            ProjectBoundaryManager(tmp_path)


class TestAddAllowedDirectory:
    """Tests for add_allowed_directory method"""

    def test_add_valid_directory(self, tmp_path):
        """Test adding a valid directory"""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        manager = ProjectBoundaryManager(str(tmp_path))
        manager.add_allowed_directory(str(subdir))

        assert str(subdir.resolve()) in manager.allowed_directories

    def test_add_empty_directory_raises_error(self, tmp_path):
        """Test adding empty string raises SecurityError"""
        manager = ProjectBoundaryManager(str(tmp_path))

        with pytest.raises(SecurityError, match="Directory cannot be empty"):
            manager.add_allowed_directory("")

    def test_add_nonexistent_directory_raises_error(self, tmp_path):
        """Test adding nonexistent directory raises SecurityError"""
        manager = ProjectBoundaryManager(str(tmp_path))

        with pytest.raises(SecurityError, match="Directory does not exist"):
            manager.add_allowed_directory("/nonexistent/directory")

    def test_add_file_as_directory_raises_error(self, tmp_path):
        """Test adding file as directory raises SecurityError"""
        file_path = tmp_path / "test_file.txt"
        file_path.write_text("test")

        manager = ProjectBoundaryManager(str(tmp_path))

        with pytest.raises(SecurityError, match="Path is not a directory"):
            manager.add_allowed_directory(str(file_path))


class TestIsWithinProject:
    """Tests for is_within_project method"""

    def test_file_within_project(self, tmp_path):
        """Test file within project returns True"""
        file_path = tmp_path / "test.py"
        file_path.write_text("test")

        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.is_within_project(str(file_path)) is True

    def test_file_outside_project(self, tmp_path):
        """Test file outside project returns False"""
        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.is_within_project("/etc/passwd") is False

    def test_empty_path_returns_false(self, tmp_path):
        """Test empty path returns False"""
        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.is_within_project("") is False

    def test_file_in_allowed_directory(self, tmp_path):
        """Test file in allowed directory returns True"""
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        file_path = other_dir / "test.py"
        file_path.write_text("test")

        manager = ProjectBoundaryManager(str(tmp_path))
        manager.add_allowed_directory(str(other_dir))

        assert manager.is_within_project(str(file_path)) is True


class TestGetRelativePath:
    """Tests for get_relative_path method"""

    def test_relative_path_within_project(self, tmp_path):
        """Test relative path for file within project"""
        subdir = tmp_path / "src"
        subdir.mkdir()
        file_path = subdir / "test.py"
        file_path.write_text("test")

        manager = ProjectBoundaryManager(str(tmp_path))
        rel_path = manager.get_relative_path(str(file_path))

        assert rel_path is not None
        assert rel_path == str(Path("src") / "test.py")

    def test_relative_path_outside_project(self, tmp_path):
        """Test relative path for file outside project returns None"""
        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.get_relative_path("/etc/passwd") is None


class TestValidateAndResolvePath:
    """Tests for validate_and_resolve_path method"""

    def test_validate_absolute_path_within_project(self, tmp_path):
        """Test validating absolute path within project"""
        file_path = tmp_path / "test.py"
        file_path.write_text("test")

        manager = ProjectBoundaryManager(str(tmp_path))
        resolved = manager.validate_and_resolve_path(str(file_path))

        assert resolved is not None
        assert resolved == str(file_path.resolve())

    def test_validate_relative_path_within_project(self, tmp_path):
        """Test validating relative path within project"""
        file_path = tmp_path / "test.py"
        file_path.write_text("test")

        manager = ProjectBoundaryManager(str(tmp_path))
        resolved = manager.validate_and_resolve_path("test.py")

        assert resolved is not None

    def test_validate_path_outside_project(self, tmp_path):
        """Test validating path outside project returns None"""
        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.validate_and_resolve_path("/etc/passwd") is None


class TestListAllowedDirectories:
    """Tests for list_allowed_directories method"""

    def test_list_allowed_directories(self, tmp_path):
        """Test listing allowed directories"""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        manager = ProjectBoundaryManager(str(tmp_path))
        manager.add_allowed_directory(str(subdir))

        allowed = manager.list_allowed_directories()
        assert len(allowed) == 2
        assert str(tmp_path.resolve()) in allowed
        assert str(subdir.resolve()) in allowed


class TestIsSymlinkSafe:
    """Tests for is_symlink_safe method"""

    def test_nonexistent_file_is_safe(self, tmp_path):
        """Test nonexistent file is considered safe"""
        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.is_symlink_safe(str(tmp_path / "nonexistent.py")) is True

    def test_regular_file_is_safe(self, tmp_path):
        """Test regular file is considered safe"""
        file_path = tmp_path / "test.py"
        file_path.write_text("test")

        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.is_symlink_safe(str(file_path)) is True

    @pytest.mark.skipif(
        os.name == "nt", reason="Symlinks may require elevated privileges on Windows"
    )
    def test_safe_symlink_within_project(self, tmp_path):
        """Test symlink within project is safe"""
        target = tmp_path / "target.py"
        target.write_text("test")
        link = tmp_path / "link.py"
        link.symlink_to(target)

        manager = ProjectBoundaryManager(str(tmp_path))
        assert manager.is_symlink_safe(str(link)) is True


class TestAuditAccess:
    """Tests for audit_access method"""

    def test_audit_allowed_access(self, tmp_path):
        """Test auditing allowed file access"""
        file_path = tmp_path / "test.py"
        file_path.write_text("test")

        manager = ProjectBoundaryManager(str(tmp_path))
        # Should not raise
        manager.audit_access(str(file_path), "read")

    def test_audit_denied_access(self, tmp_path):
        """Test auditing denied file access"""
        manager = ProjectBoundaryManager(str(tmp_path))
        # Should not raise
        manager.audit_access("/etc/passwd", "read")


class TestStringRepresentations:
    """Tests for __str__ and __repr__ methods"""

    def test_str_representation(self, tmp_path):
        """Test string representation"""
        manager = ProjectBoundaryManager(str(tmp_path))
        str_repr = str(manager)

        assert "ProjectBoundaryManager" in str_repr
        assert "root=" in str_repr
        assert "allowed_dirs=" in str_repr

    def test_repr_representation(self, tmp_path):
        """Test repr representation"""
        manager = ProjectBoundaryManager(str(tmp_path))
        repr_str = repr(manager)

        assert "ProjectBoundaryManager" in repr_str
        assert "project_root=" in repr_str
        assert "allowed_directories=" in repr_str
