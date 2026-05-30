#!/usr/bin/env python3
"""
False Positive Detection Tests for Grammar Coverage Validator — Boundary Cases

Tests for TestBoundaryCases:
- Empty file
- Single node file
- No named nodes (only tokens)
- Plugin returns empty elements
- Plugin raises exception
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.grammar_coverage.conftest import _make_parser_mock

_PM_PATCH = "tree_sitter_analyzer.plugins.manager.PluginManager"
_PARSER_PATCH = "tree_sitter_analyzer.language_loader.loader.create_parser_safely"


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


def _make_empty_plugin_mock() -> MagicMock:
    """Return a mock PluginManager whose plugin returns no elements."""
    result = MagicMock()
    result.elements = []
    plugin = AsyncMock()
    plugin.analyze_file.return_value = result
    manager = MagicMock()
    manager.get_plugin.return_value = plugin
    return manager


class TestBoundaryCases:
    """
    测试边界情况和异常处理

    场景：
    - 空文件
    - 单节点文件
    - 无命名节点（只有 token）
    - 插件返回空元素列表
    - 插件抛出异常
    """

    @pytest.mark.asyncio
    async def test_empty_file(self):
        """测试空文件"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Empty file: only root module
        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.start_point = (0, 0)
        root.end_point = (0, 0)
        root.children = []

        tree = MagicMock()
        tree.root_node = root

        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_empty_plugin_mock()

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
            patch.object(Path, "read_text", return_value=""),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/empty.py"), "python"
            )

        # Empty file: no coverage
        assert len(covered) == 0

    @pytest.mark.asyncio
    async def test_single_node_file(self):
        """测试单节点文件"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Just one expression
        expr = MagicMock()
        expr.is_named = True
        expr.type = "expression_statement"
        expr.start_point = (0, 0)
        expr.end_point = (0, 11)
        expr.start_byte = 0
        expr.end_byte = 11  # "print('hi')"
        expr.children = []

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.start_byte = 0
        root.end_byte = 11
        root.children = [expr]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_plugin_mock(start_line=1, end_line=1)

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
            patch.object(Path, "read_text", return_value="print('hi')"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/single.py"), "python"
            )

        assert "expression_statement" in covered

    @pytest.mark.asyncio
    async def test_no_named_nodes_only_tokens(self):
        """测试无命名节点（只有 token）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Only unnamed nodes (tokens like "(", ")", ",")
        token1 = MagicMock()
        token1.is_named = False
        token1.type = "("
        token1.start_byte = 0
        token1.end_byte = 1
        token1.children = []

        token2 = MagicMock()
        token2.is_named = False
        token2.type = ")"
        token2.start_byte = 1
        token2.end_byte = 2
        token2.children = []

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.start_byte = 0
        root.end_byte = 2  # "()"
        root.start_point = (0, 0)  # line 0, col 0
        root.end_point = (0, 2)  # line 0, col 2
        root.children = [token1, token2]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_plugin_mock(start_line=1, end_line=1)

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
            patch.object(Path, "read_text", return_value="()"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/tokens.py"), "python"
            )

        # module は根ノードとしてスキップされるため covered は空。
        # 名前なしノード（括弧）は元々カウントされない。
        assert "module" not in covered
        assert "(" not in covered  # Unnamed nodes not counted

    @pytest.mark.asyncio
    async def test_plugin_returns_empty_elements(self):
        """测试插件返回空元素列表"""
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

        mock_parser = _make_parser_mock(tree)
        mock_plugin_manager = _make_empty_plugin_mock()

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch(_PARSER_PATCH, return_value=mock_parser),
            patch.object(Path, "read_text", return_value="def foo(): pass"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.py"), "python"
            )

        # No extraction → no coverage
        assert len(covered) == 0

    @pytest.mark.asyncio
    async def test_plugin_raises_exception(self):
        """测试插件抛出异常"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        mock_plugin = AsyncMock()
        mock_plugin.analyze_file.side_effect = RuntimeError("Plugin crashed")

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.get_plugin.return_value = mock_plugin

        with (
            patch(_PM_PATCH, return_value=mock_plugin_manager),
            patch.object(Path, "read_text", return_value="def foo(): pass"),
        ):
            # Should handle gracefully and return empty set
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.py"), "python"
            )

        # Exception handled → empty coverage
        assert len(covered) == 0
