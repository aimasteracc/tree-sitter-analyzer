#!/usr/bin/env python3
"""
Tests for ProjectBoundaryManager class.
"""

import os
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
        self.test_subdir = os.path.join(self.temp_dir, "src")
        os.makedirs(self.test_subdir, exist_ok=True)
        
        self.test_file = os.path.join(self.test_subdir, "test.py")
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
        assert self.manager.project_root == os.path.realpath(self.temp_dir)
        assert os.path.realpath(self.temp_dir) in self.manager.allowed_directories

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
            assert os.path.realpath(new_dir) in self.manager.allowed_directories
            
            # Test file in new directory is allowed
            test_file = os.path.join(new_dir, "test.txt")
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
        assert rel_path == os.path.join("src", "test.py")

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
        relative_path = os.path.join("src", "test.py")
        
        # Act
        resolved = self.manager.validate_and_resolve_path(relative_path)
        
        # Assert
        assert resolved is not None
        assert resolved == os.path.realpath(self.test_file)

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
        assert os.path.realpath(self.temp_dir) in directories

    @pytest.mark.unit
    def test_is_symlink_safe_no_symlinks(self):
        """Test symlink safety check for regular file."""
        # Act
        is_safe = self.manager.is_symlink_safe(self.test_file)
        
        # Assert
        assert is_safe is True

    @pytest.mark.unit
    def test_is_symlink_safe_nonexistent(self):
        """Test symlink safety check for nonexistent file."""
        # Arrange
        nonexistent = os.path.join(self.temp_dir, "nonexistent.txt")
        
        # Act
        is_safe = self.manager.is_symlink_safe(nonexistent)
        
        # Assert
        assert is_safe is True

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
        # Check that the realpath representation of temp_dir is in repr (handles Windows 8.3 paths)
        expected_path = os.path.realpath(self.temp_dir)
        assert expected_path in repr_repr
