#!/usr/bin/env python3
"""
Unit tests for plugins/__init__.py

Covers: ElementExtractor ABC, LanguagePlugin ABC + is_applicable,
DefaultExtractor (all 4 extract + 4 traverse + _extract_node_name),
DefaultLanguagePlugin.
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.plugins import (
    DefaultExtractor,
    DefaultLanguagePlugin,
    ElementExtractor,
    LanguagePlugin,
)


# ---------------------------------------------------------------------------
# Helper: minimal concrete subclass of ElementExtractor (for ABC tests)
# ---------------------------------------------------------------------------


class _ConcreteExtractor(ElementExtractor):
    def extract_functions(self, tree, source_code):
        return []

    def extract_classes(self, tree, source_code):
        return []

    def extract_variables(self, tree, source_code):
        return []

    def extract_imports(self, tree, source_code):
        return []


class _ConcretePlugin(LanguagePlugin):
    def get_language_name(self):
        return "testlang"

    def get_file_extensions(self):
        return [".tl", ".testlang"]

    def create_extractor(self):
        return _ConcreteExtractor()


# ---------------------------------------------------------------------------
# LanguagePlugin.is_applicable
# ---------------------------------------------------------------------------


class TestLanguagePluginIsApplicable:
    def setup_method(self):
        self.plugin = _ConcretePlugin()

    def test_applicable_for_matching_extension(self):
        assert self.plugin.is_applicable("main.tl") is True

    def test_applicable_case_insensitive(self):
        assert self.plugin.is_applicable("Main.TL") is True

    def test_not_applicable_for_unknown_extension(self):
        assert self.plugin.is_applicable("main.py") is False

    def test_not_applicable_for_no_extension(self):
        assert self.plugin.is_applicable("Makefile") is False

    def test_applicable_for_second_extension(self):
        assert self.plugin.is_applicable("src/foo.testlang") is True


# ---------------------------------------------------------------------------
# DefaultExtractor — basic extraction (no real tree; uses mock)
# ---------------------------------------------------------------------------


def _make_leaf(node_type: str, start_line: int = 0, col: int = 0, identifier_child=None):
    """Build a minimal mock tree-sitter node."""
    node = MagicMock()
    node.type = node_type
    node.start_point = (start_line, col)
    node.end_point = (start_line + 1, 0)
    # Children: optionally include an identifier child
    if identifier_child:
        child = MagicMock()
        child.type = "identifier"
        child.start_point = (start_line, col)
        node.children = [child]
    else:
        node.children = []
    return node


def _make_tree(root_node):
    tree = MagicMock()
    tree.root_node = root_node
    return tree


class TestDefaultExtractorExtractFunctions:
    def setup_method(self):
        self.extractor = DefaultExtractor()

    def test_returns_list(self):
        root = _make_leaf("module")
        result = self.extractor.extract_functions(_make_tree(root), "")
        assert isinstance(result, list)

    def test_finds_function_node(self):
        func_node = _make_leaf("function_definition", start_line=2, identifier_child=True)
        root = MagicMock()
        root.type = "module"
        root.start_point = (0, 0)
        root.end_point = (10, 0)
        root.children = [func_node]
        result = self.extractor.extract_functions(_make_tree(root), "def foo(): pass")
        assert len(result) >= 1

    def test_no_root_node_attribute_returns_empty(self):
        tree_without_root = MagicMock(spec=[])  # no root_node attribute
        result = self.extractor.extract_functions(tree_without_root, "")
        assert result == []

    def test_exception_in_tree_returns_empty(self):
        bad_tree = MagicMock()
        bad_tree.root_node.side_effect = RuntimeError("boom")
        result = self.extractor.extract_functions(bad_tree, "")
        assert isinstance(result, list)


class TestDefaultExtractorExtractClasses:
    def setup_method(self):
        self.extractor = DefaultExtractor()

    def test_returns_list(self):
        root = _make_leaf("module")
        result = self.extractor.extract_classes(_make_tree(root), "")
        assert isinstance(result, list)

    def test_finds_class_node(self):
        cls_node = _make_leaf("class_definition", start_line=1, identifier_child=True)
        root = MagicMock()
        root.type = "module"
        root.start_point = (0, 0)
        root.end_point = (20, 0)
        root.children = [cls_node]
        result = self.extractor.extract_classes(_make_tree(root), "class Foo: pass")
        assert len(result) >= 1

    def test_no_root_node_returns_empty(self):
        result = self.extractor.extract_classes(MagicMock(spec=[]), "")
        assert result == []


class TestDefaultExtractorExtractVariables:
    def setup_method(self):
        self.extractor = DefaultExtractor()

    def test_returns_list(self):
        root = _make_leaf("module")
        result = self.extractor.extract_variables(_make_tree(root), "")
        assert isinstance(result, list)

    def test_finds_variable_declaration_node(self):
        var_node = _make_leaf("variable_declaration", start_line=0, identifier_child=True)
        root = MagicMock()
        root.type = "module"
        root.start_point = (0, 0)
        root.end_point = (5, 0)
        root.children = [var_node]
        result = self.extractor.extract_variables(_make_tree(root), "var x = 1")
        assert len(result) >= 1

    def test_no_root_node_returns_empty(self):
        result = self.extractor.extract_variables(MagicMock(spec=[]), "")
        assert result == []


class TestDefaultExtractorExtractImports:
    def setup_method(self):
        self.extractor = DefaultExtractor()

    def test_returns_list(self):
        root = _make_leaf("module")
        result = self.extractor.extract_imports(_make_tree(root), "")
        assert isinstance(result, list)

    def test_finds_import_node(self):
        imp_node = _make_leaf("import_statement", start_line=0, identifier_child=True)
        root = MagicMock()
        root.type = "module"
        root.start_point = (0, 0)
        root.end_point = (5, 0)
        root.children = [imp_node]
        result = self.extractor.extract_imports(_make_tree(root), "import os")
        assert len(result) >= 1

    def test_no_root_node_returns_empty(self):
        result = self.extractor.extract_imports(MagicMock(spec=[]), "")
        assert result == []


# ---------------------------------------------------------------------------
# DefaultExtractor._extract_node_name
# ---------------------------------------------------------------------------


class TestDefaultExtractorExtractNodeName:
    def setup_method(self):
        self.extractor = DefaultExtractor()

    def test_returns_none_when_no_identifier_child(self):
        node = MagicMock()
        node.children = []
        result = self.extractor._extract_node_name(node)
        assert result is None

    def test_returns_string_when_identifier_child_exists(self):
        child = MagicMock()
        child.type = "identifier"
        child.start_point = (3, 4)

        node = MagicMock()
        node.children = [child]
        result = self.extractor._extract_node_name(node)
        assert isinstance(result, str)
        assert "3" in result  # includes line number

    def test_returns_none_when_no_children_attribute(self):
        node = MagicMock(spec=[])  # no .children
        result = self.extractor._extract_node_name(node)
        assert result is None

    def test_skips_non_identifier_children(self):
        child = MagicMock()
        child.type = "keyword"
        child.start_point = (0, 0)

        node = MagicMock()
        node.children = [child]
        result = self.extractor._extract_node_name(node)
        assert result is None


# ---------------------------------------------------------------------------
# DefaultExtractor — recursive traversal (nested children)
# ---------------------------------------------------------------------------


class TestDefaultExtractorTraversal:
    def setup_method(self):
        self.extractor = DefaultExtractor()

    def test_traverse_nested_function_node(self):
        """_traverse_for_functions handles nested children recursively."""
        inner_func = _make_leaf("function_declaration", start_line=5, identifier_child=True)
        outer = MagicMock()
        outer.type = "block"
        outer.start_point = (0, 0)
        outer.end_point = (10, 0)
        outer.children = [inner_func]

        root = MagicMock()
        root.type = "module"
        root.start_point = (0, 0)
        root.end_point = (20, 0)
        root.children = [outer]

        result = self.extractor.extract_functions(_make_tree(root), "")
        assert len(result) >= 1

    def test_traverse_nested_class_node(self):
        inner_cls = _make_leaf("class_declaration", start_line=2, identifier_child=True)
        outer = MagicMock()
        outer.type = "namespace"
        outer.start_point = (0, 0)
        outer.end_point = (10, 0)
        outer.children = [inner_cls]

        root = MagicMock()
        root.type = "module"
        root.start_point = (0, 0)
        root.end_point = (20, 0)
        root.children = [outer]

        result = self.extractor.extract_classes(_make_tree(root), "")
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# DefaultLanguagePlugin
# ---------------------------------------------------------------------------


class TestDefaultLanguagePlugin:
    def setup_method(self):
        self.plugin = DefaultLanguagePlugin()

    def test_get_language_name_returns_generic(self):
        assert self.plugin.get_language_name() == "generic"

    def test_get_file_extensions_returns_list(self):
        exts = self.plugin.get_file_extensions()
        assert isinstance(exts, list)
        assert len(exts) > 0

    def test_create_extractor_returns_default_extractor(self):
        extractor = self.plugin.create_extractor()
        assert isinstance(extractor, DefaultExtractor)

    def test_is_applicable_for_txt(self):
        assert self.plugin.is_applicable("notes.txt") is True

    def test_is_applicable_for_md(self):
        assert self.plugin.is_applicable("README.md") is True

    def test_is_not_applicable_for_py(self):
        assert self.plugin.is_applicable("script.py") is False
