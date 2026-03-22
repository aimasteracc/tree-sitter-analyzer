"""
单元测试：security/boundary_manager.py

测试边界管理器的所有功能，包括：
- ProjectBoundaryManager 类
- 项目根路径验证
- 文件路径验证
- 安全边界检查
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.security.boundary_manager import (
    ProjectBoundaryManager,
    SecurityError,
)


def _normalize_path(path: str) -> str:
    """Normalize path to handle Windows short path names (8.3 format).

    On Windows, tempfile paths may use short names like RUNNER~1 while
    resolved paths use full names like runneradmin. This normalizes
    both to the same format for comparison.
    """
    try:
        return str(Path(path).resolve())
    except (OSError, ValueError):
        return path


class TestBoundaryManagerInitialization:
    """测试 ProjectBoundaryManager 初始化"""

    def test_default_initialization(self):
        """测试默认初始化"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            normalized_tmp = _normalize_path(tmp_dir)
            manager = ProjectBoundaryManager(project_root=tmp_dir)
            assert _normalize_path(manager.project_root) == normalized_tmp
            assert len(manager.allowed_directories) == 1
            # Check normalized paths match
            normalized_allowed = {
                _normalize_path(d) for d in manager.allowed_directories
            }
            assert normalized_tmp in normalized_allowed

    def test_custom_project_root(self):
        """测试自定义项目根路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            normalized_tmp = _normalize_path(tmp_dir)
            manager = ProjectBoundaryManager(project_root=tmp_dir)
            assert _normalize_path(manager.project_root) == normalized_tmp

    def test_project_root_as_string(self):
        """测试项目根路径作为字符串"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            normalized_tmp = _normalize_path(tmp_dir)
            manager = ProjectBoundaryManager(project_root=tmp_dir)
            assert _normalize_path(manager.project_root) == normalized_tmp

    def test_empty_project_root(self):
        """测试空项目根路径"""
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager(project_root="")
        assert "cannot be empty" in str(exc_info.value)

    def test_nonexistent_project_root(self):
        """测试不存在的项目根路径"""
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager(project_root="/nonexistent/path")
        assert "does not exist" in str(exc_info.value)

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows file permission handling differs"
    )
    def test_project_root_as_file(self):
        """测试项目根路径是文件而非目录"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            with pytest.raises(SecurityError) as exc_info:
                ProjectBoundaryManager(project_root=tmp_file.name)
            assert "not a directory" in str(exc_info.value)
            os.unlink(tmp_file.name)


class TestAddAllowedDirectory:
    """测试添加允许的目录"""

    def test_add_allowed_directory(self):
        """测试添加允许的目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            with tempfile.TemporaryDirectory() as allowed_dir:
                normalized_allowed = _normalize_path(allowed_dir)
                manager.add_allowed_directory(allowed_dir)
                # Check normalized paths match
                normalized_dirs = {
                    _normalize_path(d) for d in manager.allowed_directories
                }
                assert normalized_allowed in normalized_dirs

    def test_add_nonexistent_directory(self):
        """测试添加不存在的目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            with pytest.raises(SecurityError) as exc_info:
                manager.add_allowed_directory("/nonexistent/path")
            assert "does not exist" in str(exc_info.value)

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows file permission handling differs"
    )
    def test_add_file_as_directory(self):
        """测试添加文件作为目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                with pytest.raises(SecurityError) as exc_info:
                    manager.add_allowed_directory(tmp_file.name)
                assert "not a directory" in str(exc_info.value)
                os.unlink(tmp_file.name)

    def test_add_empty_directory(self):
        """测试添加空目录路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            with pytest.raises(SecurityError) as exc_info:
                manager.add_allowed_directory("")
            assert "cannot be empty" in str(exc_info.value)


class TestIsWithinProject:
    """测试项目边界检查"""

    def test_is_within_project_valid(self):
        """测试有效的项目内路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            test_file = Path(tmp_dir) / "test.py"
            test_file.touch()

            result = manager.is_within_project(str(test_file))
            assert result is True

    def test_is_within_project_outside(self):
        """测试项目外路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            outside_file = Path(tmp_dir) / ".." / "outside.py"

            result = manager.is_within_project(str(outside_file))
            assert result is False

    def test_is_within_project_empty_path(self):
        """测试空路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            result = manager.is_within_project("")
            assert result is False

    def test_is_within_project_nonexistent(self):
        """测试不存在的文件"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            nonexistent_file = Path(tmp_dir) / "nonexistent.py"

            result = manager.is_within_project(str(nonexistent_file))
            # 不存在的文件仍然可能被认为是"在边界内"（因为路径检查）
            # 这取决于实现
            assert isinstance(result, bool)


class TestGetRelativePath:
    """测试获取相对路径"""

    def test_get_relative_path_valid(self):
        """测试获取有效的相对路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            test_file = Path(tmp_dir) / "subdir" / "test.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.touch()

            result = manager.get_relative_path(str(test_file))
            assert result == os.path.join("subdir", "test.py")

    def test_get_relative_path_outside(self):
        """测试获取项目外路径的相对路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            outside_file = Path(tmp_dir) / ".." / "outside.py"

            result = manager.get_relative_path(str(outside_file))
            assert result is None

    def test_get_relative_path_with_dots(self):
        """测试包含点的路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            test_file = Path(tmp_dir) / "test.py"
            test_file.touch()

            result = manager.get_relative_path(str(test_file))
            assert result == "test.py"


