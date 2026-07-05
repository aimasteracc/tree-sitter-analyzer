#!/usr/bin/env python3
"""Targeted tests for 0%-coverage and critically-low-coverage methods in markdown_plugin.py.

Covers: _extract_autolinks (0%), _extract_reference_images (0%),
_extract_inline_html (0%), execute_query_strategy (0%),
_extract_pipe_tables (10.5%), _extract_emphasis_elements (41.4%),
_extract_strikethrough_elements (42.9%).
"""

from unittest.mock import Mock

from tree_sitter_analyzer.languages.markdown_plugin import (
    MarkdownElementExtractor,
    MarkdownPlugin,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_node(
    node_type,
    start_point=(0, 0),
    end_point=None,
    children=None,
    text="",
    start_byte=0,
    end_byte=None,
):
    encoded = text.encode() if isinstance(text, str) else text
    n = Mock()
    n.type = node_type
    n.start_point = start_point
    if end_point is not None:
        n.end_point = end_point
    else:
        n.end_point = (0, len(text) if text else 0)
    n.start_byte = start_byte
    n.end_byte = end_byte if end_byte is not None else len(encoded)
    n.children = children or []
    n.text = encoded
    return n


def _setup_extractor(source_code, content_lines=None):
    ext = MarkdownElementExtractor()
    ext.source_code = source_code
    ext.content_lines = content_lines or source_code.split("\n")
    ext._node_text_cache = {}
    ext._processed_nodes = set()
    ext._element_cache = {}
    ext._extracted_links = set()
    ext._extracted_images = set()
    return ext


# ---------------------------------------------------------------------------
# _extract_autolinks  (0%)
# ---------------------------------------------------------------------------


class TestExtractAutolinks:
    def test_autolink_url(self):
        ext = _setup_extractor("<https://example.com>")
        root = _make_node(
            "document",
            start_point=(0, 0),
            end_point=(0, 20),
            children=[
                _make_node(
                    "inline",
                    start_point=(0, 0),
                    end_point=(0, 20),
                    text="<https://example.com>",
                )
            ],
        )
        links = []
        ext._extract_autolinks(root, links)
        assert len(links) == 1
        assert links[0].element_type == "autolink"
        assert links[0].url == "https://example.com"

    def test_autolink_mailto(self):
        ext = _setup_extractor("<mailto:user@example.com>")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="<mailto:user@example.com>",
                    start_point=(0, 0),
                    end_point=(0, 25),
                )
            ],
        )
        links = []
        ext._extract_autolinks(root, links)
        assert len(links) == 1
        assert links[0].url == "mailto:user@example.com"

    def test_autolink_email(self):
        ext = _setup_extractor("<user@example.com>")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="<user@example.com>",
                    start_point=(0, 0),
                    end_point=(0, 20),
                )
            ],
        )
        links = []
        ext._extract_autolinks(root, links)
        assert len(links) == 1
        assert links[0].url == "user@example.com"

    def test_autolink_duplicate_skip(self):
        ext = _setup_extractor("<https://example.com>")
        ext._extracted_links.add("autolink|https://example.com")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="<https://example.com>",
                    start_point=(0, 0),
                    end_point=(0, 20),
                )
            ],
        )
        links = []
        ext._extract_autolinks(root, links)
        assert len(links) == 0

    def test_autolink_no_inline_node(self):
        ext = _setup_extractor("plain text")
        root = _make_node(
            "document", children=[_make_node("paragraph", text="plain text")]
        )
        links = []
        ext._extract_autolinks(root, links)
        assert len(links) == 0

    def test_autolink_empty_text(self):
        ext = _setup_extractor("")
        root = _make_node(
            "document",
            children=[
                _make_node("inline", text="", start_point=(0, 0), end_point=(0, 0))
            ],
        )
        links = []
        ext._extract_autolinks(root, links)
        assert len(links) == 0


# ---------------------------------------------------------------------------
# _extract_reference_images  (0%)
# ---------------------------------------------------------------------------


class TestExtractReferenceImages:
    def test_reference_image_basic(self):
        ext = _setup_extractor("![alt][ref]")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline", text="![alt][ref]", start_point=(0, 0), end_point=(0, 11)
                )
            ],
        )
        images = []
        ext._extract_reference_images(root, images)
        assert len(images) == 1
        assert images[0].element_type == "reference_image"
        assert images[0].name == "alt"

    def test_reference_image_empty_alt(self):
        ext = _setup_extractor("![][ref]")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline", text="![][ref]", start_point=(0, 0), end_point=(0, 8)
                )
            ],
        )
        images = []
        ext._extract_reference_images(root, images)
        assert len(images) == 1
        assert images[0].name == "Reference Image"

    def test_reference_image_no_inline(self):
        ext = _setup_extractor("plain")
        root = _make_node("document", children=[_make_node("paragraph", text="plain")])
        images = []
        ext._extract_reference_images(root, images)
        assert len(images) == 0


# ---------------------------------------------------------------------------
# _extract_inline_html  (0%)
# ---------------------------------------------------------------------------


