#!/usr/bin/env python3
"""Targeted tests for 0%-coverage and critically-low-coverage methods in markdown_plugin.py.

Covers: _extract_autolinks (0%), _extract_reference_images (0%),
_extract_inline_html (0%), execute_query_strategy (0%),
_extract_pipe_tables (10.5%), _extract_emphasis_elements (41.4%),
_extract_strikethrough_elements (42.9%), _extract_footnote_elements (43.2%),
_extract_inline_images (42.9%), _extract_image_reference_definitions (32.4%),
_extract_inline_links (34.6%).
"""

from unittest.mock import MagicMock, Mock, patch

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
    """Create a mock tree-sitter Node.

    If end_byte is None, it defaults to len(text.encode()) so
    _get_node_text_optimized can extract the full text from content_lines.
    If end_point is None, it defaults to (0, len(text)) for single-line nodes.
    """
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
    """Return an extractor with source_code and content_lines pre-filled."""
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
        assert len(elems) >= 1
        assert any(e.element_type == "html_inline" for e in elems)

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
        """HTML extractor should skip autolink-style angle brackets."""
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
        assert result is not None
        assert "atx_heading" in result

    def test_unknown_category_fallback_to_queries(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("nonexistent_key", "markdown")
        # Falls back to get_queries()
        assert result is None  # no such key in queries dict either

    def test_category_headers(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("headers", "markdown")
        assert result is not None

    def test_category_links(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("links", "markdown")
        assert result is not None

    def test_category_all_elements(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("all_elements", "markdown")
        assert result is not None


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
        assert tables[0].row_count >= 1
        assert tables[0].column_count >= 1

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
        assert len(bold) >= 1
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
        assert len(bold) >= 1

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
        assert len(italic) >= 1
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
        assert len(italic) >= 1

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
        assert len(elems) >= 1
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


# ---------------------------------------------------------------------------
# _extract_footnote_elements  (43.2%)
# ---------------------------------------------------------------------------


class TestExtractFootnoteElements:
    def test_footnote_reference(self):
        ext = _setup_extractor("text[^1] more")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="text[^1] more",
                    start_point=(0, 0),
                    end_point=(0, 13),
                )
            ],
        )
        footnotes = []
        ext._extract_footnote_elements(root, footnotes)
        refs = [f for f in footnotes if f.element_type == "footnote_reference"]
        assert len(refs) >= 1
        assert refs[0].text == "1"

    def test_footnote_definition(self):
        ext = _setup_extractor("[^1]: footnote content")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "paragraph",
                    text="[^1]: footnote content",
                    start_point=(0, 0),
                    end_point=(0, 21),
                )
            ],
        )
        footnotes = []
        ext._extract_footnote_elements(root, footnotes)
        defs = [f for f in footnotes if f.element_type == "footnote_definition"]
        assert len(defs) >= 1
        assert defs[0].text == "footnote content"

    def test_footnote_no_match(self):
        ext = _setup_extractor("plain paragraph")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "paragraph",
                    text="plain paragraph",
                    start_point=(0, 0),
                    end_point=(0, 15),
                )
            ],
        )
        footnotes = []
        ext._extract_footnote_elements(root, footnotes)
        assert len(footnotes) == 0


# ---------------------------------------------------------------------------
# _extract_inline_images  (42.9%)
# ---------------------------------------------------------------------------


class TestExtractInlineImages:
    def test_inline_image(self):
        ext = _setup_extractor("![alt](img.png)")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="![alt](img.png)",
                    start_point=(0, 0),
                    end_point=(0, 15),
                )
            ],
        )
        images = []
        ext._extract_inline_images(root, images)
        assert len(images) >= 1
        assert images[0].element_type == "image"
        assert images[0].url == "img.png"
        assert images[0].alt_text == "alt"

    def test_inline_image_no_inline(self):
        ext = _setup_extractor("plain")
        root = _make_node("document", children=[_make_node("paragraph", text="plain")])
        images = []
        ext._extract_inline_images(root, images)
        assert len(images) == 0


# ---------------------------------------------------------------------------
# _extract_image_reference_definitions  (32.4%)
# ---------------------------------------------------------------------------


