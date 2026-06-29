#!/usr/bin/env python3
"""Tests for plugins/_base_traverse_mixin.py — node classification, traversal, and text extraction."""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.models import Class as ModelClass
from tree_sitter_analyzer.models import Function as ModelFunction
from tree_sitter_analyzer.models import Import as ModelImport
from tree_sitter_analyzer.models import Variable as ModelVariable
from tree_sitter_analyzer.plugins._base_traverse_mixin import (
    CLASS_NODE_TYPES,
    FUNCTION_NODE_TYPES,
    IMPORT_NODE_TYPES,
    VARIABLE_NODE_TYPES,
    DefaultNodeMixin,
    DefaultTraverseAppendMixin,
    DefaultTraverseMixin,
    _extract_node_text,
    _find_identifier_child,
    _format_fallback_node_name,
    _get_language_hint,
    _is_class_node,
    _is_function_node,
    _is_import_node,
    _is_variable_node,
    _iter_children,
    _node_end_line,
    _node_start_line,
    _node_type_matches,
    _tree_root_node,
)


def _make_node(
    node_type: str = "",
    start_row: int = 0,
    start_col: int = 0,
    end_row: int = 0,
    end_col: int = 0,
    start_byte: int = 0,
    end_byte: int = 0,
    children: tuple | None = None,
    text: str = "",
):
    node = MagicMock()
    node.type = node_type
    node.start_point = (start_row, start_col)
    node.end_point = (end_row, end_col)
    node.start_byte = start_byte
    node.end_byte = end_byte
    node.children = children if children is not None else ()
    if text:
        node.text = text.encode("utf-8")
    return node


def _make_tree(root_node=None):
    tree = MagicMock()
    tree.root_node = root_node
    return tree


class TestNodeTypeConstants:
    def test_function_node_types_is_tuple(self) -> None:
        assert isinstance(FUNCTION_NODE_TYPES, tuple)

    def test_class_node_types_is_tuple(self) -> None:
        assert isinstance(CLASS_NODE_TYPES, tuple)

    def test_variable_node_types_is_tuple(self) -> None:
        assert isinstance(VARIABLE_NODE_TYPES, tuple)

    def test_import_node_types_is_tuple(self) -> None:
        assert isinstance(IMPORT_NODE_TYPES, tuple)

    def test_function_node_types_contains_key_variants(self) -> None:
        assert "function_definition" in FUNCTION_NODE_TYPES
        assert "function_declaration" in FUNCTION_NODE_TYPES
        assert "method_definition" in FUNCTION_NODE_TYPES
        assert "method" in FUNCTION_NODE_TYPES

    def test_class_node_types_contains_key_variants(self) -> None:
        assert "class_definition" in CLASS_NODE_TYPES
        assert "class" in CLASS_NODE_TYPES
        assert "interface" in CLASS_NODE_TYPES
        assert "struct" in CLASS_NODE_TYPES
        assert "enum" in CLASS_NODE_TYPES

    def test_variable_node_types_contains_key_variants(self) -> None:
        assert "variable_declaration" in VARIABLE_NODE_TYPES
        assert "field_declaration" in VARIABLE_NODE_TYPES
        assert "assignment" in VARIABLE_NODE_TYPES
        assert "variable" in VARIABLE_NODE_TYPES

    def test_import_node_types_contains_key_variants(self) -> None:
        assert "import_statement" in IMPORT_NODE_TYPES
        assert "include" in IMPORT_NODE_TYPES
        assert "require" in IMPORT_NODE_TYPES
        assert "use" in IMPORT_NODE_TYPES


class TestNodeStartLine:
    def test_with_start_point(self) -> None:
        node = _make_node(start_row=5, start_col=10)
        assert _node_start_line(node) == 6

    def test_with_zero_start_point(self) -> None:
        node = _make_node(start_row=0, start_col=0)
        assert _node_start_line(node) == 1

    def test_without_start_point(self) -> None:
        node = MagicMock(spec=[])
        del node.start_point
        assert _node_start_line(node) == 0