class TestExtractInlineHTML:
    def test_inline_html_tag(self):
        ext = _setup_extractor("<span>text</span>")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="<span>text</span>",
                    start_point=(0, 0),
                    end_point=(0, 16),
                )
            ],
        )
        elems = []
        ext._extract_inline_html(root, elems)
        # <span> and </span> each produce one html_inline element
        assert len(elems) == 2
        assert all(e.element_type == "html_inline" for e in elems)

    def test_inline_html_br_tag(self):
        ext = _setup_extractor("text<br>more")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline", text="text<br>more", start_point=(0, 0), end_point=(0, 12)
                )
            ],
        )
        elems = []
        ext._extract_inline_html(root, elems)
        assert any(e.element_type == "html_inline" for e in elems)

    def test_inline_html_not_autolink(self):
        ext = _setup_extractor("<https://example.com>")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="<https://example.com>",
                    start_point=(0, 0),
                    end_point=(0, 20),
                )
            ],
        )
        elems = []
        ext._extract_inline_html(root, elems)
        assert len(elems) == 0

    def test_inline_html_no_inline(self):
        ext = _setup_extractor("plain")
        root = _make_node("document", children=[_make_node("paragraph", text="plain")])
        elems = []
        ext._extract_inline_html(root, elems)
        assert len(elems) == 0


# ---------------------------------------------------------------------------
# execute_query_strategy  (0%)
# ---------------------------------------------------------------------------


class TestExecuteQueryStrategy:
    def test_none_query(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy(None, "markdown")
        assert result is None

    def test_known_category(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("function", "markdown")
        assert isinstance(result, str)
        assert "atx_heading" in result

    def test_unknown_category_fallback_to_queries(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("nonexistent_key", "markdown")
        assert result is None

    def test_category_headers(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("headers", "markdown")
        assert isinstance(result, str) and "atx_heading" in result

    def test_category_links(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("links", "markdown")
        assert isinstance(result, str) and "inline" in result

    def test_category_all_elements(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("all_elements", "markdown")
        assert isinstance(result, str) and "atx_heading" in result


# ---------------------------------------------------------------------------
# _extract_pipe_tables  (10.5%)
# ---------------------------------------------------------------------------


class TestExtractPipeTables:
    def test_pipe_table(self):
        source = "| a | b |\n|---|---|\n| 1 | 2 |"
        ext = _setup_extractor(source)
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "pipe_table",
                    text=source,
                    start_point=(0, 0),
                    end_point=(2, 8),
                    start_byte=0,
                    end_byte=len(source.encode()),
                )
            ],
        )
        tables = []
        ext._extract_pipe_tables(root, tables)
        assert len(tables) == 1
        assert tables[0].element_type == "table"
        assert tables[0].type == "table"
        # header row + one data row (separator excluded); two columns a/b
        assert tables[0].row_count == 2
        assert tables[0].column_count == 2

    def test_pipe_table_no_pipe_node(self):
        ext = _setup_extractor("plain")
        root = _make_node("document", children=[_make_node("paragraph", text="plain")])
        tables = []
        ext._extract_pipe_tables(root, tables)
        assert len(tables) == 0


# ---------------------------------------------------------------------------
# _extract_emphasis_elements  (41.4%)
# ---------------------------------------------------------------------------


class TestExtractEmphasisElements:
    def test_bold(self):
        ext = _setup_extractor("**bold text**")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="**bold text**",
                    start_point=(0, 0),
                    end_point=(0, 13),
                )
            ],
        )
        elems = []
        ext._extract_emphasis_elements(root, elems)
        bold = [e for e in elems if e.element_type == "strong_emphasis"]
        assert len(bold) == 1
        assert bold[0].text == "bold text"

    def test_bold_underscore(self):
        ext = _setup_extractor("__bold text__")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="__bold text__",
                    start_point=(0, 0),
                    end_point=(0, 13),
                )
            ],
        )
        elems = []
        ext._extract_emphasis_elements(root, elems)
        bold = [e for e in elems if e.element_type == "strong_emphasis"]
        assert len(bold) == 1

    def test_italic(self):
        ext = _setup_extractor("*italic text*")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="*italic text*",
                    start_point=(0, 0),
                    end_point=(0, 13),
                )
            ],
        )
        elems = []
        ext._extract_emphasis_elements(root, elems)
        italic = [e for e in elems if e.element_type == "emphasis"]
        assert len(italic) == 1
        assert italic[0].text == "italic text"

    def test_italic_underscore(self):
        ext = _setup_extractor("_italic text_")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="_italic text_",
                    start_point=(0, 0),
                    end_point=(0, 13),
                )
            ],
        )
        elems = []
        ext._extract_emphasis_elements(root, elems)
        italic = [e for e in elems if e.element_type == "emphasis"]
        assert len(italic) == 1

    def test_no_inline(self):
        ext = _setup_extractor("plain")
        root = _make_node("document", children=[_make_node("paragraph", text="plain")])
        elems = []
        ext._extract_emphasis_elements(root, elems)
        assert len(elems) == 0


# ---------------------------------------------------------------------------
# _extract_strikethrough_elements  (42.9%)
# ---------------------------------------------------------------------------


class TestExtractStrikethrough:
    def test_strikethrough(self):
        ext = _setup_extractor("~~struck text~~")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="~~struck text~~",
                    start_point=(0, 0),
                    end_point=(0, 15),
                )
            ],
        )
        elems = []
        ext._extract_strikethrough_elements(root, elems)
        assert len(elems) == 1
        assert elems[0].element_type == "strikethrough"
        assert elems[0].text == "struck text"

    def test_strikethrough_no_inline(self):
        ext = _setup_extractor("plain")
        root = _make_node("document", children=[_make_node("paragraph", text="plain")])
        elems = []
        ext._extract_strikethrough_elements(root, elems)
        assert len(elems) == 0

    def test_strikethrough_multiple(self):
        ext = _setup_extractor("~~a~~ and ~~b~~")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="~~a~~ and ~~b~~",
                    start_point=(0, 0),
                    end_point=(0, 14),
                )
            ],
        )
        elems = []
        ext._extract_strikethrough_elements(root, elems)
        assert len(elems) == 2