class TestExtractImageRefDefs:
    def test_image_ref_by_usage(self):
        source_img_ref = "![img][logo]\n\n[logo]: photo.png"
        ext = _setup_extractor(source_img_ref)
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline", text="![img][logo]", start_point=(0, 0), end_point=(0, 11)
                ),
                _make_node(
                    "link_reference_definition",
                    text="[logo]: photo.png",
                    start_point=(2, 0),
                    end_point=(2, 16),
                    start_byte=len(b"![img][logo]\n\n"),
                    end_byte=len(source_img_ref.encode()),
                ),
            ],
        )
        images = []
        ext._extract_image_reference_definitions(root, images)
        assert len(images) >= 1
        assert any(i.element_type == "image_reference_definition" for i in images)

    def test_image_ref_by_url_extension(self):
        source = "[logo]: photo.png"
        ext = _setup_extractor(source)
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "link_reference_definition",
                    text=source,
                    start_point=(0, 0),
                    end_point=(0, 16),
                    start_byte=0,
                    end_byte=len(source.encode()),
                ),
            ],
        )
        images = []
        ext._extract_image_reference_definitions(root, images)
        assert len(images) >= 1
        assert images[0].url == "photo.png"

    def test_image_ref_no_match(self):
        ext = _setup_extractor("[link]: https://example.com")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "link_reference_definition",
                    text="[link]: https://example.com",
                    start_point=(0, 0),
                    end_point=(0, 27),
                ),
            ],
        )
        images = []
        ext._extract_image_reference_definitions(root, images)
        assert len(images) == 0


# ---------------------------------------------------------------------------
# _extract_inline_links  (34.6%)
# ---------------------------------------------------------------------------


class TestExtractInlineLinks:
    def test_inline_link(self):
        ext = _setup_extractor("[text](https://example.com)")
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text="[text](https://example.com)",
                    start_point=(0, 0),
                    end_point=(0, 27),
                )
            ],
        )
        links = []
        ext._extract_inline_links(root, links)
        assert len(links) >= 1
        assert links[0].element_type == "link"
        assert links[0].url == "https://example.com"

    def test_inline_link_no_inline(self):
        ext = _setup_extractor("plain")
        root = _make_node("document", children=[_make_node("paragraph", text="plain")])
        links = []
        ext._extract_inline_links(root, links)
        assert len(links) == 0

    def test_inline_link_with_title(self):
        ext = _setup_extractor('[text](https://example.com "title")')
        root = _make_node(
            "document",
            children=[
                _make_node(
                    "inline",
                    text='[text](https://example.com "title")',
                    start_point=(0, 0),
                    end_point=(0, 35),
                )
            ],
        )
        links = []
        ext._extract_inline_links(root, links)
        assert len(links) >= 1
        assert links[0].title == "title"


# ---------------------------------------------------------------------------
# Public methods that delegate to private extractors
# (increases coverage across multiple private methods)
# ---------------------------------------------------------------------------