class TestNodeEndLine:
    def test_with_end_point(self) -> None:
        node = _make_node(end_row=10, end_col=5)
        assert _node_end_line(node) == 11

    def test_with_zero_end_point(self) -> None:
        node = _make_node(end_row=0, end_col=0)
        assert _node_end_line(node) == 1

    def test_without_end_point(self) -> None:
        node = MagicMock(spec=[])
        del node.end_point
        assert _node_end_line(node) == 0


class TestIterChildren:
    def test_with_children(self) -> None:
        child1 = _make_node("child1")
        child2 = _make_node("child2")
        node = _make_node(children=(child1, child2))
        result = _iter_children(node)
        assert tuple(result) == (child1, child2)

    def test_with_empty_children(self) -> None:
        node = _make_node(children=())
        result = _iter_children(node)
        assert tuple(result) == ()

    def test_without_children_attr(self) -> None:
        node = MagicMock(spec=[])
        result = _iter_children(node)
        assert tuple(result) == ()


class TestTreeRootNode:
    def test_with_root_node(self) -> None:
        root = _make_node("root")
        tree = _make_tree(root)
        assert _tree_root_node(tree) is root

    def test_with_none_root(self) -> None:
        tree = _make_tree(None)
        assert _tree_root_node(tree) is None

    def test_without_root_node_attr(self) -> None:
        tree = MagicMock(spec=[])
        del tree.root_node
        assert _tree_root_node(tree) is None


class TestNodeTypeMatches:
    def test_exact_match(self) -> None:
        assert (
            _node_type_matches("function_definition", ("function_definition",)) is True
        )

    def test_case_insensitive_match(self) -> None:
        assert (
            _node_type_matches("Function_Definition", ("function_definition",)) is True
        )

    def test_substring_match(self) -> None:
        assert _node_type_matches("function_definition", ("function",)) is True

    def test_no_match(self) -> None:
        assert _node_type_matches("variable_declaration", ("function",)) is False

    def test_empty_node_type(self) -> None:
        assert _node_type_matches("", ("function",)) is False

    def test_empty_candidates(self) -> None:
        assert _node_type_matches("function", ()) is False

    def test_multiple_candidates_first_match(self) -> None:
        assert _node_type_matches("method", ("function", "method")) is True

    def test_multiple_candidates_second_match(self) -> None:
        assert _node_type_matches("subroutine", ("function", "subroutine")) is True


class TestIsFunctionNode:
    @pytest.mark.parametrize(
        "node_type",
        [
            "function_definition",
            "function_declaration",
            "method_definition",
            "function",
            "method",
            "procedure",
            "subroutine",
        ],
    )
    def test_function_types(self, node_type: str) -> None:
        assert _is_function_node(node_type) is True

    def test_non_function_type(self) -> None:
        assert _is_function_node("class") is False

    def test_case_insensitive(self) -> None:
        assert _is_function_node("Function_Definition") is True

    def test_empty_string(self) -> None:
        assert _is_function_node("") is False


class TestIsClassNode:
    @pytest.mark.parametrize(
        "node_type",
        [
            "class_definition",
            "class_declaration",
            "interface_definition",
            "class",
            "interface",
            "struct",
            "enum",
        ],
    )
    def test_class_types(self, node_type: str) -> None:
        assert _is_class_node(node_type) is True

    def test_non_class_type(self) -> None:
        assert _is_class_node("function") is False

    def test_case_insensitive(self) -> None:
        assert _is_class_node("Class") is True


class TestIsVariableNode:
    @pytest.mark.parametrize(
        "node_type",
        [
            "variable_declaration",
            "variable_definition",
            "field_declaration",
            "assignment",
            "declaration",
            "variable",
            "field",
        ],
    )
    def test_variable_types(self, node_type: str) -> None:
        assert _is_variable_node(node_type) is True

    def test_non_variable_type(self) -> None:
        assert _is_variable_node("class") is False

    def test_case_insensitive(self) -> None:
        assert _is_variable_node("Variable") is True


