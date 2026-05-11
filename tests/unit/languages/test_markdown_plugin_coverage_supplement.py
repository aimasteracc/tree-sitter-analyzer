#!/usr/bin/env python3
"""Supplement markdown plugin tests — targets bare-minimum extractor paths."""

from unittest.mock import MagicMock

from tree_sitter_analyzer.languages.markdown_plugin import (
    MarkdownElementExtractor,
    MarkdownPlugin,
)


class MockNode:
    def __init__(
        self,
        node_type,
        start_point=(0, 0),
        end_point=(0, 1),
        children=None,
        text="",
        start_byte=0,
        end_byte=1,
    ):
        self.type = node_type
        self.start_point = start_point
        self.end_point = end_point
        self.start_byte = start_byte
        self.end_byte = end_byte
        self._children = children or []
        self._text = text

    @property
    def children(self):
        return self._children

    @property
    def text(self):
        return self._text.encode() if isinstance(self._text, str) else self._text


class TestMarkdownSupplement:
    """Target extractors that require minimal mocking."""

    def _mk_tree(self, root_children, source=""):
        tree = MagicMock()
        root = MockNode("document", children=root_children)
        tree.root_node = root
        return tree

    def test_extract_headers_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        headers = ext.extract_headers(tree, "some markdown")
        assert isinstance(headers, list)

    def test_extract_links_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        links = ext.extract_links(tree, "text")
        assert isinstance(links, list)

    def test_extract_images_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        imgs = ext.extract_images(tree, "text")
        assert isinstance(imgs, list)

    def test_extract_blockquotes_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        bqs = ext.extract_blockquotes(tree, "text")
        assert isinstance(bqs, list)

    def test_extract_code_blocks_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        cbs = ext.extract_code_blocks(tree, "text")
        assert isinstance(cbs, list)

    def test_extract_references_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        refs = ext.extract_references(tree, "text")
        assert isinstance(refs, list)

    def test_plugin_get_queries(self):
        plugin = MarkdownPlugin()
        queries = plugin.get_queries()
        assert isinstance(queries, dict)

    def test_extract_functions_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        funcs = ext.extract_functions(tree, "text")
        assert isinstance(funcs, list)

    def test_extract_classes_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        classes = ext.extract_classes(tree, "text")
        assert isinstance(classes, list)

    def test_extract_variables_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        vars_ = ext.extract_variables(tree, "text")
        assert isinstance(vars_, list)

    def test_extract_imports_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        imports = ext.extract_imports(tree, "text")
        assert isinstance(imports, list)
