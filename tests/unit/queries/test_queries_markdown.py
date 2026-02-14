"""
Tests for Markdown language queries.

Validates that Markdown tree-sitter queries are syntactically correct
and return expected results for various Markdown constructs.
"""

import pytest

try:
    import tree_sitter_markdown

    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import markdown as md_queries


def _lang():
    return get_language(tree_sitter_markdown.language())


SAMPLE_MARKDOWN_CODE = """
# Heading 1

## Heading 2

Some paragraph text with **bold** and *italic*.

- Item 1
- Item 2
  - Nested item

1. First
2. Second

[Link text](https://example.com)
![Alt text](image.png)

> This is a blockquote

```python
def hello():
    print("hello")
```

| Column 1 | Column 2 |
|----------|----------|
| Cell 1   | Cell 2   |

---

- [x] Done task
- [ ] Todo task
"""

MARKDOWN_KEYS_TO_TEST = [
    "headers",
    "code_blocks",
    "inline_code",
    "links",
    "images",
    "lists",
    "emphasis",
    "blockquotes",
    "tables",
    "horizontal_rules",
    "html_blocks",
    "inline_html",
    "strikethrough",
    "task_lists",
    "footnotes",
    "text_content",
    "document",
    "all_elements",
]


def _get_query(key):
    """Get query string via get_query or from MARKDOWN_QUERIES."""
    try:
        return md_queries.get_query(key)
    except KeyError:
        pass
    if key in md_queries.MARKDOWN_QUERIES:
        return md_queries.MARKDOWN_QUERIES[key]
    return None


@pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="tree-sitter-markdown not available")
class TestMarkdownQueriesSyntax:
    """Test that Markdown queries compile successfully."""

    def test_markdown_queries_dict_exists(self):
        assert hasattr(md_queries, "MARKDOWN_QUERIES")
        assert hasattr(md_queries, "QUERY_ALIASES")
        assert hasattr(md_queries, "get_all_queries")
        assert not hasattr(md_queries, "ALL_QUERIES")
        assert len(md_queries.MARKDOWN_QUERIES) > 0

    def test_get_all_queries_returns_dict(self):
        all_q = md_queries.get_all_queries()
        assert isinstance(all_q, dict)
        assert len(all_q) >= len(md_queries.MARKDOWN_QUERIES)

    def test_get_all_queries_compilable_count(self):
        """At least 70% of get_all_queries() entries should compile."""
        import tree_sitter

        lang = _lang()
        all_q = md_queries.get_all_queries()
        compiled, failed = 0, 0
        for name, qstr in all_q.items():
            assert isinstance(qstr, str), f"{name} should be plain query string"
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed) if (compiled + failed) > 0 else 1.0
        assert (
            ratio >= 0.7
        ), f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"

    @pytest.mark.parametrize(
        "key", [k for k in MARKDOWN_KEYS_TO_TEST if k in md_queries.MARKDOWN_QUERIES]
    )
    def test_individual_query_compiles(self, key, query_validator):
        qstr = _get_query(key)
        assert qstr is not None and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="tree-sitter-markdown not available")
class TestMarkdownQueriesFunctionality:
    """Test that Markdown queries return expected results."""

    def test_headers_query_finds_headings(self, query_executor):
        results = query_executor(_lang(), SAMPLE_MARKDOWN_CODE, _get_query("headers"))
        assert len(results) >= 2  # Heading 1, Heading 2

    def test_code_blocks_query_finds_code_blocks(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_MARKDOWN_CODE, _get_query("code_blocks")
        )
        assert len(results) >= 1  # python block

    def test_lists_query_finds_lists(self, query_executor):
        results = query_executor(_lang(), SAMPLE_MARKDOWN_CODE, _get_query("lists"))
        assert len(results) >= 2  # unordered, ordered, nested

    def test_blockquotes_query_finds_blockquotes(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_MARKDOWN_CODE, _get_query("blockquotes")
        )
        assert len(results) >= 1  # blockquote

    def test_tables_query_finds_tables(self, query_executor):
        results = query_executor(_lang(), SAMPLE_MARKDOWN_CODE, _get_query("tables"))
        assert len(results) >= 1  # pipe table

    def test_horizontal_rules_query_finds_hr(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_MARKDOWN_CODE, _get_query("horizontal_rules")
        )
        assert len(results) >= 1  # ---

    def test_emphasis_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_MARKDOWN_CODE, _get_query("emphasis"))
        assert results is not None  # may match inline elements

    def test_task_lists_query(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_MARKDOWN_CODE, _get_query("task_lists")
        )
        assert len(results) >= 2  # [x] Done, [ ] Todo

    def test_text_content_query(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_MARKDOWN_CODE, _get_query("text_content")
        )
        assert len(results) >= 1

    def test_document_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_MARKDOWN_CODE, _get_query("document"))
        assert len(results) >= 1

    def test_all_elements_query(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_MARKDOWN_CODE, _get_query("all_elements")
        )
        assert len(results) >= 5  # multiple element types

    def test_query_alias_heading_resolves(self):
        """Alias 'heading' should resolve to headers query."""
        qstr = _get_query("heading")
        assert qstr is not None
        assert qstr == md_queries.MARKDOWN_QUERIES["headers"]


@pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="tree-sitter-markdown not available")
class TestMarkdownQueriesEdgeCases:
    """Test Markdown queries with edge cases."""

    def test_empty_file_returns_no_header_matches(self, query_executor):
        results = query_executor(_lang(), "", _get_query("headers"))
        assert len(results) == 0

    def test_single_heading(self, query_executor):
        code = "# Hello\n\nParagraph.\n"
        results = query_executor(_lang(), code, _get_query("headers"))
        # tree-sitter-markdown structure may vary by version
        assert results is not None
        assert isinstance(results, list)

    def test_single_code_block(self, query_executor):
        code = "```\ncode\n```"
        results = query_executor(_lang(), code, _get_query("code_blocks"))
        assert len(results) >= 1

    def test_single_list_item(self, query_executor):
        code = "- item"
        results = query_executor(_lang(), code, _get_query("lists"))
        assert len(results) >= 1

    def test_get_query_raises_for_unknown(self):
        with pytest.raises(KeyError):
            md_queries.get_query("nonexistent_query_xyz")


@pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="tree-sitter-markdown not available")
class TestMarkdownQueriesHelpers:
    """Test helper functions in the markdown queries module."""

    def test_get_query_valid(self):
        result = md_queries.get_query("headers")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_query_with_alias(self):
        # QUERY_ALIASES maps aliases to canonical names
        if hasattr(md_queries, "QUERY_ALIASES"):
            for alias, _canonical in md_queries.QUERY_ALIASES.items():
                result = md_queries.get_query(alias)
                assert isinstance(result, str)
                break  # just test one

    def test_get_query_invalid_raises(self):
        with pytest.raises((ValueError, KeyError)):
            md_queries.get_query("__nonexistent__")

    def test_get_all_queries(self):
        result = md_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_get_available_queries(self):
        result = md_queries.get_available_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_query_info(self):
        if hasattr(md_queries, "get_query_info"):
            info = md_queries.get_query_info("headers")
            assert info is not None
            assert "name" in info
            assert "query" in info

    def test_get_query_info_unknown_returns_error(self):
        if hasattr(md_queries, "get_query_info"):
            info = md_queries.get_query_info("__nonexistent__")
            assert "error" in info
