#!/usr/bin/env python3
"""
False Positive Detection Tests for Grammar Coverage Validator — Wrapper Nodes (Part C)

Tests 12-15 from TestWrapperNodesFalsPositives:
- Wrapper with multiple children
- No wrapper direct extraction
- Adjacent nodes no overlap
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWrapperNodesFalsePositivesC:
    """
    测试 wrapper nodes（包装节点）不会造成 false positives — Part C

    多子节点、直接提取和相邻节点场景。
    """

    @pytest.mark.asyncio
    async def test_wrapper_with_multiple_children(self):
        """测试 wrapper 包含多个子节点"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # wrapper
        #   ├─ child1
        #   ├─ child2
        #   └─ child3
        wrapper = MagicMock()
        wrapper.is_named = True
        wrapper.type = "wrapper"
        wrapper.start_point = (0, 0)
        wrapper.end_point = (10, 0)

        child1 = MagicMock()
        child1.is_named = True
        child1.type = "child_type_a"
        child1.start_point = (1, 0)
        child1.end_point = (3, 0)
        child1.children = []

        child2 = MagicMock()
        child2.is_named = True
        child2.type = "child_type_b"
        child2.start_point = (4, 0)
        child2.end_point = (6, 0)
        child2.children = []

        child3 = MagicMock()
        child3.is_named = True
        child3.type = "child_type_c"
        child3.start_point = (7, 0)
        child3.end_point = (10, 0)
        child3.children = []

        wrapper.children = [child1, child2, child3]

        root = MagicMock()
        root.is_named = True
        root.type = "root"
        root.children = [wrapper]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Extracted wrapper only
        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 11

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
            patch.object(Path, "read_text", return_value="wrapper with children"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )

        # 行号匹配：wrapper(0-10) 与 element(0-10) 精确匹配
        # 三个子节点(1-3, 4-6, 7-10) 起始行不同，均不匹配
        assert "wrapper" in covered
        assert "child_type_a" not in covered
        assert "child_type_b" not in covered
        assert "child_type_c" not in covered

    @pytest.mark.asyncio
    async def test_no_wrapper_direct_extraction(self):
        """测试没有 wrapper 的直接提取（正常情况，无 false positive）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Just function_definition, no wrapper
        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"
        func.start_point = (0, 0)
        func.end_point = (5, 0)
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
        mock_element.end_line = 6

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
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.py"), "python"
            )

        # 行号匹配：function_definition(0-5) 与 element(0-5) 精确匹配（正常直接提取）
        assert "function_definition" in covered

    @pytest.mark.asyncio
    async def test_adjacent_nodes_no_overlap(self):
        """测试相邻节点无重叠（应该正确区分）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # func1 (lines 1-3), func2 (lines 5-7), extracted only func1
        func1 = MagicMock()
        func1.is_named = True
        func1.type = "function_definition"
        func1.start_point = (0, 0)
        func1.end_point = (2, 0)
        func1.children = []

        func2 = MagicMock()
        func2.is_named = True
        func2.type = "function_definition"
        func2.start_point = (4, 0)
        func2.end_point = (6, 0)
        func2.children = []

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.children = [func1, func2]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Extracted only func1
        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 3

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
                Path, "read_text", return_value="def f1(): pass\n\ndef f2(): pass"
            ),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.py"), "python"
            )

        # 行号匹配：func1(0-2) 与 element(0-2) 精确匹配；func2(4-6) 不匹配（正确区分相邻节点）
        assert "function_definition" in covered  # func1 覆盖
        # func2 虽然类型相同，但它的行范围(4-6)与 element(0-2) 不匹配，不增加新 type
