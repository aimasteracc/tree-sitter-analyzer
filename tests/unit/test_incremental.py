"""增量分析工具的单元测试"""

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.incremental import (
    CacheManagerTool,
    ChangeDetectorTool,
    IncrementalAnalyzerTool,
)


class TestChangeDetectorTool:
    """测试文件变更检测工具"""

    def test_detect_changes_new_files(self, tmp_path: Path):
        """测试检测新文件"""
        tool = ChangeDetectorTool()

        # 创建测试文件
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        result = tool.execute({"directory": str(tmp_path)})

        assert result["success"] is True
        assert len(result["changes"]["added"]) == 1
        assert test_file.name in result["changes"]["added"][0]

    def test_detect_changes_modified_files(self, tmp_path: Path):
        """测试检测修改的文件"""
        tool = ChangeDetectorTool()

        # 第一次扫描
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")
        tool.execute({"directory": str(tmp_path)})

        # 修改文件
        test_file.write_text("def bar(): pass")

        # 第二次扫描
        result = tool.execute({"directory": str(tmp_path)})

        assert result["success"] is True
        assert len(result["changes"]["modified"]) == 1
        assert test_file.name in result["changes"]["modified"][0]

    def test_detect_changes_deleted_files(self, tmp_path: Path):
        """测试检测删除的文件"""
        tool = ChangeDetectorTool()

        # 第一次扫描
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")
        tool.execute({"directory": str(tmp_path)})

        # 删除文件
        test_file.unlink()

        # 第二次扫描
        result = tool.execute({"directory": str(tmp_path)})

        assert result["success"] is True
        assert len(result["changes"]["deleted"]) == 1
        assert test_file.name in result["changes"]["deleted"][0]


class TestCacheManagerTool:
    """测试缓存管理工具"""

    def test_set_and_get_cache(self):
        """测试设置和获取缓存"""
        tool = CacheManagerTool()

        # 设置缓存
        result = tool.execute(
            {"operation": "set", "key": "test_key", "value": {"data": "test_data"}}
        )
        assert result["success"] is True

        # 获取缓存
        result = tool.execute({"operation": "get", "key": "test_key"})
        assert result["success"] is True
        assert result["value"]["data"] == "test_data"

    def test_get_nonexistent_cache(self):
        """测试获取不存在的缓存"""
        tool = CacheManagerTool()

        result = tool.execute({"operation": "get", "key": "nonexistent_key"})
        assert result["success"] is True
        assert result["value"] is None

    def test_delete_cache(self):
        """测试删除缓存"""
        tool = CacheManagerTool()

        # 设置缓存
        tool.execute(
            {"operation": "set", "key": "test_key", "value": {"data": "test_data"}}
        )

        # 删除缓存
        result = tool.execute({"operation": "delete", "key": "test_key"})
        assert result["success"] is True

        # 验证缓存已删除
        result = tool.execute({"operation": "get", "key": "test_key"})
        assert result["value"] is None

    def test_clear_all_cache(self):
        """测试清除所有缓存"""
        tool = CacheManagerTool()

        # 设置多个缓存
        tool.execute({"operation": "set", "key": "key1", "value": {"data": "data1"}})
        tool.execute({"operation": "set", "key": "key2", "value": {"data": "data2"}})

        # 清除所有缓存
        result = tool.execute({"operation": "clear"})
        assert result["success"] is True

        # 验证缓存已清除
        result = tool.execute({"operation": "get", "key": "key1"})
        assert result["value"] is None


class TestIncrementalAnalyzerTool:
    """测试增量分析工具"""

    def test_analyze_only_changed_files(self, tmp_path: Path):
        """测试只分析变更的文件"""
        tool = IncrementalAnalyzerTool()

        # 创建测试文件
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass\ndef bar(): pass")

        # 第一次分析
        result = tool.execute({"directory": str(tmp_path)})
        assert result["success"] is True
        assert len(result["analyzed_files"]) == 1

        # 修改文件
        test_file.write_text("def foo(): pass\ndef bar(): pass\ndef baz(): pass")

        # 第二次分析（增量）
        result = tool.execute({"directory": str(tmp_path)})
        assert result["success"] is True
        assert len(result["analyzed_files"]) == 1  # 只分析了修改的文件
        assert result["cache_hit"] is False

    def test_use_cache_for_unchanged_files(self, tmp_path: Path):
        """测试对未变更的文件使用缓存"""
        tool = IncrementalAnalyzerTool()

        # 创建测试文件
        test_file1 = tmp_path / "test1.py"
        test_file1.write_text("def foo(): pass")
        test_file2 = tmp_path / "test2.py"
        test_file2.write_text("def bar(): pass")

        # 第一次分析
        result = tool.execute({"directory": str(tmp_path)})
        assert result["success"] is True
        assert len(result["analyzed_files"]) == 2

        # 只修改一个文件
        test_file1.write_text("def foo(): pass\ndef baz(): pass")

        # 第二次分析
        result = tool.execute({"directory": str(tmp_path)})
        assert result["success"] is True
        # 应该只分析修改的文件，另一个使用缓存
        assert len(result["analyzed_files"]) == 1
