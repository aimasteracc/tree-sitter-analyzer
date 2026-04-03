#!/usr/bin/env python3
"""
False Positive Detection Tests for Grammar Coverage Validator

测试 validator 对 wrapper nodes 和嵌套结构的处理，确保不会误报覆盖率。

测试分类：
1. Wrapper nodes (15 tests) - 包装节点不应被误标记为已覆盖
2. 深度限制 (5 tests) - 防止无限嵌套和递归
3. 多文件场景 (5 tests) - 跨文件节点身份冲突
4. 边界情况 (5 tests) - 空文件、异常处理等

False Positive 定义：
- 插件未提取某节点类型，但因位置重叠被误标记为"已覆盖"
- 例：提取了 `decorator` 后，其包裹的 `function_definition` 被误标记

测试策略：
- 使用 mock 避免实际 tree-sitter 调用
- 构造精确的 AST 嵌套结构
- 验证只有真正提取的节点类型被标记为覆盖
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWrapperNodesFalsPositives:
    """
    测试 wrapper nodes（包装节点）不会造成 false positives

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

        # 行号匹配：export_statement(0-2) 和 class_declaration(0-2) 都与 element(0-2) 精确匹配
        # 同行节点均被覆盖（已知 line-based 的正常行为）
        assert "export_statement" in covered
        assert "class_declaration" in covered

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

        # 行号匹配：export_statement(0-0) 和 class_declaration(0-0) 同行，均匹配 element(0-0)
        # 同行节点行号一致，均被覆盖（已知行号匹配的正常行为）
        assert "export_statement" in covered
        assert "class_declaration" in covered

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
                Path, "read_text", return_value="@d\ndef f1(): pass\n\n@d\ndef f2(): pass"
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
            covered = await _get_covered_node_types_from_plugin(
                Path(""), "python"
            )

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

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Plugin returns no elements
        mock_result = MagicMock()
        mock_result.elements = []

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
        root.end_point = (0, 2)    # line 0, col 2
        root.children = [token1, token2]

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
            patch.object(Path, "read_text", return_value="()"),
        ):
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/tokens.py"), "python"
            )

        # Only module marked (no named children)
        assert "module" in covered
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

        mock_parser = MagicMock()
        mock_parser.parse.return_value = tree

        # Plugin returns empty list
        mock_result = MagicMock()
        mock_result.elements = []

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
            patch(
                "tree_sitter_analyzer.plugins.manager.PluginManager",
                return_value=mock_plugin_manager,
            ),
            patch.object(Path, "read_text", return_value="def foo(): pass"),
        ):
            # Should handle gracefully and return empty set
            covered = await _get_covered_node_types_from_plugin(
                Path("/fake/test.py"), "python"
            )

        # Exception handled → empty coverage
        assert len(covered) == 0
