#!/usr/bin/env python3
"""
False Positive Detection Tests for Grammar Coverage Validator — Depth Limit

Tests for TestDepthLimitFalsePositives:
- 99 layers nesting should pass
- 100 layers should trigger limit
- 101 layers extreme
- Circular reference detection
- Extreme 1000 layers (circuit breaker)
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDepthLimitFalsePositives:
    """
    测试深度限制防止无限嵌套和递归

    防止：
    - 病态深度嵌套（>100 层）
    - 循环引用导致的无限递归
    - 栈溢出风险
    """

    @pytest.mark.asyncio
    async def test_nesting_99_layers_should_pass(self):
        """测试 99 层嵌套应该通过"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Create 99-layer deep nesting
        nodes = []
        for i in range(99):
            node = MagicMock()
            node.is_named = True
            node.type = f"node_level_{i}"
            node.start_point = (i, 0)
            node.end_point = (99, 0)
            nodes.append(node)

        # Wire up parent-child relationships
        for i in range(98):
            nodes[i].children = [nodes[i + 1]]
        nodes[98].children = []

        root = MagicMock()
        root.is_named = True
        root.type = "root"
        root.children = [nodes[0]]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 100

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
            patch.object(Path, "read_text", return_value="deep nesting"),
        ):
            # Should not raise RecursionError
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )

        # 行号匹配：node_level_0(0-99) 与 element(0-99) 精确匹配；其余层起始行不同
        assert "node_level_0" in covered

    @pytest.mark.asyncio
    async def test_nesting_100_layers_should_trigger_limit(self):
        """测试 100 层嵌套应该触发限制（如果实现了限制）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Create 100-layer deep nesting
        nodes = []
        for i in range(100):
            node = MagicMock()
            node.is_named = True
            node.type = f"node_level_{i}"
            node.start_point = (i, 0)
            node.end_point = (100, 0)
            nodes.append(node)

        for i in range(99):
            nodes[i].children = [nodes[i + 1]]
        nodes[99].children = []

        root = MagicMock()
        root.is_named = True
        root.type = "root"
        root.children = [nodes[0]]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 101

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
            patch.object(Path, "read_text", return_value="deep nesting"),
        ):
            # TODO: If Agent 1 implements depth limit, this should trigger warning
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )

        # Current behavior: should still work
        assert isinstance(covered, set)

    @pytest.mark.asyncio
    async def test_nesting_101_layers_extreme(self):
        """测试 101 层极端嵌套"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        nodes = []
        for i in range(101):
            node = MagicMock()
            node.is_named = True
            node.type = f"node_level_{i}"
            node.start_point = (i, 0)
            node.end_point = (101, 0)
            nodes.append(node)

        for i in range(100):
            nodes[i].children = [nodes[i + 1]]
        nodes[100].children = []

        root = MagicMock()
        root.is_named = True
        root.type = "root"
        root.children = [nodes[0]]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 102

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
            patch.object(Path, "read_text", return_value="extreme nesting"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )

        assert isinstance(covered, set)

    @pytest.mark.asyncio
    async def test_circular_reference_detection(self):
        """测试循环引用检测（病态 AST）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Create circular reference: node1 -> node2 -> node1
        node1 = MagicMock()
        node1.is_named = True
        node1.type = "node1"
        node1.start_point = (0, 0)
        node1.end_point = (10, 0)

        node2 = MagicMock()
        node2.is_named = True
        node2.type = "node2"
        node2.start_point = (1, 0)
        node2.end_point = (10, 0)

        # Circular reference (should never happen in real tree-sitter, but defensive coding)
        node1.children = [node2]
        node2.children = [node1]  # Circular!

        root = MagicMock()
        root.is_named = True
        root.type = "root"
        root.children = [node1]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

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
            patch.object(Path, "read_text", return_value="circular"),
        ):
            # Should handle gracefully without infinite loop
            # Implementation has recursion limit防护，不会抛出 RecursionError
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )
        # 行号匹配：node1(0-10) 与 element(0-10) 精确匹配；深度限制防止无限循环
        assert "node1" in covered
        # node2(1-10) 起始行不同，不匹配（无 false positive）
        assert "node2" not in covered

    @pytest.mark.asyncio
    async def test_extreme_nesting_1000_layers(self):
        """测试极端 1000 层嵌套（断路器测试）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # This should trigger recursion limit in Python
        nodes = []
        for i in range(1000):
            node = MagicMock()
            node.is_named = True
            node.type = f"node_{i}"
            node.start_point = (i, 0)
            node.end_point = (1000, 0)
            nodes.append(node)

        for i in range(999):
            nodes[i].children = [nodes[i + 1]]
        nodes[999].children = []

        root = MagicMock()
        root.is_named = True
        root.type = "root"
        root.children = [nodes[0]]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 1001

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
            patch.object(Path, "read_text", return_value="extreme"),
        ):
            # 递归限制保护，不会触发 RecursionError
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )
        # 行号匹配：node_0(0-1000) 与 element(0-1000) 精确匹配（深度限制内的第一个节点）
        assert "node_0" in covered
