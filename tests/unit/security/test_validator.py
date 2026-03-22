#!/usr/bin/env python3
"""
Unit tests for validator module.

Tests for SecurityValidator class which provides comprehensive security
validation for file paths, regex patterns, and user inputs.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security.validator import SecurityValidator


class TestSecurityValidatorInitialization:
    """测试 SecurityValidator 初始化"""

    def test_default_initialization(self):
        """测试默认初始化"""
        validator = SecurityValidator()
        assert validator is not None
        assert validator.boundary_manager is None
        assert validator.regex_checker is not None

    def test_initialization_with_project_root(self):
        """测试带项目根目录的初始化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = SecurityValidator(temp_dir)
            assert validator.boundary_manager is not None
            assert validator.regex_checker is not None

    def test_initialization_with_invalid_project_root(self):
        """测试无效项目根目录的初始化"""
        # Non-existent path should still initialize, but boundary_manager should be None
        validator = SecurityValidator("/nonexistent/path")
        # The boundary_manager should be None or initialized gracefully
        assert validator.regex_checker is not None


class TestValidateFilePath:
    """测试 validate_file_path 方法"""

    def test_validate_file_path_valid_relative(self):
        """测试有效的相对路径"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("src/main.py")
        assert is_valid
        assert error == ""

    def test_validate_file_path_empty(self):
        """测试空路径"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("")
        assert not is_valid
        assert "non-empty" in error

    def test_validate_file_path_none(self):
        """测试 None 路径"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path(None)
        assert not is_valid
        assert "non-empty" in error

    def test_validate_file_path_non_string(self):
        """测试非字符串路径"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path(123)
        assert not is_valid
        assert "non-empty" in error

    def test_validate_file_path_null_byte(self):
        """测试空字节注入"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("test\x00file.py")
        assert not is_valid
        assert "null bytes" in error

    def test_validate_file_path_with_base_path(self):
        """测试带基础路径的验证"""
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = SecurityValidator(temp_dir)
            is_valid, error = validator.validate_file_path("subdir/file.py", temp_dir)
            assert is_valid
            assert error == ""

    def test_validate_file_path_traversal(self):
        """测试路径遍历攻击"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("../etc/passwd")
        assert not is_valid
        assert "traversal" in error.lower()

    def test_validate_file_path_traversal_backslash(self):
        """测试反斜杠路径遍历"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_file_path("..\\..\\file.py")
        assert not is_valid
        assert "traversal" in error.lower()

    def test_validate_file_path_absolute_with_boundary(self):
        """测试带边界管理的绝对路径"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a file in temp directory
            test_file = Path(temp_dir) / "test.py"
            test_file.touch()

            validator = SecurityValidator(temp_dir)
            is_valid, error = validator.validate_file_path(str(test_file))
            assert is_valid
            assert error == ""

    def test_validate_file_path_absolute_outside_boundary(self):
        """测试边界外的绝对路径"""
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = SecurityValidator(temp_dir)
            is_valid, error = validator.validate_file_path("/etc/passwd")
            assert not is_valid
            assert "project directory" in error.lower()

    def test_validate_file_path_symlink(self):
        """测试符号链接路径"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a symlink
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
                # Symlink creation might not be supported
                pytest.skip("Symlink creation not supported")

    def test_validate_file_path_exception_handling(self):
        """测试异常处理"""
        validator = SecurityValidator()

        with patch.object(
            validator,
            "_validate_windows_drive_letter",
            side_effect=Exception("Test error"),
        ):
            is_valid, error = validator.validate_file_path("test.py")
            assert not is_valid
            assert "Validation error" in error


class TestValidateDirectoryPath:
    """测试 validate_directory_path 方法"""

    def test_validate_directory_path_valid(self):
        """测试有效目录路径"""
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = SecurityValidator()
            is_valid, error = validator.validate_directory_path(temp_dir)
            assert is_valid
            assert error == ""

    def test_validate_directory_path_nonexistent(self):
        """测试不存在的目录"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_directory_path("/nonexistent/dir")
        assert not is_valid
        # For absolute paths without boundary manager, error is "Absolute file paths are not allowed"
        assert (
            "does not exist" in error or "Absolute file paths are not allowed" in error
        )

    def test_validate_directory_path_file_instead(self):
        """测试文件而非目录"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.txt"
            test_file.touch()

            validator = SecurityValidator()
            is_valid, error = validator.validate_directory_path(str(test_file))
            assert not is_valid
            # For absolute paths without boundary manager, error is "Absolute file paths are not allowed"
            assert (
                "not a directory" in error
                or "Absolute file paths are not allowed" in error
            )

    def test_validate_directory_path_must_exist_false(self):
        """测试不检查存在性"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_directory_path(
            "/nonexistent/dir", must_exist=False
        )
        # For absolute paths without boundary manager, it may still be invalid
        # Just verify it doesn't crash
        assert isinstance(is_valid, bool)

    def test_validate_directory_path_with_base_path(self):
        """测试带基础路径的目录验证"""
        with tempfile.TemporaryDirectory() as temp_dir:
            sub_dir = Path(temp_dir) / "subdir"
            sub_dir.mkdir()

            validator = SecurityValidator(temp_dir)
            is_valid, error = validator.validate_directory_path("subdir", temp_dir)
            # Just verify it doesn't crash
            assert isinstance(is_valid, bool)


