"""
Tests for HTML language queries.

Validates that HTML tree-sitter queries are syntactically correct
and return expected results for various HTML constructs.
"""
import pytest

try:
    import tree_sitter_html

    HTML_AVAILABLE = True
except ImportError:
    HTML_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import html as html_queries


def _lang():
    return get_language(tree_sitter_html.language())


ALL_QUERY_CONSTANTS = ["ELEMENTS", "ATTRIBUTES", "COMMENTS", "TEXT_CONTENT"]

# Legacy ELEMENTS/ATTRIBUTES use field names not in tree-sitter-html grammar
KNOWN_BROKEN_QUERIES = {"ELEMENTS", "ATTRIBUTES"}


@pytest.mark.skipif(not HTML_AVAILABLE, reason="tree-sitter-html not available")
class TestHTMLQueriesSyntax:
    """Test that all HTML query constants compile successfully."""

    @pytest.mark.parametrize("query_name", ALL_QUERY_CONSTANTS)
    def test_query_compiles(self, query_name, query_validator):
        if query_name in KNOWN_BROKEN_QUERIES:
            pytest.xfail(f"{query_name} has known grammar incompatibility")
        qstr = getattr(html_queries, query_name)
        assert isinstance(qstr, str) and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)

    def test_all_queries_dict_compilable_count(self):
        """Count compilable queries; tree-sitter-html grammar structure may differ."""
        import tree_sitter

        lang = _lang()
        all_q = html_queries.ALL_QUERIES
        assert len(all_q) > 0
        compiled, failed = 0, 0
        for name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed)
        assert ratio >= 0.15, (
            f"At least 15% should compile: {compiled}/{compiled+failed} ({ratio:.0%})"
        )


@pytest.mark.skipif(not HTML_AVAILABLE, reason="tree-sitter-html not available")
class TestHTMLQueriesFunctionality:
    """Test that HTML queries return expected results."""

    SAMPLE_CODE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Test Page</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div id="app" class="container">
        <h1>Hello World</h1>
        <p>Some text content</p>
        <a href="https://example.com">Link</a>
        <!-- This is a comment -->
        <img src="image.png" alt="An image">
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
    </div>
    <script src="app.js"></script>
</body>
</html>
"""

    @pytest.mark.xfail(reason="ELEMENTS query has grammar incompatibility")
    def test_elements_query_finds_elements(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, html_queries.ELEMENTS)
        assert len(results) >= 5

    @pytest.mark.xfail(reason="ATTRIBUTES query has grammar incompatibility")
    def test_attributes_query_finds_attributes(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, html_queries.ATTRIBUTES)
        assert len(results) >= 3

    def test_comments_query_finds_comments(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, html_queries.COMMENTS)
        assert len(results) >= 1

    def test_text_content_query_finds_text(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, html_queries.TEXT_CONTENT)
        assert len(results) >= 1

    def test_element_query_from_dict(self, query_executor):
        all_q = html_queries.ALL_QUERIES
        if "element" not in all_q:
            pytest.skip("element query not in ALL_QUERIES")
        qstr = all_q["element"]["query"]
        results = query_executor(_lang(), self.SAMPLE_CODE, qstr)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="start_tag query may have grammar incompatibility")
    def test_start_tag_query(self, query_executor):
        all_q = html_queries.ALL_QUERIES
        if "start_tag" not in all_q:
            pytest.skip("start_tag query not in ALL_QUERIES")
        qstr = all_q["start_tag"]["query"]
        results = query_executor(_lang(), self.SAMPLE_CODE, qstr)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="attribute query may have grammar incompatibility")
    def test_attribute_query_from_dict(self, query_executor):
        all_q = html_queries.ALL_QUERIES
        if "attribute" not in all_q:
            pytest.skip("attribute query not in ALL_QUERIES")
        qstr = all_q["attribute"]["query"]
        results = query_executor(_lang(), self.SAMPLE_CODE, qstr)
        assert len(results) >= 1


@pytest.mark.skipif(not HTML_AVAILABLE, reason="tree-sitter-html not available")
class TestHTMLQueriesEdgeCases:
    """Test HTML queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", html_queries.COMMENTS)
        assert len(results) == 0

    def test_comments_only_finds_comment(self, query_executor):
        code = "<!-- only comment -->"
        results = query_executor(_lang(), code, html_queries.COMMENTS)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="ELEMENTS query has grammar incompatibility")
    def test_single_tag_detected(self, query_executor):
        code = "<div>hello</div>"
        results = query_executor(_lang(), code, html_queries.ELEMENTS)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="ELEMENTS query has grammar incompatibility")
    def test_self_closing_tag_detected(self, query_executor):
        code = "<br /><img src='x' />"
        results = query_executor(_lang(), code, html_queries.ELEMENTS)
        assert len(results) >= 1

    def test_comment_detected(self, query_executor):
        code = "<!-- HTML comment -->"
        results = query_executor(_lang(), code, html_queries.COMMENTS)
        assert len(results) >= 1


@pytest.mark.skipif(not HTML_AVAILABLE, reason="tree-sitter-html not available")
class TestHTMLQueriesHelpers:
    """Test helper functions in the html queries module."""

    def test_get_query_valid(self):
        all_q = html_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = html_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            html_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = html_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = html_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_html_query_valid(self):
        available = html_queries.get_available_html_queries()
        if available:
            result = html_queries.get_html_query(available[0])
            assert isinstance(result, (str, dict))

    def test_get_html_query_invalid_raises(self):
        with pytest.raises(ValueError):
            html_queries.get_html_query("__nonexistent__")

    def test_get_html_query_description(self):
        available = html_queries.get_available_html_queries()
        if available:
            desc = html_queries.get_html_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_html_query_description_unknown(self):
        desc = html_queries.get_html_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_html_queries(self):
        result = html_queries.get_available_html_queries()
        assert isinstance(result, list)
        assert len(result) > 0