class TestIsImportNode:
    @pytest.mark.parametrize(
        "node_type",
        [
            "import_statement",
            "import_declaration",
            "include_statement",
            "import",
            "include",
            "require",
            "use",
        ],
    )
    def test_import_types(self, node_type: str) -> None:
        assert _is_import_node(node_type) is True

    def test_non_import_type(self) -> None:
        assert _is_import_node("function") is False

    def test_case_insensitive(self) -> None:
        assert _is_import_node("Import") is True


class TestFindIdentifierChild:
    def test_finds_identifier(self) -> None:
        ident = _make_node("identifier")
        other = _make_node("string")
        node = _make_node(children=(other, ident, other))
        assert _find_identifier_child(node) is ident

    def test_no_identifier(self) -> None:
        child = _make_node("string")
        node = _make_node(children=(child,))
        assert _find_identifier_child(node) is None

    def test_empty_children(self) -> None:
        node = _make_node(children=())
        assert _find_identifier_child(node) is None

    def test_first_identifier_wins(self) -> None:
        ident1 = _make_node("identifier")
        ident2 = _make_node("identifier")
        node = _make_node(children=(ident1, ident2))
        assert _find_identifier_child(node) is ident1

    def test_no_children_attr(self) -> None:
        node = MagicMock(spec=[])
        del node.children
        assert _find_identifier_child(node) is None


class TestFormatFallbackNodeName:
    def test_formats_correctly(self) -> None:
        node = _make_node(start_row=10, start_col=5)
        result = _format_fallback_node_name(node)
        assert result == "element_10_5"

    def test_zero_position(self) -> None:
        node = _make_node(start_row=0, start_col=0)
        result = _format_fallback_node_name(node)
        assert result == "element_0_0"


class TestExtractNodeText:
    def test_extracts_text(self) -> None:
        source = "def hello(): pass"
        node = _make_node(start_byte=4, end_byte=9)
        result = _extract_node_text(node, source)
        assert result == "hello"

    def test_empty_source(self) -> None:
        node = _make_node(start_byte=0, end_byte=0)
        result = _extract_node_text(node, "")
        assert result == ""

    def test_full_source(self) -> None:
        source = "hello"
        node = _make_node(start_byte=0, end_byte=5)
        result = _extract_node_text(node, source)
        assert result == "hello"

    def test_unicode_source(self) -> None:
        source = "x = '日本語'"
        encoded = source.encode("utf-8")
        target = "'日本語'".encode()
        start = encoded.index(target)
        node = _make_node(start_byte=start, end_byte=start + len(target))
        result = _extract_node_text(node, source)
        assert result == "'日本語'"

    def test_without_byte_attrs(self) -> None:
        node = MagicMock(spec=[])
        result = _extract_node_text(node, "hello")
        assert result == ""

    @patch("tree_sitter_analyzer.plugins._base_traverse_mixin.log_debug")
    def test_exception_returns_empty(self, mock_log: MagicMock) -> None:
        node = MagicMock()
        node.start_byte = property(lambda s: (_ for _ in ()).throw(ValueError("boom")))
        result = _extract_node_text(node, "hello")
        assert result == ""


class TestGetLanguageHint:
    def test_returns_unknown(self) -> None:
        assert _get_language_hint() == "unknown"