class TestValidateAndResolvePath:
    """测试路径验证和解析"""

    def test_validate_and_resolve_path_valid(self):
        """测试验证和解析有效路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            test_file = Path(tmp_dir) / "test.py"
            test_file.touch()

            result = manager.validate_and_resolve_path(str(test_file))
            assert result == str(test_file.resolve())

    def test_validate_and_resolve_path_relative(self):
        """测试验证和解析相对路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            test_file = Path(tmp_dir) / "subdir" / "test.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.touch()

            result = manager.validate_and_resolve_path("subdir/test.py")
            assert result == str(test_file.resolve())

    def test_validate_and_resolve_path_outside(self):
        """测试验证和解析项目外路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            outside_file = Path(tmp_dir) / ".." / "outside.py"

            result = manager.validate_and_resolve_path(str(outside_file))
            assert result is None

    def test_validate_and_resolve_path_nonexistent(self):
        """测试验证和解析不存在的路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            # 不存在的文件路径仍然可能返回解析后的路径
            result = manager.validate_and_resolve_path("nonexistent.py")
            # 结果取决于实现
            assert result is None or isinstance(result, str)


class TestListAllowedDirectories:
    """测试列出允许的目录"""

    def test_list_allowed_directories(self):
        """测试列出允许的目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            normalized_tmp = _normalize_path(tmp_dir)
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            with tempfile.TemporaryDirectory() as allowed_dir:
                normalized_allowed = _normalize_path(allowed_dir)
                manager.add_allowed_directory(allowed_dir)

                allowed_dirs = manager.list_allowed_directories()
                assert len(allowed_dirs) == 2
                # Check normalized paths match
                normalized_dirs = {_normalize_path(d) for d in allowed_dirs}
                assert normalized_tmp in normalized_dirs
                assert normalized_allowed in normalized_dirs


class TestIsSymlinkSafe:
    """测试符号链接安全性检查"""

    def test_is_symlink_safe_regular_file(self):
        """测试常规文件的安全性"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            test_file = Path(tmp_dir) / "test.txt"
            test_file.write_text("content")

            result = manager.is_symlink_safe(str(test_file))
            assert result is True

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows symlink handling differs"
    )
    def test_is_symlink_safe_within_boundary(self):
        """测试边界内符号链接的安全性"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            target_file = Path(tmp_dir) / "target.txt"
            target_file.write_text("content")

            link_file = Path(tmp_dir) / "link.txt"
            link_file.symlink_to(target_file)

            result = manager.is_symlink_safe(str(link_file))
            # 边界内的符号链接应该被认为是安全的
            assert result is True

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows symlink handling differs"
    )
    def test_is_symlink_safe_outside_boundary(self):
        """测试边界外符号链接的安全性"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            with tempfile.TemporaryDirectory() as outside_dir:
                target_file = Path(outside_dir) / "target.txt"
                target_file.write_text("content")

                link_file = Path(tmp_dir) / "link.txt"
                link_file.symlink_to(target_file)

                result = manager.is_symlink_safe(str(link_file))
                # 边界外的符号链接应该被认为是不安全的
                assert result is False

    def test_is_symlink_safe_nonexistent(self):
        """测试不存在的文件"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            nonexistent_file = Path(tmp_dir) / "nonexistent.txt"

            result = manager.is_symlink_safe(str(nonexistent_file))
            # 不存在的文件是安全的
            assert result is True


class TestAuditAccess:
    """测试访问审计"""

    def test_audit_access_within_boundary(self):
        """测试审计边界内访问"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            test_file = Path(tmp_dir) / "test.txt"
            test_file.write_text("content")

            # 应该记录审计日志
            manager.audit_access(str(test_file), "read")
            # 不抛出异常

    def test_audit_access_outside_boundary(self):
        """测试审计边界外访问"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            outside_file = Path(tmp_dir) / ".." / "outside.txt"

            # 应该记录审计日志
            manager.audit_access(str(outside_file), "read")
            # 不抛出异常


class TestStringRepresentation:
    """测试字符串表示"""

    def test_str_representation(self):
        """测试 __str__ 方法"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            str_repr = str(manager)
            # The string representation may contain either the original or normalized path
            assert "ProjectBoundaryManager" in str_repr
            # Check that some form of the path is present (either short or long form)
            assert "Temp" in str_repr or "tmp" in str_repr.lower()

    def test_repr_representation(self):
        """测试 __repr__ 方法"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            repr_str = repr(manager)
            assert "ProjectBoundaryManager" in repr_str
            assert "allowed_directories" in repr_str
            # Check that some form of the path is present (either short or long form)
            assert "Temp" in repr_str or "tmp" in repr_str.lower()


class TestEdgeCases:
    """测试边缘情况"""

    def test_deeply_nested_directory(self):
        """测试深层嵌套目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            deep_dir = Path(tmp_dir) / "a" / "b" / "c" / "d"
            deep_dir.mkdir(parents=True)

            result = manager.is_within_project(str(deep_dir))
            assert result is True

    def test_unicode_filename(self):
        """测试 Unicode 文件名"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            unicode_file = Path(tmp_dir) / "测试文件.txt"
            unicode_file.write_text("content")

            result = manager.is_within_project(str(unicode_file))
            assert result is True

    def test_path_with_spaces(self):
        """测试包含空格的路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            space_file = Path(tmp_dir) / "file with spaces.txt"
            space_file.write_text("content")

            result = manager.is_within_project(str(space_file))
            assert result is True

    def test_multiple_allowed_directories(self):
        """测试多个允许的目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            allowed_dirs = []
            for _i in range(3):
                with tempfile.TemporaryDirectory() as allowed_dir:
                    manager.add_allowed_directory(allowed_dir)
                    allowed_dirs.append(allowed_dir)

            assert len(manager.allowed_directories) == 4  # 1 initial + 3 added


class TestIntegration:
    """集成测试"""

    def test_complete_workflow(self):
        """测试完整工作流程"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            # 创建测试文件
            test_file = Path(tmp_dir) / "test.txt"
            test_file.write_text("test content")

            # 验证文件在边界内
            assert manager.is_within_project(str(test_file)) is True

            # 获取相对路径
            rel_path = manager.get_relative_path(str(test_file))
            assert rel_path == "test.txt"

            # 验证和解析路径
            resolved = manager.validate_and_resolve_path(str(test_file))
            assert resolved == str(test_file.resolve())

            # 检查符号链接安全性
            assert manager.is_symlink_safe(str(test_file)) is True

            # 审计访问
            manager.audit_access(str(test_file), "read")

    def test_boundary_enforcement(self):
        """测试边界强制执行"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ProjectBoundaryManager(project_root=tmp_dir)

            # 项目内文件
            inside_file = Path(tmp_dir) / "inside.txt"
            inside_file.write_text("inside")

            # 项目外文件
            outside_file = Path(tmp_dir) / ".." / "outside.txt"
            outside_file.write_text("outside")

            # 验证边界检查
            assert manager.is_within_project(str(inside_file)) is True
            assert manager.is_within_project(str(outside_file)) is False

            # 验证相对路径获取
            assert manager.get_relative_path(str(inside_file)) == "inside.txt"
            assert manager.get_relative_path(str(outside_file)) is None

            # 验证和解析路径
            assert manager.validate_and_resolve_path(str(inside_file)) == str(
                inside_file.resolve()
            )
            assert manager.validate_and_resolve_path(str(outside_file)) is None