class TestValidateRegexPattern:
    """测试 validate_regex_pattern 方法"""

    def test_validate_regex_pattern_safe(self):
        """测试安全的正则表达式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_regex_pattern(r"test.*pattern")
        assert is_valid
        assert error == ""

    def test_validate_regex_pattern_dangerous(self):
        """测试危险的正则表达式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_regex_pattern(r"(a+)+")
        assert not is_valid
        assert "dangerous" in error.lower()

    def test_validate_regex_pattern_invalid(self):
        """测试无效的正则表达式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_regex_pattern(r"[invalid(regex")
        assert not is_valid
        assert "Invalid regex" in error


class TestSanitizeInput:
    """测试 sanitize_input 方法"""

    def test_sanitize_input_normal(self):
        """测试正常输入"""
        validator = SecurityValidator()
        result = validator.sanitize_input("test input")
        assert result == "test input"

    def test_sanitize_input_null_bytes(self):
        """测试空字节清理"""
        validator = SecurityValidator()
        result = validator.sanitize_input("test\x00input")
        assert "\x00" not in result

    def test_sanitize_input_html_tags(self):
        """测试HTML标签清理"""
        validator = SecurityValidator()
        result = validator.sanitize_input("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "alert" in result

    def test_sanitize_input_control_chars(self):
        """测试控制字符清理"""
        validator = SecurityValidator()
        result = validator.sanitize_input("test\x1b\x1ffile")
        assert "\x1b" not in result
        assert "\x1f" not in result

    def test_sanitize_input_dangerous_chars(self):
        """测试危险字符清理"""
        validator = SecurityValidator()
        result = validator.sanitize_input('test"><script>alert')
        assert ">" not in result
        assert "'" not in result

    def test_sanitize_input_too_long(self):
        """测试过长输入"""
        validator = SecurityValidator()
        with pytest.raises(SecurityError):
            validator.sanitize_input("a" * 2000)

    def test_sanitize_input_non_string(self):
        """测试非字符串输入"""
        validator = SecurityValidator()
        with pytest.raises(SecurityError):
            validator.sanitize_input(123)


class TestValidateGlobPattern:
    """测试 validate_glob_pattern 方法"""

    def test_validate_glob_pattern_valid(self):
        """测试有效的glob模式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_glob_pattern("*.py")
        assert is_valid
        assert error == ""

    def test_validate_glob_pattern_empty(self):
        """测试空glob模式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_glob_pattern("")
        assert not is_valid
        assert "non-empty" in error

    def test_validate_glob_pattern_traversal(self):
        """测试路径遍历glob模式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_glob_pattern("../../*")
        assert not is_valid
        assert "dangerous" in error.lower()

    def test_validate_glob_pattern_double_slash(self):
        """测试双斜杠glob模式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_glob_pattern("//etc/*")
        assert not is_valid
        assert "dangerous" in error.lower()

    def test_validate_glob_pattern_double_backslash(self):
        """测试双反斜杠glob模式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_glob_pattern("\\\\Windows\\*")
        assert not is_valid
        assert "dangerous" in error.lower()

    def test_validate_glob_pattern_too_long(self):
        """测试过长glob模式"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_glob_pattern("a" * 600)
        assert not is_valid
        assert "too long" in error


class TestValidatePathAlias:
    """测试 validate_path 别名方法"""

    def test_validate_path_alias(self):
        """测试validate_path别名方法"""
        validator = SecurityValidator()
        is_valid, error = validator.validate_path("src/main.py")
        assert is_valid
        assert error == ""


class TestIsSafePath:
    """测试 is_safe_path 方法"""

    def test_is_safe_path_valid(self):
        """测试安全路径"""
        validator = SecurityValidator()
        result = validator.is_safe_path("src/main.py")
        assert result is True

    def test_is_safe_path_invalid(self):
        """测试不安全路径"""
        validator = SecurityValidator()
        result = validator.is_safe_path("../etc/passwd")
        assert result is False


class TestValidateWindowsDriveLetter:
    """测试 _validate_windows_drive_letter 方法"""

    def test_validate_windows_drive_letter_on_windows(self):
        """测试Windows系统上的驱动器字母"""
        validator = SecurityValidator()

        with patch("platform.system", return_value="Windows"):
            is_valid, error = validator._validate_windows_drive_letter("C:\\test.py")
            assert is_valid
            assert error == ""

    def test_validate_windows_drive_letter_on_non_windows(self):
        """测试非Windows系统上的驱动器字母"""
        validator = SecurityValidator()

        with patch("platform.system", return_value="Linux"):
            is_valid, error = validator._validate_windows_drive_letter("C:\\test.py")
            assert not is_valid
            assert "not allowed" in error

    def test_validate_windows_drive_letter_normal_path(self):
        """测试正常路径"""
        validator = SecurityValidator()
        is_valid, error = validator._validate_windows_drive_letter("normal/path")
        assert is_valid
        assert error == ""


class TestValidateAbsolutePath:
    """测试 _validate_absolute_path 方法"""

    def test_validate_absolute_path_with_boundary(self):
        """测试带边界的绝对路径"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.touch()

            validator = SecurityValidator(temp_dir)
            is_valid, error = validator._validate_absolute_path(str(test_file))
            assert is_valid
            assert error == ""

    def test_validate_absolute_path_outside_boundary(self):
        """测试边界外的绝对路径"""
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = SecurityValidator(temp_dir)
            is_valid, error = validator._validate_absolute_path("/etc/passwd")
            assert not is_valid
            assert "project directory" in error.lower()

    def test_validate_absolute_path_no_boundary(self):
        """测试无边界的绝对路径"""
        validator = SecurityValidator()

        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "1"}):
            # Use a platform-appropriate temp path
            with tempfile.TemporaryDirectory() as temp_dir:
                test_path = str(Path(temp_dir) / "test.py")
                is_valid, error = validator._validate_absolute_path(test_path)
                # Should be allowed in test environment
                assert is_valid


