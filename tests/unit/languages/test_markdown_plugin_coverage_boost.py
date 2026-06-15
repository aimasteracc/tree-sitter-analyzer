from unittest.mock import patch

import pytest

from tree_sitter_analyzer.languages.markdown_plugin import (
    MarkdownElementExtractor,
    MarkdownPlugin,
)


class _Node:
    def __init__(
        self,
        node_type,
        *,
        raw_text="",
        children=None,
        start_point=(0, 0),
        end_point=(0, 1),
    ):
        self.type = node_type
        self.raw_text = raw_text
        self.children = children or []
        self.start_point = start_point
        self.end_point = end_point


@pytest.fixture
def plugin():
    return MarkdownPlugin()


def test_markdown_plugin_basic(plugin):
    code = """
    # Header 1
    ## Header 2
    [link](http://example.com)
    ![image](img.png)
    * list item
    1. numbered item
    ```python
    print("hello")
    ```
    | col1 | col2 |
    |------|------|
    | val1 | val2 |
    """
    extractor = plugin.create_extractor()
    # Test specific extraction methods to avoid high-level issues
    # Passing None as tree because extract_headers checks if tree is None
    headers = extractor.extract_headers(None, code)
    assert headers == []

    links = extractor.extract_links(None, code)
    assert links == []

    # Add more tests to cover all methods
    plugin.get_language_name()
    plugin.get_file_extensions()
    plugin.get_element_categories()


def test_fenced_code_block_extracts_language_and_line_count():
    extractor = MarkdownElementExtractor()
    raw_text = "```python\nprint('hello')\nprint('bye')\n```"
    code_node = _Node(
        "fenced_code_block",
        raw_text=raw_text,
        start_point=(0, 0),
        end_point=(3, 3),
    )
    root = _Node("document", children=[code_node])

    code_blocks = []
    with patch.object(
        extractor,
        "_get_node_text_optimized",
        side_effect=lambda node: node.raw_text,
    ):
        extractor._extract_fenced_code_blocks(root, code_blocks)

    assert len(code_blocks) == 1
    block = code_blocks[0]
    assert block.name == "Code Block (python)"
    assert block.element_type == "code_block"
    assert block.language_info == "python"
    assert block.language == "python"
    assert (
        block.line_count == 4
    )  # end_point row 3 → end_line 4, start_point row 0 → start_line 1; 4-1+1=4
    assert block.type == "code_block"


def test_atx_header_extracts_level_and_text():
    extractor = MarkdownElementExtractor()
    header_node = _Node(
        "atx_heading",
        raw_text="### Release Notes",
        start_point=(4, 0),
        end_point=(4, 17),
    )
    root = _Node("document", children=[header_node])

    headers = []
    with patch.object(
        extractor,
        "_get_node_text_optimized",
        side_effect=lambda node: node.raw_text,
    ):
        extractor._extract_atx_headers(root, headers)

    assert len(headers) == 1
    header = headers[0]
    assert header.name == "Release Notes"
    assert header.level == 3
    assert header.text == "Release Notes"
    assert header.type == "heading"


def test_fenced_code_block_without_language_uses_unknown_name_and_text_language():
    extractor = MarkdownElementExtractor()
    raw_text = "```\nplain text\n```"
    code_node = _Node(
        "fenced_code_block",
        raw_text=raw_text,
        start_point=(0, 0),
        end_point=(2, 3),
    )
    root = _Node("document", children=[code_node])

    code_blocks = []
    with patch.object(
        extractor,
        "_get_node_text_optimized",
        side_effect=lambda node: node.raw_text,
    ):
        extractor._extract_fenced_code_blocks(root, code_blocks)

    assert len(code_blocks) == 1
    block = code_blocks[0]
    assert block.name == "Code Block (unknown)"
    assert block.language_info == ""
    assert block.language == "text"
    assert (
        block.line_count == 3
    )  # end_point row 2 → end_line 3, start_point row 0 → start_line 1; 3-1+1=3


def test_fenced_code_block_extraction_swallows_single_node_failure():
    extractor = MarkdownElementExtractor()
    code_node = _Node("fenced_code_block", raw_text="```python\nx\n```")
    root = _Node("document", children=[code_node])

    code_blocks = []
    with patch.object(
        extractor,
        "_get_node_text_optimized",
        side_effect=RuntimeError("node text failed"),
    ):
        extractor._extract_fenced_code_blocks(root, code_blocks)

    assert code_blocks == []


def test_list_items_classify_task_ordered_and_unordered_lists():
    extractor = MarkdownElementExtractor()
    task_list = _Node(
        "list",
        raw_text="- [x] done",
        children=[_Node("list_item", raw_text="- [x] done")],
    )
    ordered_list = _Node(
        "list",
        raw_text="1. first",
        children=[_Node("list_item", raw_text="1. first")],
    )
    unordered_list = _Node(
        "list",
        raw_text="- first",
        children=[_Node("list_item", raw_text="- first")],
    )
    root = _Node("document", children=[task_list, ordered_list, unordered_list])

    lists = []
    with patch.object(
        extractor,
        "_get_node_text_optimized",
        side_effect=lambda node: node.raw_text,
    ):
        extractor._extract_list_items(root, lists)

    assert [item.list_type for item in lists] == ["task", "ordered", "unordered"]
    assert [item.element_type for item in lists] == ["task_list", "list", "list"]
    assert [item.item_count for item in lists] == [1, 1, 1]
    assert [item.type for item in lists] == ["task", "ordered", "unordered"]


def test_list_item_extraction_swallows_single_node_failure():
    extractor = MarkdownElementExtractor()
    list_node = _Node(
        "list",
        raw_text="- broken",
        children=[_Node("list_item", raw_text="- broken")],
    )
    root = _Node("document", children=[list_node])

    lists = []
    with patch.object(
        extractor,
        "_get_node_text_optimized",
        side_effect=RuntimeError("node text failed"),
    ):
        extractor._extract_list_items(root, lists)

    assert lists == []


def test_pipe_table_extracts_row_and_column_counts():
    extractor = MarkdownElementExtractor()
    table_node = _Node(
        "pipe_table",
        raw_text="| Name | Value |\n| --- | --- |\n| A | 1 |",
        start_point=(0, 0),
        end_point=(2, 9),
    )
    root = _Node("document", children=[table_node])

    tables = []
    with patch.object(
        extractor,
        "_get_node_text_optimized",
        side_effect=lambda node: node.raw_text,
    ):
        extractor._extract_pipe_tables(root, tables)

    assert len(tables) == 1
    table = tables[0]
    assert table.name == "Table (2 rows, 2 columns)"
    assert table.row_count == 2
    assert table.column_count == 2
    assert table.type == "table"