class TestDefaultNodeMixin:
    def test_is_instantiable(self) -> None:
        mixin = DefaultNodeMixin()
        assert isinstance(mixin, DefaultNodeMixin)

    def test_get_language_hint_returns_unknown(self) -> None:
        mixin = DefaultNodeMixin()
        assert mixin._get_language_hint() == "unknown"

    def test_extract_node_name_with_identifier(self) -> None:
        mixin = DefaultNodeMixin()
        ident = _make_node("identifier", start_byte=4, end_byte=7)
        node = _make_node("function_definition", children=(ident,))
        source = "def foo(): pass"
        result = mixin._extract_node_name(node, source)
        assert result == "foo"

    def test_extract_node_name_without_identifier(self) -> None:
        mixin = DefaultNodeMixin()
        node = _make_node("function_definition", start_row=3, start_col=0)
        result = mixin._extract_node_name(node, "source")
        assert result == "element_3_0"

    def test_extract_node_name_exception_returns_none(self) -> None:
        mixin = DefaultNodeMixin()
        node = MagicMock()
        node.children = property(lambda s: (_ for _ in ()).throw(RuntimeError("fail")))
        result = mixin._extract_node_name(node, "source")
        assert result is None

    def test_element_fields(self) -> None:
        mixin = DefaultNodeMixin()
        ident = _make_node("identifier", start_byte=4, end_byte=7)
        node = _make_node(
            "function_definition",
            start_row=2,
            end_row=4,
            start_col=0,
            end_col=10,
            children=(ident,),
        )
        source = "def bar(): pass"
        fields = mixin._element_fields(node, source)
        assert "name" in fields
        assert fields["start_line"] == 3
        assert fields["end_line"] == 5
        assert fields["language"] == "unknown"
        assert "raw_text" in fields

    def test_is_function_node_delegates(self) -> None:
        mixin = DefaultNodeMixin()
        assert mixin._is_function_node("function") is True
        assert mixin._is_function_node("class") is False

    def test_is_class_node_delegates(self) -> None:
        mixin = DefaultNodeMixin()
        assert mixin._is_class_node("class") is True
        assert mixin._is_class_node("function") is False

    def test_is_variable_node_delegates(self) -> None:
        mixin = DefaultNodeMixin()
        assert mixin._is_variable_node("variable") is True
        assert mixin._is_variable_node("class") is False

    def test_is_import_node_delegates(self) -> None:
        mixin = DefaultNodeMixin()
        assert mixin._is_import_node("import") is True
        assert mixin._is_import_node("class") is False

    def test_find_identifier_child_delegates(self) -> None:
        mixin = DefaultNodeMixin()
        ident = _make_node("identifier")
        node = _make_node(children=(ident,))
        assert mixin._find_identifier_child(node) is ident

    def test_format_fallback_node_name_delegates(self) -> None:
        mixin = DefaultNodeMixin()
        node = _make_node(start_row=1, start_col=2)
        assert mixin._format_fallback_node_name(node) == "element_1_2"

    def test_extract_node_text_delegates(self) -> None:
        mixin = DefaultNodeMixin()
        source = "hello"
        node = _make_node(start_byte=0, end_byte=5)
        assert mixin._extract_node_text(node, source) == "hello"

    def test_tree_root_node_delegates(self) -> None:
        mixin = DefaultNodeMixin()
        root = _make_node("root")
        tree = _make_tree(root)
        assert mixin._tree_root_node(tree) is root


class TestDefaultTraverseAppendMixin:
    def test_append_function(self) -> None:
        mixin = DefaultTraverseAppendMixin()
        functions: list[ModelFunction] = []
        ident = _make_node("identifier", start_byte=0, end_byte=3)
        node = _make_node(
            "function_definition", start_row=0, end_row=2, children=(ident,)
        )
        mixin._append_function(node, functions, "foo")
        assert len(functions) == 1
        assert isinstance(functions[0], ModelFunction)

    def test_append_function_exception_skips(self) -> None:
        mixin = DefaultTraverseAppendMixin()
        functions: list[ModelFunction] = []
        node = _make_node("function_definition")
        with patch.object(mixin, "_element_fields", side_effect=RuntimeError("fail")):
            mixin._append_function(node, functions, "source")
        assert len(functions) == 0

    def test_append_class_exception_skips(self) -> None:
        mixin = DefaultTraverseAppendMixin()
        classes: list[ModelClass] = []
        node = _make_node("class_definition")
        with patch.object(mixin, "_element_fields", side_effect=RuntimeError("fail")):
            mixin._append_class(node, classes, "source")
        assert len(classes) == 0

    def test_append_variable_exception_skips(self) -> None:
        mixin = DefaultTraverseAppendMixin()
        variables: list[ModelVariable] = []
        node = _make_node("variable_declaration")
        with patch.object(mixin, "_element_fields", side_effect=RuntimeError("fail")):
            mixin._append_variable(node, variables, "source")
        assert len(variables) == 0

    def test_append_import_exception_skips(self) -> None:
        mixin = DefaultTraverseAppendMixin()
        imports: list[ModelImport] = []
        node = _make_node("import_statement")
        with patch.object(mixin, "_element_fields", side_effect=RuntimeError("fail")):
            mixin._append_import(node, imports, "source")
        assert len(imports) == 0


