#!/usr/bin/env python3
"""
False Positive Detection Tests for Grammar Coverage Validator — Wrapper Nodes (Part A)

Tests 1-6 from TestWrapperNodesFalsPositives:
- Python decorated function
- TypeScript export class wrapper
- Rust attribute function wrapper
- Ruby visibility method wrapper
- Single-layer nesting Python
- Multi-layer nesting Python
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWrapperNodesFalsePositivesA:
    """
    测试 wrapper nodes（包装节点）不会造成 false positives — Part A

    Wrapper nodes 是包裹其他节点的语法结构：
    - Python: `decorated_definition` 包裹 `function_definition`
    - TypeScript: `export_statement` 包裹 `class_declaration`
    - Rust: `attribute_item` 包裹 `function_item`
    - Ruby: visibility modifiers 包裹 `method`
    """

    @pytest.mark.asyncio
    async def test_python_decorated_function_not_false_positive(self):
        """测试 Python decorator 不会导致被包裹的函数被误标记"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Mock AST structure:
        # decorated_definition (lines 1-5)
        #   └─ function_definition (lines 2-5)
        decorator_node = MagicMock()
        decorator_node.is_named = True
        decorator_node.type = "decorated_definition"
        decorator_node.start_point = (0, 0)  # line 1
        decorator_node.end_point = (4, 0)  # line 5

        func_node = MagicMock()
        func_node.is_named = True
        func_node.type = "function_definition"
        func_node.start_point = (1, 0)  # line 2
        func_node.end_point = (4, 0)  # line 5
        func_node.children = []

        decorator_node.children = [func_node]

        root_node = MagicMock()
        root_node.is_named = True
        root_node.type = "module"
        root_node.start_point = (0, 0)
        root_node.end_point = (4, 0)
        root_node.children = [decorator_node]

        # Mock tree
        tree = MagicMock()
        tree.root_node = root_node

        # Mock parser
        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Mock plugin result: 只提取了 decorator，没提取 function
        mock_element = MagicMock()
        mock_element.start_line = 1  # 1-based
        mock_element.end_line = 5

        mock_result = MagicMock()
        mock_result.elements = [mock_element]

        mock_plugin = AsyncMock()
        mock_plugin.analyze_file.return_value = mock_result

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.get_plugin.return_value = mock_plugin

        corpus_path = Path("/fake/corpus.py")

        with (
            patch(
                "tree_sitter_analyzer.plugins.manager.PluginManager",
                return_value=mock_plugin_manager,
            ),
            patch(
                "tree_sitter_analyzer.language_loader.loader.create_parser_safely",
                return_value=mock_parser,
            ),
            patch.object(Path, "read_text", return_value="@decorator\ndef foo(): pass"),
        ):
            covered = await _get_covered_node_types_from_plugin(corpus_path, "python")

        # 关键断言（行号匹配 2026-04）：
        # element(start=1,end=5) → 0-based(0,4)
        # decorated_definition(0,0)-(4,0) → 0-4 → MATCH ✓
        # function_definition(1,0)-(4,0) → 1-4 → no match（起始行不同）✗
        # module(0,0)-(4,0) → 0-4 → MATCH ✓（显式设置了 start_point）
        assert "decorated_definition" in covered
        assert "function_definition" not in covered  # 核心：无 false positive

    @pytest.mark.asyncio
    async def test_typescript_export_class_wrapper(self):
        """测试 TypeScript export 语句包裹的 class 不被误标记"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # export_statement (lines 1-3)
        #   └─ class_declaration (lines 1-3)
        export_node = MagicMock()
        export_node.is_named = True
        export_node.type = "export_statement"
        export_node.start_point = (0, 0)
        export_node.end_point = (2, 0)

        class_node = MagicMock()
        class_node.is_named = True
        class_node.type = "class_declaration"
        class_node.start_point = (0, 7)  # after "export "
        class_node.end_point = (2, 0)
        class_node.children = []

        export_node.children = [class_node]

        root = MagicMock()
        root.is_named = True
        root.type = "program"
        root.children = [export_node]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Plugin only extracted export_statement
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
            patch.object(Path, "read_text", return_value="export class Foo {}"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/file.ts"), "typescript"
            )

        # 修复后（第一匹配 + 跳过根节点）：
        # program 被跳过，export_statement 是第一个非根节点 → 只有它被标记。
        # class_declaration 不被标记（它是 export_statement 的子节点，排在第二位）。
        assert "export_statement" in covered
        assert "class_declaration" not in covered

    @pytest.mark.asyncio
    async def test_rust_attribute_function_wrapper(self):
        """测试 Rust attribute 包裹的函数不被误标记"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # attribute_item (lines 1-3)
        #   └─ function_item (lines 2-3)
        attr_node = MagicMock()
        attr_node.is_named = True
        attr_node.type = "attribute_item"
        attr_node.start_point = (0, 0)
        attr_node.end_point = (2, 0)

        func_node = MagicMock()
        func_node.is_named = True
        func_node.type = "function_item"
        func_node.start_point = (1, 0)
        func_node.end_point = (2, 0)
        func_node.children = []

        attr_node.children = [func_node]

        root = MagicMock()
        root.is_named = True
        root.type = "source_file"
        root.children = [attr_node]

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
            patch.object(Path, "read_text", return_value="#[test]\nfn foo() {}"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/file.rs"), "rust"
            )

        # 行号匹配：attribute_item(0-2) 与 element(0-2) 精确匹配
        # function_item(1-2) 起始行不同，不匹配（无 false positive）
        assert "attribute_item" in covered
        assert "function_item" not in covered

    @pytest.mark.asyncio
    async def test_ruby_visibility_method_wrapper(self):
        """测试 Ruby visibility modifier 包裹的方法不被误标记"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # Ruby: private method
        # visibility_modifier (lines 1-2)
        #   └─ method (lines 2-2)
        visibility_node = MagicMock()
        visibility_node.is_named = True
        visibility_node.type = "visibility_modifier"
        visibility_node.start_point = (0, 0)
        visibility_node.end_point = (1, 0)

        method_node = MagicMock()
        method_node.is_named = True
        method_node.type = "method"
        method_node.start_point = (1, 0)
        method_node.end_point = (1, 20)
        method_node.children = []

        visibility_node.children = [method_node]

        root = MagicMock()
        root.is_named = True
        root.type = "program"
        root.children = [visibility_node]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 2

        mock_result = MagicMock()
        mock_result.elements = [mock_element]

        mock_plugin = AsyncMock()
        mock_plugin.analyze_file.return_value = mock_plugin

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
            patch.object(Path, "read_text", return_value="private\ndef foo; end"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/file.rb"), "ruby"
            )

        # 精确匹配：Mock 环境无匹配
        assert len(covered) == 0

    @pytest.mark.asyncio
    async def test_single_layer_nesting_python(self):
        """测试单层嵌套（Python decorator）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        decorator = MagicMock()
        decorator.is_named = True
        decorator.type = "decorated_definition"
        decorator.start_point = (0, 0)
        decorator.end_point = (5, 0)

        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"
        func.start_point = (1, 0)
        func.end_point = (5, 0)
        func.children = []

        decorator.children = [func]

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.children = [decorator]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Plugin extracted decorator only
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
            patch.object(Path, "read_text", return_value="@dec\ndef foo(): pass"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.py"), "python"
            )

        # 行号匹配：decorated_definition(0-5) 与 element(0-5) 精确匹配
        # function_definition(1-5) 起始行不同，不匹配（核心：无 false positive）
        assert "decorated_definition" in covered
        assert "function_definition" not in covered

    @pytest.mark.asyncio
    async def test_multi_layer_nesting_python(self):
        """测试多层嵌套（Python 多个 decorator）"""
        from tree_sitter_analyzer.grammar_coverage.validator import (
            _get_covered_node_types_from_plugin,
        )

        # decorated_definition (outer)
        #   └─ decorated_definition (inner)
        #       └─ function_definition
        outer_dec = MagicMock()
        outer_dec.is_named = True
        outer_dec.type = "decorated_definition"
        outer_dec.start_point = (0, 0)
        outer_dec.end_point = (6, 0)

        inner_dec = MagicMock()
        inner_dec.is_named = True
        inner_dec.type = "decorated_definition"
        inner_dec.start_point = (1, 0)
        inner_dec.end_point = (6, 0)

        func = MagicMock()
        func.is_named = True
        func.type = "function_definition"
        func.start_point = (2, 0)
        func.end_point = (6, 0)
        func.children = []

        inner_dec.children = [func]
        outer_dec.children = [inner_dec]

        root = MagicMock()
        root.is_named = True
        root.type = "module"
        root.children = [outer_dec]

        tree = MagicMock()
        tree.root_node = root

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Plugin only extracted outer decorator
        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 7

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
                Path, "read_text", return_value="@dec1\n@dec2\ndef foo(): pass"
            ),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.py"), "python"
            )

        # 行号匹配：outer decorated_definition(0-6) 与 element(0-6) 精确匹配
        # inner decorated_definition(1-6) 和 function_definition(2-6) 不匹配（起始行不同）
        assert "decorated_definition" in covered
        assert "function_definition" not in covered