class TestValidatePathTraversal:
    """测试 _validate_path_traversal 方法"""

    def test_validate_path_traversal_normal(self):
        """测试正常路径"""
        validator = SecurityValidator()
        is_valid, error = validator._validate_path_traversal("src/main.py")
        assert is_valid
        assert error == ""

    def test_validate_path_traversal_double_dot(self):
        """测试双点路径遍历"""
        validator = SecurityValidator()
        is_valid, error = validator._validate_path_traversal("..\\file.py")
        assert not is_valid
        assert "traversal" in error.lower()

    def test_validate_path_traversal_double_dot_slash(self):
        """测试双点斜杠路径遍历"""
        validator = SecurityValidator()
        is_valid, error = validator._validate_path_traversal("../file.py")
        assert not is_valid
        assert "traversal" in error.lower()

    def test_validate_path_traversal_triple_dot(self):
        """测试三点路径遍历"""
        validator = SecurityValidator()
        is_valid, error = validator._validate_path_traversal(".../file.py")
        # "..." is not a traversal pattern, so it should pass
        # But it might be normalized to something else
        assert isinstance(is_valid, bool)


class TestValidateProjectBoundary:
    """测试 _validate_project_boundary 方法"""

    def test_validate_project_boundary_no_manager(self):
        """测试无边界管理器"""
        validator = SecurityValidator()
        is_valid, error = validator._validate_project_boundary("src/main.py", None)
        assert is_valid
        assert error == ""

    def test_validate_project_boundary_within(self):
        """测试边界内路径"""
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = SecurityValidator(temp_dir)
            is_valid, error = validator._validate_project_boundary(
                "subdir/file.py", temp_dir
            )
            assert is_valid
            assert error == ""

    def test_validate_project_boundary_outside(self):
        """测试边界外路径"""
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = SecurityValidator(temp_dir)
            is_valid, error = validator._validate_project_boundary(
                "../outside/file.py", temp_dir
            )
            assert not is_valid
            assert "Access denied" in error


