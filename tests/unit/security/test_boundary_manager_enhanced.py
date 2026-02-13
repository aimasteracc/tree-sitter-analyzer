#!/usr/bin/env python3
"""
Enhanced tests for ProjectBoundaryManager class - coverage gaps.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security import ProjectBoundaryManager

# Skip symlink tests on Windows when symlinks may fail (no admin/developer mode)
SKIP_SYMLINK_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Symlink creation may require admin/developer mode on Windows",
)


class TestProjectBoundaryManagerEnhanced:
    """Enhanced test suite for ProjectBoundaryManager - coverage gaps."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = ProjectBoundaryManager(self.temp_dir)
        self.test_subdir = str(Path(self.temp_dir) / "src")
        Path(self.test_subdir).mkdir(parents=True, exist_ok=True)
        self.test_file = str(Path(self.test_subdir) / "test.py")
        with open(self.test_file, "w") as f:
            f.write("# test file")

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.unit
    def test_init_with_non_string_root_raises_security_error(self):
        """__init__ with non-string root (e.g. int) should raise SecurityError."""
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager(123)
        msg = str(exc_info.value)
        assert "Invalid project root type" in msg or (
            "Failed to initialize" in msg and "int" in msg
        )

    @pytest.mark.unit
    def test_init_with_path_object_raises_security_error(self):
        """__init__ with Path object (non-str) should raise SecurityError."""
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager(Path(self.temp_dir))
        assert "Invalid project root type" in str(exc_info.value)

    @pytest.mark.unit
    def test_init_with_none_raises_security_error(self):
        """__init__ with None should raise (empty check)."""
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager(None)
        assert "cannot be empty" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_init_with_file_path_instead_of_directory(self):
        """__init__ with file path instead of directory should raise SecurityError."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            file_path = f.name
        try:
            with pytest.raises(SecurityError) as exc_info:
                ProjectBoundaryManager(file_path)
            assert "not a directory" in str(exc_info.value)
        finally:
            os.unlink(file_path)

    @pytest.mark.unit
    def test_init_exception_path_wrapped_in_security_error(self):
        """__init__ generic exception should be wrapped in SecurityError."""
        with patch("pathlib.Path.exists", side_effect=RuntimeError("Mock error")):
            with pytest.raises(SecurityError) as exc_info:
                ProjectBoundaryManager(self.temp_dir)
            assert "Failed to initialize ProjectBoundaryManager" in str(exc_info.value)
            assert "Mock error" in str(exc_info.value)

    @pytest.mark.unit
    def test_add_allowed_directory_empty_string(self):
        """add_allowed_directory with empty string should raise SecurityError."""
        with pytest.raises(SecurityError) as exc_info:
            self.manager.add_allowed_directory("")
        assert "cannot be empty" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_add_allowed_directory_with_relative_path(self):
        """add_allowed_directory resolves relative paths to absolute."""
        nested = Path(self.temp_dir) / "nested" / "sub"
        nested.mkdir(parents=True, exist_ok=True)
        # Pass relative path - Path resolves it from current working directory
        orig_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            self.manager.add_allowed_directory("nested/sub")
            abs_path = str(nested.resolve())
            assert abs_path in self.manager.allowed_directories
        finally:
            os.chdir(orig_cwd)

    @pytest.mark.unit
    def test_add_allowed_directory_file_instead_of_dir(self):
        """add_allowed_directory with file path should raise SecurityError."""
        with pytest.raises(SecurityError) as exc_info:
            self.manager.add_allowed_directory(self.test_file)
        assert "not a directory" in str(exc_info.value)

    @pytest.mark.unit
    def test_is_within_project_with_path_traversal_components(self):
        """is_within_project with .. in path - traversal outside boundaries."""
        # Path like ".." when we're in a subdir could resolve outside
        outside_traversal = str(Path(self.temp_dir) / "src" / ".." / ".." / "..")
        # Resolve it - may point outside temp
        resolved = str(Path(outside_traversal).resolve())
        result = self.manager.is_within_project(outside_traversal)
        # Should be False if resolved path is outside temp_dir
        assert result is False or Path(resolved) == Path(self.temp_dir).resolve()

    @pytest.mark.unit
    def test_get_relative_path_with_dotdot_in_result(self):
        """get_relative_path when path is in allowed dir but yields .. from project_root."""
        # Add sibling directory as allowed
        sibling = tempfile.mkdtemp(dir=Path(self.temp_dir).parent)
        try:
            self.manager.add_allowed_directory(sibling)
            sibling_file = str(Path(sibling) / "file.txt")
            with open(sibling_file, "w") as f:
                f.write("x")
            # Path is within allowed dirs (sibling) but relative_to(project_root) = ../sibling/file.txt
            rel = self.manager.get_relative_path(sibling_file)
            assert rel is None
        finally:
            shutil.rmtree(sibling, ignore_errors=True)

    @pytest.mark.unit
    @SKIP_SYMLINK_WIN
    def test_is_symlink_safe_with_symlink_escaping_project(self):
        """is_symlink_safe with symlink pointing outside project."""
        outside_dir = tempfile.mkdtemp(dir=Path(self.temp_dir).parent)
        try:
            link_in_project = str(Path(self.temp_dir) / "escaped_link")
            os.symlink(outside_dir, link_in_project)
            is_safe = self.manager.is_symlink_safe(link_in_project)
            assert is_safe is False
        finally:
            if os.path.exists(link_in_project):
                os.unlink(link_in_project)
            shutil.rmtree(outside_dir, ignore_errors=True)

    @pytest.mark.unit
    @SKIP_SYMLINK_WIN
    def test_is_symlink_safe_with_symlink_within_project(self):
        """is_symlink_safe with symlink pointing inside project should be safe."""
        inner_dir = str(Path(self.temp_dir) / "inner")
        Path(inner_dir).mkdir(exist_ok=True)
        link_path = str(Path(self.temp_dir) / "safe_link")
        try:
            os.symlink(inner_dir, link_path)
            is_safe = self.manager.is_symlink_safe(link_path)
            assert is_safe is True
        finally:
            if os.path.exists(link_path):
                os.unlink(link_path)

    @pytest.mark.unit
    def test_audit_access_with_different_operations(self):
        """audit_access with various operation types."""
        for op in ("read", "write", "analyze", "delete", "execute"):
            self.manager.audit_access(self.test_file, op)
        # Denied path
        self.manager.audit_access("/etc/passwd", "read")

    @pytest.mark.unit
    def test_validate_and_resolve_path_nonexistent_file(self):
        """validate_and_resolve_path with non-existent file (within bounds)."""
        nonexistent = str(Path(self.temp_dir) / "missing.py")
        resolved = self.manager.validate_and_resolve_path(nonexistent)
        assert resolved is not None
        assert "missing.py" in resolved

    @pytest.mark.unit
    def test_validate_and_resolve_path_traversal_attempt(self):
        """validate_and_resolve_path rejects traversal outside."""
        resolved = self.manager.validate_and_resolve_path("../../../etc/passwd")
        assert resolved is None

    @pytest.mark.unit
    def test_validate_and_resolve_path_relative_within_project(self):
        """validate_and_resolve_path with relative path within project."""
        rel = str(Path("src") / "test.py")
        resolved = self.manager.validate_and_resolve_path(rel)
        assert resolved == str(Path(self.test_file).resolve())

    @pytest.mark.unit
    def test_multiple_allowed_directories_access_each(self):
        """Add several allowed dirs and test access to each."""
        dirs = []
        for i in range(3):
            d = tempfile.mkdtemp(dir=Path(self.temp_dir).parent)
            dirs.append(d)
            self.manager.add_allowed_directory(d)
        try:
            for d in dirs:
                f = str(Path(d) / "f.txt")
                with open(f, "w") as fp:
                    fp.write("x")
                assert self.manager.is_within_project(f)
        finally:
            for d in dirs:
                shutil.rmtree(d, ignore_errors=True)

    @pytest.mark.unit
    def test_is_within_project_with_none_path(self):
        """is_within_project with None-like empty handling."""
        result = self.manager.is_within_project("")
        assert result is False

    @pytest.mark.unit
    def test_get_relative_path_within_subdir(self):
        """get_relative_path for nested path."""
        nested = str(Path(self.temp_dir) / "a" / "b" / "c.py")
        Path(nested).parent.mkdir(parents=True, exist_ok=True)
        with open(nested, "w") as f:
            f.write("#")
        rel = self.manager.get_relative_path(nested)
        assert rel == str(Path("a") / "b" / "c.py")

    @pytest.mark.unit
    def test_list_allowed_directories_returns_copy(self):
        """list_allowed_directories returns a copy, not the internal set."""
        dirs = self.manager.list_allowed_directories()
        dirs.add("/some/other")
        assert "/some/other" not in self.manager.allowed_directories

    @pytest.mark.unit
    def test_str_and_repr(self):
        """String and repr representations."""
        s = str(self.manager)
        r = repr(self.manager)
        assert "ProjectBoundaryManager" in s
        assert "ProjectBoundaryManager" in r
        assert "allowed_dirs" in s or "allowed" in r.lower()
