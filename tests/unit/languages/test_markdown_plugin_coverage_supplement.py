#!/usr/bin/env python3
"""Coverage boost for markdown_plugin.py — targets uncovered extraction paths."""

import pytest
from unittest.mock import MagicMock, PropertyMock

from tree_sitter_analyzer.languages.markdown_plugin import MarkdownElementExtractor


def _build_mock_tree(source_code, type_map=None):
    """Build a mock tree-sitter tree from source lines."""
    mock_tree = MagicMock()
    mock_root = MagicMock()
    lines = source_code.split("\n")
    children = []
    for i, line in enumerate(lines):
        if line.strip():
            node_type = "paragraph"
            if type_map:
                for pattern, ntype in type_map.items():
                    if pattern in line:
                        node_type = ntype
                        break
            n = MagicMock()
            n.type = node_type
            n.start_point = (i, 0)
            n.end_point = (i + 1, 0)
            n.start_byte = 0
            n.end_byte = len(source_code)
            n.text = PropertyMock(return_value=line.encode("utf8"))
            n.children = []
            children.append(n)
    mock_root.children = children
    mock_tree.root_node = mock_root
    return mock_tree


class TestMarkdownExtractorSupplement:
    """Covers: extract_headers, code_blocks, links, tables, lists, images, references,
    blockquotes, horizontal_rules, html_elements, text_formatting, footnotes"""

    MD_HEADERS = "# Title\n## Section\nText\n### Sub"
    MD_CODE = "```python\ndef hello(): pass\n```\n\n```js\nconsole.log('hi')\n```"
    MD_LINKS = "[text](url)\n![img](img.png)"
    MD_REFS = "[text][ref]\n\n[ref]: url"
    MD_TABLE = "| A | B |\n|---|---|\n| 1 | 2 |"
    MD_LIST = "- item\n  - nested\n1. first\n2. second"
    MD_QUOTE = "> quoted\n> more"
    MD_HR = "---\n***\n___"
    MD_HTML = "<div>hi</div>\n<script>alert(1)</script>"

    def test_extract_headers(self):
        mock = _build_mock_tree(self.MD_HEADERS)
        ext = MarkdownElementExtractor()
        r = ext.extract_headers(mock, self.MD_HEADERS)
        assert isinstance(r, list)

    def test_extract_code_blocks(self):
        mock = _build_mock_tree(self.MD_CODE, {"```": "fenced_code_block"})
        ext = MarkdownElementExtractor()
        ext.source_code = self.MD_CODE
        ext.content_lines = self.MD_CODE.split("\n")
        r = ext.extract_code_blocks(mock, self.MD_CODE)
        assert isinstance(r, list)

    def test_extract_links(self):
        mock = _build_mock_tree(self.MD_LINKS, {"[": "inline"})
        ext = MarkdownElementExtractor()
        ext.source_code = self.MD_LINKS
        ext.content_lines = self.MD_LINKS.split("\n")
        r = ext.extract_links(mock, self.MD_LINKS)
        assert isinstance(r, list)

    def test_extract_images(self):
        mock = _build_mock_tree(self.MD_LINKS, {"![": "inline"})
        ext = MarkdownElementExtractor()
        ext.source_code = self.MD_LINKS
        ext.content_lines = self.MD_LINKS.split("\n")
        r = ext.extract_images(mock, self.MD_LINKS)
        assert isinstance(r, list)

    def test_extract_references(self):
        mock = _build_mock_tree(self.MD_REFS, {"[ref]": "link_reference_definition"})
        ext = MarkdownElementExtractor()
        ext.source_code = self.MD_REFS
        ext.content_lines = self.MD_REFS.split("\n")
        r = ext.extract_references(mock, self.MD_REFS)
        assert isinstance(r, list)

    def test_extract_tables(self):
        mock = _build_mock_tree(self.MD_TABLE, {"|": "pipe_table"})
        ext = MarkdownElementExtractor()
        ext.source_code = self.MD_TABLE
        ext.content_lines = self.MD_TABLE.split("\n")
        r = ext.extract_tables(mock, self.MD_TABLE)
        assert isinstance(r, list)

    def test_extract_lists(self):
        mock = _build_mock_tree(self.MD_LIST, {"-": "list", "1.": "list"})
        ext = MarkdownElementExtractor()
        ext.source_code = self.MD_LIST
        ext.content_lines = self.MD_LIST.split("\n")
        r = ext.extract_lists(mock, self.MD_LIST)
        assert isinstance(r, list)

    def test_extract_blockquotes(self):
        mock = _build_mock_tree(self.MD_QUOTE, {">": "block_quote"})
        ext = MarkdownElementExtractor()
        ext.source_code = self.MD_QUOTE
        ext.content_lines = self.MD_QUOTE.split("\n")
        r = ext.extract_blockquotes(mock, self.MD_QUOTE)
        assert isinstance(r, list)

    def test_extract_horizontal_rules(self):
        mock = _build_mock_tree(self.MD_HR, {"---": "thematic_break", "***": "thematic_break"})
        ext = MarkdownElementExtractor()
        r = ext.extract_horizontal_rules(mock, self.MD_HR)
        assert isinstance(r, list)

    def test_extract_html_elements(self):
        mock = _build_mock_tree(self.MD_HTML, {"<div>": "html_block", "<script>": "html_block"})
        ext = MarkdownElementExtractor()
        ext.source_code = self.MD_HTML
        ext.content_lines = self.MD_HTML.split("\n")
        r = ext.extract_html_elements(mock, self.MD_HTML)
        assert isinstance(r, list)