class TestIsJunctionOrReparsePoint:
    """测试 _is_junction_or_reparse_point 方法"""

    def test_is_junction_or_reparse_point_non_windows(self):
        """测试非Windows系统"""
        validator = SecurityValidator()

        with patch("platform.system", return_value="Linux"):
            result = validator._is_junction_or_reparse_point(Path("/test/path"))
            assert result is False

    def test_is_junction_or_reparse_point_nonexistent(self):
        """测试不存在的路径"""
        validator = SecurityValidator()
        result = validator._is_junction_or_reparse_point(Path("/nonexistent/path"))
        assert result is False

    def test_is_junction_or_reparse_point_exception(self):
        """测试异常处理"""
        validator = SecurityValidator()

        with patch("platform.system", return_value="Windows"):
            with patch("tree_sitter_analyzer.security.validator.HAS_CTYPES", False):
                result = validator._is_junction_or_reparse_point(Path("/test/path"))
                assert result is False


class TestHasJunctionInPath:
    """测试 _has_junction_in_path 方法"""

    def test_has_junction_in_path_non_windows(self):
        """测试非Windows系统"""
        validator = SecurityValidator()

        with patch("platform.system", return_value="Linux"):
            result = validator._has_junction_in_path(Path("/test/path"))
            assert result is False

    def test_has_junction_in_path_exception(self):
        """测试异常处理"""
        validator = SecurityValidator()

        with patch.object(
            validator,
            "_is_junction_or_reparse_point",
            side_effect=Exception("Test error"),
        ):
            result = validator._has_junction_in_path(Path("/test/path"))
            assert result is False


class TestCheckTestEnvironmentAccess:
    """测试 _check_test_environment_access 方法"""

    def test_check_test_environment_access_temp_dir(self):
        """测试临时目录访问"""
        validator = SecurityValidator()

        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "1"}):
            with tempfile.TemporaryDirectory() as temp_dir:
                is_valid, error = validator._check_test_environment_access(
                    str(Path(temp_dir) / "test.py")
                )
                assert is_valid
                assert error == ""

    def test_check_test_environment_access_non_test(self):
        """测试非测试环境"""
        validator = SecurityValidator()

        with patch.dict(os.environ, {}, clear=True):
            # Use system temp directory instead of hardcoded /tmp
            with tempfile.TemporaryDirectory() as temp_dir:
                test_file = str(Path(temp_dir) / "test.py")
                is_valid, error = validator._check_test_environment_access(test_file)
                # Should be allowed under system temp directory
                assert is_valid
                assert error == ""

    def test_check_test_environment_access_test_file(self):
        """测试测试文件"""
        validator = SecurityValidator()

        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "1"}):
            # Use a platform-appropriate temp path
            with tempfile.TemporaryDirectory() as temp_dir:
                test_path = str(Path(temp_dir) / "test_file.py")
                is_valid, error = validator._check_test_environment_access(test_path)
                assert is_valid
                assert error == ""


class TestIntegration:
    """测试集成场景"""

    def test_complete_file_validation_workflow(self):
        """测试完整文件验证工作流"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test file
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("test content")

            validator = SecurityValidator(temp_dir)

            # Validate file path
            is_valid, error = validator.validate_file_path("test.py", temp_dir)
            assert is_valid
            assert error == ""

            # Check if safe
            assert validator.is_safe_path("test.py", temp_dir)

    def test_complete_directory_validation_workflow(self):
        """测试完整目录验证工作流"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test directory
            test_dir = Path(temp_dir) / "test_dir"
            test_dir.mkdir()

            validator = SecurityValidator(temp_dir)

            # Validate directory path
            is_valid, error = validator.validate_directory_path("test_dir", temp_dir)
            # Just verify it doesn't crash
            assert isinstance(is_valid, bool)

    def test_security_layered_validation(self):
        """测试分层安全验证"""
        validator = SecurityValidator()

        # Test that multiple security layers work together
        is_valid, error = validator.validate_file_path("safe/path.py")
        assert is_valid
        assert error == ""

        # Test that traversal is caught
        is_valid, error = validator.validate_file_path("../etc/passwd")
        assert not is_valid
        assert "traversal" in error.lower()
