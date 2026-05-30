#!/usr/bin/env python3
"""
False Positive Detection Tests for Grammar Coverage Validator — Wrapper Nodes (Part B)

Tests 7-11 from TestWrapperNodesFalsPositives:
- Wrapper node boundary same start line
- Wrapper node partial overlap
- TypeScript decorator method wrapper
- Multiple wrappers at same level
- Deeply nested wrappers (three levels)
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWrapperNodesFalsePositivesB:
    """
    测试 wrapper nodes（包装节点）不会造成 false positives — Part B

    边界情况和复杂嵌套场景。
    """

    @pytest.mark.asyncio
    async def test_wrapper_node_boundary_same_start_line(self):
        """测试边界情况：wrapper 和被包裹节点起始行相同"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # export class Foo {} - export 和 class 都在同一行
        export = MagicMock()
        export.is_named = True
        export.type = "export_statement"
        export.start_point = (0, 0)
        export.end_point = (0, 20)

        class_decl = MagicMock()
        class_decl.is_named = True
        class_decl.type = "class_declaration"
        class_decl.start_point = (0, 7)  # same line
        class_decl.end_point = (0, 20)
        class_decl.children = []

        export.children = [class_decl]

        root = MagicMock()
        root.is_named = True
        root.type = "program"
        root.children = [export]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 1

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
            patch.object(Path, "read_text", return_value="export class Foo {}"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.ts"), "typescript"
            )

        # 修复后（第一匹配 + 跳过根节点）：
        # program 被跳过，export_statement 是第一个非根节点 → 只有它被标记。
        assert "export_statement" in covered
        assert "class_declaration" not in covered

    @pytest.mark.asyncio
    async def test_wrapper_node_partial_overlap(self):
        """测试部分重叠：提取的元素只覆盖 wrapper 的一部分"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Wrapper lines 1-10, extracted element lines 5-10
        wrapper = MagicMock()
        wrapper.is_named = True
        wrapper.type = "wrapper_node"
        wrapper.start_point = (0, 0)  # line 1
        wrapper.end_point = (9, 0)  # line 10

        child = MagicMock()
        child.is_named = True
        child.type = "child_node"
        child.start_point = (4, 0)  # line 5
        child.end_point = (9, 0)  # line 10
        child.children = []

        wrapper.children = [child]

        root = MagicMock()
        root.is_named = True
        root.type = "root"
        root.children = [wrapper]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Extracted element: lines 5-10 (only covers child)
        mock_element = MagicMock()
        mock_element.start_line = 5
        mock_element.end_line = 10

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
            patch.object(Path, "read_text", return_value="code here"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )

        # 行号匹配：child_node(4-9) 与 element(4-9) 精确匹配
        # wrapper_node(0-9) 起始行不同，不匹配（无 false positive）
        assert "child_node" in covered
        assert "wrapper_node" not in covered

    @pytest.mark.asyncio
    async def test_typescript_decorator_method_wrapper(self):
        """测试 TypeScript decorator 包裹的方法"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # decorator
        #   └─ method_definition
        decorator = MagicMock()
        decorator.is_named = True
        decorator.type = "decorator"
        decorator.start_point = (0, 0)
        decorator.end_point = (2, 0)

        method = MagicMock()
        method.is_named = True
        method.type = "method_definition"
        method.start_point = (1, 0)
        method.end_point = (2, 0)
        method.children = []

        decorator.children = [method]

        root = MagicMock()
        root.is_named = True
        root.type = "class_body"
        root.children = [decorator]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

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
            patch.object(Path, "read_text", return_value="@log\nmethod() {}"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.ts"), "typescript"
            )

        # 行号匹配：decorator(0-2) 与 element(0-2) 精确匹配
        # method_definition(1-2) 起始行不同，不匹配（无 false positive）
        assert "decorator" in covered
        assert "method_definition" not in covered

    @pytest.mark.asyncio
    async def test_multiple_wrappers_same_level(self):
        """测试同级多个 wrapper nodes"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Two decorated functions at same level
        dec1 = MagicMock()
        dec1.is_named = True
        dec1.type = "decorated_definition"
        dec1.start_point = (0, 0)
        dec1.end_point = (2, 0)

        func1 = MagicMock()
        func1.is_named = True
        func1.type = "function_definition"
        func1.start_point = (1, 0)
        func1.end_point = (2, 0)
        func1.children = []

        dec1.children = [func1]

        dec2 = MagicMock()
        dec2.is_named = True
        dec2.type = "decorated_definition"
        dec2.start_point = (4, 0)
        dec2.end_point = (6, 0)

        func2 = MagicMock()
        func2.is_named = True
        func2.type = "function_definition"
        func2.start_point = (5, 0)
        func2.end_point = (6, 0)
        func2.children = []

        dec2.children = [func2]

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.children = [dec1, dec2]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Only extracted first decorator
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
                Path,
                "read_text",
                return_value="@d\ndef f1(): pass\n\n@d\ndef f2(): pass",
            ),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.py"), "python"
            )

        # 行号匹配：dec1(0-2) 与 element(0-2) 精确匹配，dec2(4-6) 和 func1/func2 不匹配
        assert "decorated_definition" in covered
        assert "function_definition" not in covered

    @pytest.mark.asyncio
    async def test_deeply_nested_wrappers_three_levels(self):
        """测试三层嵌套 wrapper"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # level1 > level2 > level3 > actual_node
        level1 = MagicMock()
        level1.is_named = True
        level1.type = "wrapper_level1"
        level1.start_point = (0, 0)
        level1.end_point = (10, 0)

        level2 = MagicMock()
        level2.is_named = True
        level2.type = "wrapper_level2"
        level2.start_point = (1, 0)
        level2.end_point = (10, 0)

        level3 = MagicMock()
        level3.is_named = True
        level3.type = "wrapper_level3"
        level3.start_point = (2, 0)
        level3.end_point = (10, 0)

        actual = MagicMock()
        actual.is_named = True
        actual.type = "actual_node"
        actual.start_point = (3, 0)
        actual.end_point = (10, 0)
        actual.children = []

        level3.children = [actual]
        level2.children = [level3]
        level1.children = [level2]

        root = MagicMock()
        root.is_named = True
        root.type = "root"
        root.children = [level1]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Extracted only level1
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
            patch.object(Path, "read_text", return_value="nested code"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.txt"), "generic"
            )

        # 行号匹配：wrapper_level1(0-10) 与 element(0-10) 精确匹配
        # level2/level3/actual_node 起始行不同，均不匹配（无 false positive）
        assert "wrapper_level1" in covered
        assert "wrapper_level2" not in covered
        assert "wrapper_level3" not in covered
        assert "actual_node" not in covered