class TestDefaultTraverseMixin:
    def test_traverse_for_functions_finds_matching_nodes(self) -> None:
        mixin = DefaultTraverseMixin()
        func_node = _make_node(
            "function_definition", start_row=0, end_row=3, start_byte=0, end_byte=20
        )
        ident = _make_node("identifier", start_byte=4, end_byte=7)
        func_node.children = (ident,)
        root = _make_node("module", children=(func_node,))
        functions: list[ModelFunction] = []
        mixin._traverse_for_functions(root, functions, [], "def foo(): pass")
        assert len(functions) == 1

    def test_traverse_for_functions_skips_non_matching(self) -> None:
        mixin = DefaultTraverseMixin()
        var_node = _make_node("variable_declaration")
        root = _make_node("module", children=(var_node,))
        functions: list[ModelFunction] = []
        mixin._traverse_for_functions(root, functions, [], "x = 1")
        assert len(functions) == 0

    def test_traverse_for_functions_recursive(self) -> None:
        mixin = DefaultTraverseMixin()
        func1 = _make_node(
            "function_definition", start_row=0, end_row=2, start_byte=0, end_byte=10
        )
        func2 = _make_node(
            "function", start_row=3, end_row=5, start_byte=11, end_byte=21
        )
        ident1 = _make_node("identifier", start_byte=4, end_byte=7)
        ident2 = _make_node("identifier", start_byte=15, end_byte=18)
        func1.children = (ident1,)
        func2.children = (ident2,)
        root = _make_node("module", children=(func1, func2))
        functions: list[ModelFunction] = []
        mixin._traverse_for_functions(
            root, functions, [], "def a(): pass\ndef b(): pass"
        )
        assert len(functions) == 2

    def test_traverse_for_classes_finds_matching_nodes(self) -> None:
        mixin = DefaultTraverseMixin()
        class_node = _make_node(
            "class_definition", start_row=0, end_row=5, start_byte=0, end_byte=30
        )
        ident = _make_node("identifier", start_byte=6, end_byte=9)
        class_node.children = (ident,)
        root = _make_node("module", children=(class_node,))
        classes: list[ModelClass] = []
        mixin._traverse_for_classes(root, classes, [], "class Foo: pass")
        assert len(classes) == 1

    def test_traverse_for_classes_recursive(self) -> None:
        mixin = DefaultTraverseMixin()
        cls1 = _make_node(
            "class_definition", start_row=0, end_row=3, start_byte=0, end_byte=15
        )
        cls2 = _make_node("class", start_row=4, end_row=7, start_byte=16, end_byte=31)
        ident1 = _make_node("identifier", start_byte=6, end_byte=9)
        ident2 = _make_node("identifier", start_byte=22, end_byte=25)
        cls1.children = (ident1,)
        cls2.children = (ident2,)
        root = _make_node("module", children=(cls1, cls2))
        classes: list[ModelClass] = []
        mixin._traverse_for_classes(root, classes, [], "class A: pass\nclass B: pass")
        assert len(classes) == 2

    def test_traverse_for_variables_finds_matching_nodes(self) -> None:
        mixin = DefaultTraverseMixin()
        var_node = _make_node(
            "variable_declaration", start_row=0, end_row=0, start_byte=0, end_byte=5
        )
        ident = _make_node("identifier", start_byte=0, end_byte=1)
        var_node.children = (ident,)
        root = _make_node("module", children=(var_node,))
        variables: list[ModelVariable] = []
        mixin._traverse_for_variables(root, variables, [], "x = 1")
        assert len(variables) == 1

    def test_traverse_for_imports_finds_matching_nodes(self) -> None:
        mixin = DefaultTraverseMixin()
        imp_node = _make_node(
            "import_statement", start_row=0, end_row=0, start_byte=0, end_byte=10
        )
        ident = _make_node("identifier", start_byte=7, end_byte=9)
        imp_node.children = (ident,)
        root = _make_node("module", children=(imp_node,))
        imports: list[ModelImport] = []
        mixin._traverse_for_imports(root, imports, [], "import os")
        assert len(imports) == 1

    def test_traverse_for_imports_recursive(self) -> None:
        mixin = DefaultTraverseMixin()
        imp1 = _make_node(
            "import_statement", start_row=0, end_row=0, start_byte=0, end_byte=10
        )
        imp2 = _make_node("include", start_row=1, end_row=1, start_byte=11, end_byte=22)
        ident1 = _make_node("identifier", start_byte=7, end_byte=9)
        ident2 = _make_node("identifier", start_byte=18, end_byte=21)
        imp1.children = (ident1,)
        imp2.children = (ident2,)
        root = _make_node("module", children=(imp1, imp2))
        imports: list[ModelImport] = []
        mixin._traverse_for_imports(root, imports, [], "import os\ninclude stdio")
        assert len(imports) == 2

    def test_traverse_empty_tree(self) -> None:
        mixin = DefaultTraverseMixin()
        root = _make_node("module", children=())
        functions: list[ModelFunction] = []
        mixin._traverse_for_functions(root, functions, [], "")
        assert len(functions) == 0

    def test_traverse_deeply_nested(self) -> None:
        mixin = DefaultTraverseMixin()
        inner_func = _make_node(
            "function_definition", start_row=2, end_row=4, start_byte=10, end_byte=25
        )
        ident = _make_node("identifier", start_byte=14, end_byte=17)
        inner_func.children = (ident,)
        middle = _make_node("block", children=(inner_func,))
        outer = _make_node("block", children=(middle,))
        root = _make_node("module", children=(outer,))
        functions: list[ModelFunction] = []
        mixin._traverse_for_functions(
            root, functions, [], "def outer():\n  def inner(): pass"
        )
        assert len(functions) == 1

    def test_traverse_mixed_node_types(self) -> None:
        mixin = DefaultTraverseMixin()
        func_node = _make_node(
            "function_definition", start_row=0, end_row=2, start_byte=0, end_byte=15
        )
        class_node = _make_node(
            "class_definition", start_row=3, end_row=8, start_byte=16, end_byte=40
        )
        var_node = _make_node(
            "variable_declaration", start_row=9, end_row=9, start_byte=41, end_byte=46
        )
        imp_node = _make_node(
            "import_statement", start_row=10, end_row=10, start_byte=47, end_byte=57
        )
        for n in [func_node, class_node, var_node, imp_node]:
            ident = _make_node(
                "identifier", start_byte=n.start_byte, end_byte=n.start_byte + 3
            )
            n.children = (ident,)
        root = _make_node(
            "module", children=(func_node, class_node, var_node, imp_node)
        )

        functions: list[ModelFunction] = []
        classes: list[ModelClass] = []
        variables: list[ModelVariable] = []
        imports: list[ModelImport] = []
        mixin._traverse_for_functions(root, functions, [], "source")
        mixin._traverse_for_classes(root, classes, [], "source")
        mixin._traverse_for_variables(root, variables, [], "source")
        mixin._traverse_for_imports(root, imports, [], "source")
        assert len(functions) == 1
        assert len(classes) == 1
        assert len(variables) == 1
        assert len(imports) == 1
