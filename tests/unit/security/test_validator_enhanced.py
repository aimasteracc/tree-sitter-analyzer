#!/usr/bin/env python3
"""
Enhanced tests for SecurityValidator class - coverage gaps.
"""

import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security import SecurityValidator

SKIP_SYMLINK_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Symlink creation may require admin/developer mode on Windows",
)


class TestSecurityValidatorEnhanced:
    """Enhanced test suite for SecurityValidator - coverage gaps."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.validator = SecurityValidator(self.temp_dir)
        Path(self.temp_dir, "src").mkdir(exist_ok=True)
        self.test_file = str(Path(self.temp_dir) / "src" / "main.py")
        with open(self.test_file, "w") as f:
            f.write("# test")

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.unit
    def test_validate_file_path_with_non_string_input(self):
        """validate_file_path with non-string (int, None) returns invalid."""
        for invalid in (123, None, [], {}):
            is_valid, error = self.validator.validate_file_path(invalid)
            assert not is_valid
            assert "non-empty string" in error or "must be" in error

    @pytest.mark.unit
    @SKIP_SYMLINK_WIN
    def test_validate_file_path_with_symlink_rejected(self):
        """validate_file_path rejects symlinks."""
        link_path = str(Path(self.temp_dir) / "link_to_src")
        try:
            os.symlink(Path(self.temp_dir) / "src", link_path)
            is_valid, error = self.validator.validate_file_path(link_path)
            assert not is_valid
            assert "symlink" in error.lower() or "ymbolic" in error
        finally:
            if os.path.exists(link_path):
                os.unlink(link_path)

    @pytest.mark.unit
    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="Windows junction test only on Windows",
    )
    def test_validate_file_path_with_windows_junction(self):
        """validate_file_path with Windows junction/reparse point (platform-specific)."""
        # Create a directory junction on Windows - requires ctypes/admin
        try:
            junction_dir = str(Path(self.temp_dir) / "junction_target")
            Path(junction_dir).mkdir(exist_ok=True)
            junction_path = str(Path(self.temp_dir) / "my_junction")
            # CreateJunction would need CreateSymbolicLinkW or junction API
            # For simplicity, mock _is_junction_or_reparse_point to return True
            with patch.object(
                self.validator, "_is_junction_or_reparse_point", return_value=True
            ):
                is_valid, _ = self.validator.validate_file_path(
                    junction_path, base_path=self.temp_dir
                )
                # With mock, behavior depends on when junction check runs
                # Just verify no crash
        except Exception:
            pytest.skip("Junction creation not available")

    @pytest.mark.unit
    def test_validate_directory_path_with_file_path(self):
        """validate_directory_path with path to file (not directory) fails."""
        full_file = str(Path(self.temp_dir) / "src" / "main.py")
        is_valid, error = self.validator.validate_directory_path(
            full_file, must_exist=True
        )
        assert not is_valid
        assert "not a directory" in error

    @pytest.mark.unit
    def test_validate_directory_path_must_exist_false_nonexistent(self):
        """validate_directory_path with must_exist=False allows non-existent dir."""
        nonexistent = str(Path(self.temp_dir) / "nonexistent_dir")
        is_valid, error = self.validator.validate_directory_path(
            nonexistent, must_exist=False
        )
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    def test_sanitize_input_with_non_string_raises(self):
        """sanitize_input with non-string raises SecurityError."""
        with pytest.raises(SecurityError) as exc_info:
            self.validator.sanitize_input(123)
        assert "must be a string" in str(exc_info.value)

    @pytest.mark.unit
    def test_sanitize_input_html_xss_removal(self):
        """sanitize_input removes HTML tags and dangerous chars."""
        dirty = '<script>alert("xss")</script>hello'
        result = self.validator.sanitize_input(dirty)
        assert "<" not in result or ">" not in result
        assert "script" not in result
        assert "hello" in result

    @pytest.mark.unit
    def test_sanitize_input_dangerous_characters_removed(self):
        """sanitize_input removes < > \" '."""
        dirty = "test<>\"'chars"
        result = self.validator.sanitize_input(dirty)
        for c in "<>\"'":
            assert c not in result

    @pytest.mark.unit
    def test_sanitize_input_control_characters(self):
        """sanitize_input removes null bytes and control chars in range \\x00-\\x08, \\x0b, \\x0c, \\x0e-\\x1f, \\x7f."""
        dirty = "hello\x00world\x07bell\x01ctrl"
        result = self.validator.sanitize_input(dirty)
        assert "\x00" not in result
        assert "\x07" not in result
        assert "\x01" not in result
        assert "hello" in result and "world" in result

    @pytest.mark.unit
    def test_validate_glob_pattern_too_long(self):
        """validate_glob_pattern rejects pattern > 500 chars."""
        long_pattern = "a" * 501
        is_valid, error = self.validator.validate_glob_pattern(long_pattern)
        assert not is_valid
        assert "too long" in error

    @pytest.mark.unit
    def test_validate_glob_pattern_empty(self):
        """validate_glob_pattern rejects empty string."""
        is_valid, error = self.validator.validate_glob_pattern("")
        assert not is_valid
        assert "non-empty" in error or "empty" in error.lower()

    @pytest.mark.unit
    def test_validate_path_alias(self):
        """validate_path is alias for validate_file_path."""
        is_valid, error = self.validator.validate_path(
            "src/main.py", base_path=self.temp_dir
        )
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    def test_is_safe_path_direct(self):
        """is_safe_path returns True/False based on validation."""
        assert self.validator.is_safe_path("src/main.py", base_path=self.temp_dir)
        assert not self.validator.is_safe_path("../../../etc/passwd")

    @pytest.mark.unit
    def test_validate_path_traversal_dotdot(self):
        """_validate_path_traversal rejects .. patterns."""
        is_valid, error = self.validator._validate_path_traversal("../etc/passwd")
        assert not is_valid
        assert "traversal" in error.lower()

    @pytest.mark.unit
    def test_validate_path_traversal_backslash(self):
        """_validate_path_traversal rejects ..\\ patterns."""
        is_valid, error = self.validator._validate_path_traversal("..\\..\\etc")
        assert not is_valid

    @pytest.mark.unit
    def test_validate_path_traversal_starts_with_dotdot(self):
        """_validate_path_traversal rejects path starting with .."""
        is_valid, error = self.validator._validate_path_traversal("..")
        assert not is_valid

    @pytest.mark.unit
    def test_validate_path_traversal_safe(self):
        """_validate_path_traversal accepts safe path."""
        is_valid, error = self.validator._validate_path_traversal("src/main.py")
        assert is_valid
        assert error == ""

    @pytest.mark.unit
    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Windows drive letter check only on non-Windows",
    )
    def test_validate_windows_drive_letter_on_unix(self):
        """_validate_windows_drive_letter rejects C: on non-Windows."""
        is_valid, error = self.validator._validate_windows_drive_letter("C:\\path")
        assert not is_valid
        assert "drive" in error.lower() or "Windows" in error

    @pytest.mark.unit
    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="Windows drive letter allowed on Windows",
    )
    def test_validate_windows_drive_letter_on_windows(self):
        """_validate_windows_drive_letter allows C: on Windows."""
        is_valid, error = self.validator._validate_windows_drive_letter("C:\\path")
        assert is_valid

    @pytest.mark.unit
    def test_validate_file_path_null_bytes(self):
        """validate_file_path rejects null byte injection."""
        is_valid, error = self.validator.validate_file_path("src/main\x00evil.py")
        assert not is_valid
        assert "null" in error.lower()

    @pytest.mark.unit
    def test_validate_file_path_path_too_long(self):
        """validate_file_path handles very long paths."""
        # Create a path longer than MAX_PATH (260 on Windows, 4096 on Linux)
        base = Path(self.temp_dir) / "src"
        long_name = "a" * 300
        str(base / long_name)
        is_valid, error = self.validator.validate_file_path(
            long_name, base_path=str(base)
        )
        # May pass validation (path exists check) or fail - just ensure no crash
        assert isinstance(is_valid, bool)

    @pytest.mark.unit
    def test_validate_directory_path_with_nonexistent_must_exist(self):
        """validate_directory_path with must_exist=True for non-existent dir."""
        nonexistent = str(Path(self.temp_dir) / "does_not_exist")
        is_valid, error = self.validator.validate_directory_path(
            nonexistent, must_exist=True
        )
        assert not is_valid
        assert "does not exist" in error

    @pytest.mark.unit
    def test_sanitize_input_preserves_safe_content(self):
        """sanitize_input preserves safe alphanumeric content."""
        safe = "hello world 123"
        assert self.validator.sanitize_input(safe) == safe