class TestPublicExtractMethods:
    """Test public extract_* methods that delegate to private _extract_* methods."""

    def _mk_tree(self, root_children, source=""):
        tree = MagicMock()
        root = Mock()
        root.children = root_children
        tree.root_node = root
        return tree

    def test_extract_links_delegates(self):
        ext = _setup_extractor("[text](https://example.com)")
        tree = self._mk_tree(
            [
                _make_node(
                    "inline",
                    text="[text](https://example.com)",
                    start_point=(0, 0),
                    end_point=(0, 27),
                )
            ]
        )
        result = ext.extract_links(tree, ext.source_code)
        assert isinstance(result, list)

    def test_extract_images_delegates(self):
        ext = _setup_extractor("![alt](img.png)")
        tree = self._mk_tree(
            [
                _make_node(
                    "inline",
                    text="![alt](img.png)",
                    start_point=(0, 0),
                    end_point=(0, 15),
                )
            ]
        )
        result = ext.extract_images(tree, ext.source_code)
        assert isinstance(result, list)

    def test_extract_text_formatting(self):
        ext = _setup_extractor("**bold** *italic* ~~strike~~ `code`")
        tree = self._mk_tree(
            [
                _make_node(
                    "inline",
                    text="**bold** *italic* ~~strike~~ `code`",
                    start_point=(0, 0),
                    end_point=(0, 33),
                )
            ]
        )
        result = ext.extract_text_formatting(tree, ext.source_code)
        assert isinstance(result, list)

    def test_extract_footnotes(self):
        ext = _setup_extractor("[^1]: note\n\ntext[^1]")
        tree = self._mk_tree(
            [
                _make_node(
                    "paragraph", text="[^1]: note", start_point=(0, 0), end_point=(0, 8)
                ),
                _make_node(
                    "inline", text="text[^1]", start_point=(2, 0), end_point=(2, 7)
                ),
            ]
        )
        result = ext.extract_footnotes(tree, ext.source_code)
        assert isinstance(result, list)

    def test_extract_lists(self):
        ext = _setup_extractor("- item 1\n- item 2")
        tree = self._mk_tree(
            [
                _make_node(
                    "list",
                    children=[
                        _make_node(
                            "list_item",
                            text="- item 1",
                            start_point=(0, 0),
                            end_point=(0, 7),
                        ),
                        _make_node(
                            "list_item",
                            text="- item 2",
                            start_point=(1, 0),
                            end_point=(1, 7),
                        ),
                    ],
                    start_point=(0, 0),
                    end_point=(1, 7),
                ),
            ]
        )
        result = ext.extract_lists(tree, ext.source_code)
        assert isinstance(result, list)

    def test_extract_tables(self):
        source = "| a | b |\n|---|---|"
        ext = _setup_extractor(source)
        tree = self._mk_tree(
            [
                _make_node(
                    "pipe_table", text=source, start_point=(0, 0), end_point=(1, 8)
                ),
            ]
        )
        result = ext.extract_tables(tree, ext.source_code)
        assert isinstance(result, list)

    def test_extract_html_elements(self):
        ext = _setup_extractor("<span>text</span>")
        tree = self._mk_tree(
            [
                _make_node(
                    "html_block",
                    text="<span>text</span>",
                    start_point=(0, 0),
                    end_point=(0, 16),
                ),
            ]
        )
        result = ext.extract_html_elements(tree, ext.source_code)
        assert isinstance(result, list)

    def test_extract_horizontal_rules(self):
        ext = _setup_extractor("---")
        tree = self._mk_tree(
            [
                _make_node(
                    "thematic_break", text="---", start_point=(0, 0), end_point=(0, 3)
                ),
            ]
        )
        result = ext.extract_horizontal_rules(tree, ext.source_code)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# analyze_file branch paths
# ---------------------------------------------------------------------------


class TestAnalyzeFile:
    def test_empty_source(self):
        plugin = MarkdownPlugin()
        extractor = plugin.create_extractor()
        with patch.object(extractor, "extract_all_elements", return_value=[]):
            result = extractor.extract_all_elements(None, "")
        assert result == []


# ---------------------------------------------------------------------------
# MarkdownElement attributes
# ---------------------------------------------------------------------------


class TestMarkdownElementAttributes:
    def test_all_attributes_set(self):
        from tree_sitter_analyzer.languages.markdown_plugin import MarkdownElement

        elem = MarkdownElement(
            name="test",
            start_line=1,
            end_line=2,
            raw_text="text",
            level=3,
            url="http://example.com",
            alt_text="alt",
            title="title",
            language_info="python",
            is_checked=True,
        )
        elem.text = "content"
        elem.type = "test_type"
        elem.line_count = 5
        elem.alt = "alt_value"
        elem.list_type = "ordered"
        elem.item_count = 10
        elem.row_count = 3
        elem.column_count = 4
        assert elem.level == 3
        assert elem.url == "http://example.com"
        assert elem.alt_text == "alt"
        assert elem.title == "title"
        assert elem.language_info == "python"
        assert elem.is_checked is True
        assert elem.text == "content"
        assert elem.type == "test_type"
        assert elem.line_count == 5
        assert elem.alt == "alt_value"
        assert elem.list_type == "ordered"
        assert elem.item_count == 10
        assert elem.row_count == 3
        assert elem.column_count == 4

    def test_default_attributes(self):
        from tree_sitter_analyzer.languages.markdown_plugin import MarkdownElement

        elem = MarkdownElement(
            name="test",
            start_line=1,
            end_line=2,
            raw_text="text",
        )
        assert elem.level is None
        assert elem.url is None
        assert elem.alt_text is None
        assert elem.title is None
        assert elem.language_info is None
        assert elem.is_checked is None
        assert elem.text is None
        assert elem.type is None
        assert elem.line_count is None
        assert elem.alt is None
        assert elem.list_type is None
        assert elem.item_count is None
        assert elem.row_count is None
        assert elem.column_count is None
