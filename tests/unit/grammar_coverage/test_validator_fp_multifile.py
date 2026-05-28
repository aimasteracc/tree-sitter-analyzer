#!/usr/bin/env python3
"""
False Positive Detection Tests for Grammar Coverage Validator — Multi-File Scenarios

Tests for TestMultiFileScenarios:
- Same node type in different files
- Same position range in different files
- Cross-file node identity no conflict
- Empty file path boundary
- Relative vs absolute path
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMultiFileScenarios:
    """
    测试多文件场景下的节点身份冲突

    场景：
    - 两个文件有相同节点类型和位置
    - file_path 区分不同文件的节点
    - 相对路径 vs 绝对路径
    """

    @pytest.mark.asyncio
    async def test_same_node_type_different_files(self):
        """测试相同节点类型在不同文件（应正确区分）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # File 1: function_definition at lines 1-5
        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"
        func.start_point = (0, 0)
        func.end_point = (4, 0)
        func.children = []

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.children = [func]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Extracted from file1
        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 5

        mock_result = MagicMock()
        mock_result.elements = [mock_element]

        mock_plugin = AsyncMock()
        mock_plugin.analyze_file.return_value = mock_result

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.get_plugin.return_value = mock_plugin

        with (
            patch(
                "tree_sitter_analyzer.plugins.manager.PluginManager",
                return_value=mock_plugin_manager,
            ),
            patch(
                "tree_sitter_analyzer.language_loader.loader.create_parser_safely",
                return_value=mock_parser,
            ),
            patch.object(Path, "read_text", return_value="def foo(): pass"),
        ):
            covered1 = await _get_covered_node_types_from_plugin(
                Path("/project/file1.py"), "python"
            )

            covered2 = await _get_covered_node_types_from_plugin(
                Path("/project/file2.py"), "python"
            )

        # 行号匹配：function_definition(0-4) 与 element(0-4) 精确匹配
        assert "function_definition" in covered1
        assert "function_definition" in covered2  # 同 mock，相同结果

    @pytest.mark.asyncio
    async def test_same_position_range_different_files(self):
        """测试相同位置范围但不同文件"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"
        func.start_point = (0, 0)
        func.end_point = (4, 0)
        func.children = []

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.children = [func]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 5

        mock_result = MagicMock()
        mock_result.elements = [mock_element]

        mock_plugin = AsyncMock()
        mock_plugin.analyze_file.return_value = mock_result

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.get_plugin.return_value = mock_plugin

        with (
            patch(
                "tree_sitter_analyzer.plugins.manager.PluginManager",
                return_value=mock_plugin_manager,
            ),
            patch(
                "tree_sitter_analyzer.language_loader.loader.create_parser_safely",
                return_value=mock_parser,
            ),
            patch.object(Path, "read_text", return_value="def foo(): pass"),
        ):
            covered_a = await _get_covered_node_types_from_plugin(
                Path("/a/file.py"), "python"
            )
            covered_b = await _get_covered_node_types_from_plugin(
                Path("/b/file.py"), "python"
            )

        # Both should mark same type
        assert covered_a == covered_b

    @pytest.mark.asyncio
    async def test_cross_file_node_identity_no_conflict(self):
        """测试跨文件节点身份不冲突"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Two different node types, two different files
        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"
        func.start_point = (0, 0)
        func.end_point = (4, 0)
        func.children = []

        root1 = MagicMock()
        root1.is_named = True
        root1.type = "module"
        root1.children = [func]

        tree1 = MagicMock()
        tree1.root_node = root1

        cls = MagicMock()
        cls.is_named = True
        cls.type = "class_definition"
        cls.start_point = (0, 0)
        cls.end_point = (4, 0)
        cls.children = []

        root2 = MagicMock()
        root2.is_named = True
        root2.type = "module"
        root2.children = [cls]

        tree2 = MagicMock()
        tree2.root_node = root2

        mock_parser = MagicMock()
        mock_parser.parse.side_effect = [tree1, tree2]

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 5

        mock_result = MagicMock()
        mock_result.elements = [mock_element]

        mock_plugin = AsyncMock()
        mock_plugin.analyze_file.return_value = mock_result

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.get_plugin.return_value = mock_plugin

        with (
            patch(
                "tree_sitter_analyzer.plugins.manager.PluginManager",
                return_value=mock_plugin_manager,
            ),
            patch(
                "tree_sitter_analyzer.language_loader.loader.create_parser_safely",
                return_value=mock_parser,
            ),
            patch.object(
                Path,
                "read_text",
                side_effect=["def foo(): pass", "class Bar: pass"],
            ),
        ):
            covered1 = await _get_covered_node_types_from_plugin(
                Path("/file1.py"), "python"
            )
            covered2 = await _get_covered_node_types_from_plugin(
                Path("/file2.py"), "python"
            )

        # 行号匹配：file1 的 function_definition(0-4) 匹配，file2 的 class_definition(0-4) 匹配
        assert "function_definition" in covered1
        assert "class_definition" in covered2
        assert "class_definition" not in covered1  # 跨文件不冲突

    @pytest.mark.asyncio
    async def test_empty_file_path_boundary(self):
        """测试 file_path 为空的边界情况"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"
        func.start_point = (0, 0)
        func.end_point = (0, 15)
        func.start_byte = 0
        func.end_byte = 15  # "def foo(): pass"
        func.children = []

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.start_byte = 0
        root.end_byte = 15
        root.children = [func]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 1  # Single line file

        mock_result = MagicMock()
        mock_result.elements = [mock_element]

        mock_plugin = AsyncMock()
        mock_plugin.analyze_file.return_value = mock_result

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.get_plugin.return_value = mock_plugin

        with (
            patch(
                "tree_sitter_analyzer.plugins.manager.PluginManager",
                return_value=mock_plugin_manager,
            ),
            patch(
                "tree_sitter_analyzer.language_loader.loader.create_parser_safely",
                return_value=mock_parser,
            ),
            patch.object(Path, "read_text", return_value="def foo(): pass"),
        ):
            # Empty path should still work
            covered = await _get_covered_node_types_from_plugin(Path(""), "python")

        assert "function_definition" in covered

    @pytest.mark.asyncio
    async def test_relative_vs_absolute_path(self):
        """测试相对路径 vs 绝对路径"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"
        func.start_point = (0, 0)
        func.end_point = (0, 15)
        func.start_byte = 0
        func.end_byte = 15  # "def foo(): pass"
        func.children = []

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.start_byte = 0
        root.end_byte = 15
        root.children = [func]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 1  # Single line file

        mock_result = MagicMock()
        mock_result.elements = [mock_element]

        mock_plugin = AsyncMock()
        mock_plugin.analyze_file.return_value = mock_result

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.get_plugin.return_value = mock_plugin

        with (
            patch(
                "tree_sitter_analyzer.plugins.manager.PluginManager",
                return_value=mock_plugin_manager,
            ),
            patch(
                "tree_sitter_analyzer.language_loader.loader.create_parser_safely",
                return_value=mock_parser,
            ),
            patch.object(Path, "read_text", return_value="def foo(): pass"),
        ):
            covered_rel = await _get_covered_node_types_from_plugin(
                Path("relative/file.py"), "python"
            )
            covered_abs = await _get_covered_node_types_from_plugin(
                Path("/absolute/file.py"), "python"
            )

        # Should produce same coverage (type-based, not path-based)
        assert covered_rel == covered_abs
