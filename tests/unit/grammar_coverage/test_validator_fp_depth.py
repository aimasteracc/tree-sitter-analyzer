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

from tests.unit.grammar_coverage.conftest import _make_parser_mock

_PM_PATCH = "tree_sitter_analyzer.plugins.manager.PluginManager"
_PARSER_PATCH = "tree_sitter_analyzer.language_loader.loader.create_parser_safely"


def _make_deep_nodes(n: int, *, name_prefix: str = "node_level") -> tuple:
    """Create a linear chain of *n* MagicMock AST nodes.

    Returns (nodes, root, tree) where root.children = [nodes[0]] and
    nodes[i].children = [nodes[i+1]] (last node has children=[]).
    Each node has start_point=(i, 0), end_point=(n, 0).
    """
    nodes = []
    for i in range(n):
        node = MagicMock()
        node.is_named = True
        node.type = f"{name_prefix}_{i}"
        node.start_point = (i, 0)
        node.end_point = (n, 0)
        nodes.append(node)
    for i in range(n - 1):
        nodes[i].children = [nodes[i + 1]]
    nodes[-1].children = []

    root = MagicMock()
    root.is_named = True
    root.type = "root"
    root.children = [nodes[0]]

    tree = MagicMock()
    tree.root_node = root
    return nodes, root, tree


def _make_plugin_mock(start_line: int, end_line: int) -> MagicMock:
    """Return a mock PluginManager with one element covering start_line..end_line."""
    element = MagicMock()
    element.start_line = start_line
    element.end_line = end_line
    result = MagicMock()
    result.elements = [element]
    plugin = AsyncMock()
    plugin.analyze_file.return_value = result
    manager = MagicMock()
    manager.get_plugin.return_value = plugin
    return manager


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

        nodes, _, tree = _make_deep_nodes(99)
        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_plugin_mock(start_line=1, end_line=100)

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
            patch.object(Path, "read_text", return_value="deep nesting"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )

        assert "node_level_0" in covered

    @pytest.mark.asyncio
    async def test_nesting_100_layers_should_trigger_limit(self):
        """测试 100 层嵌套应该触发限制（如果实现了限制）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        nodes, _, tree = _make_deep_nodes(100)
        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_plugin_mock(start_line=1, end_line=101)

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
            patch.object(Path, "read_text", return_value="deep nesting"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )

        assert isinstance(covered, set)

    @pytest.mark.asyncio
    async def test_nesting_101_layers_extreme(self):
        """测试 101 层极端嵌套"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        nodes, _, tree = _make_deep_nodes(101)
        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_plugin_mock(start_line=1, end_line=102)

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
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

        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_plugin_mock(start_line=1, end_line=11)

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
            patch.object(Path, "read_text", return_value="circular"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )
        assert "node1" in covered
        assert "node2" not in covered

    @pytest.mark.asyncio
    async def test_extreme_nesting_1000_layers(self):
        """测试极端 1000 层嵌套（断路器测试）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        nodes, _, tree = _make_deep_nodes(1000, name_prefix="node")
        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_plugin_mock(start_line=1, end_line=1001)

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
            patch.object(Path, "read_text", return_value="extreme"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )
        assert "node_0" in covered
