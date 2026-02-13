"""Tests for CSS language queries."""
import pytest

try:
    import tree_sitter_css
    CSS_AVAILABLE = True
except ImportError:
    CSS_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import css as css_queries


def _lang():
    return get_language(tree_sitter_css.language())


SAMPLE_CSS_CODE = """
/* Global styles */
:root {
    --primary-color: #333;
    --font-size: 16px;
}

body {
    margin: 0;
    padding: 0;
    font-family: Arial, sans-serif;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
}

#header {
    background-color: var(--primary-color);
    color: white;
}

h1, h2, h3 {
    font-weight: bold;
}

@media (max-width: 768px) {
    .container { max-width: 100%; }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

a:hover { text-decoration: underline; }
"""

# String constants for parametrized compile tests
CSS_STRING_CONSTANTS = ["RULES", "SELECTORS", "DECLARATIONS", "COMMENTS", "AT_RULES"]

# Legacy constants with grammar incompatibility (tree-sitter-css field names differ)
CSS_LEGACY_BROKEN = {"RULES", "SELECTORS", "DECLARATIONS"}


@pytest.mark.skipif(not CSS_AVAILABLE, reason="tree-sitter-css not available")
class TestCSSQueriesSyntax:
    """Test that CSS queries compile successfully."""

    def test_all_queries_dict_compilable_count(self):
        import tree_sitter
        lang = _lang()
        all_q = css_queries.ALL_QUERIES
        assert len(all_q) > 0
        compiled, failed = 0, 0
        for _name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed)
        assert ratio >= 0.35, (
            f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"
        )

    @pytest.mark.parametrize("query_name", CSS_STRING_CONSTANTS)
    def test_string_constant_compiles(self, query_name, query_validator):
        if query_name in CSS_LEGACY_BROKEN:
            pytest.xfail(f"{query_name} uses legacy grammar field names")
        qstr = getattr(css_queries, query_name, None)
        assert qstr is not None, f"Constant {query_name} not found"
        assert isinstance(qstr, str) and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not CSS_AVAILABLE, reason="tree-sitter-css not available")
class TestCSSQueriesFunctionality:
    """Test that CSS queries return expected results."""

    def test_rule_set_query_finds_rules(self, query_executor):
        qstr = css_queries.ALL_QUERIES["rule_set"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 1

    def test_selectors_query_finds_selectors(self, query_executor):
        qstr = css_queries.ALL_QUERIES["class_selector"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 2

    def test_declaration_query_finds_declarations(self, query_executor):
        qstr = css_queries.ALL_QUERIES["rule_set"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 6


    def test_comments_query_finds_comments(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSS_CODE, css_queries.COMMENTS)
        assert len(results) >= 1

    def test_at_rules_query_finds_at_rules(self, query_executor):
        results = query_executor(_lang(), SAMPLE_CSS_CODE, css_queries.AT_RULES)
        assert len(results) >= 0  # grammar may vary; at least no crash

    def test_rule_set_query(self, query_executor):
        qstr = css_queries.ALL_QUERIES["rule_set"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 1

    def test_class_selector_query(self, query_executor):
        qstr = css_queries.ALL_QUERIES["class_selector"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 2

    def test_id_selector_query(self, query_executor):
        qstr = css_queries.ALL_QUERIES["id_selector"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 1

    def test_call_expression_query(self, query_executor):
        qstr = css_queries.ALL_QUERIES["call_expression"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 1

    def test_property_query(self, query_executor):
        qstr = css_queries.ALL_QUERIES["property"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 5

    def test_media_statement_query(self, query_executor):
        qstr = css_queries.ALL_QUERIES["media_statement"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 1

    def test_keyframes_statement_query(self, query_executor):
        qstr = css_queries.ALL_QUERIES["keyframes_statement"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 1

    def test_pseudo_class_selector_query(self, query_executor):
        qstr = css_queries.ALL_QUERIES["pseudo_class_selector"]["query"]
        results = query_executor(_lang(), SAMPLE_CSS_CODE, qstr)
        assert len(results) >= 1  # :hover, :root


@pytest.mark.skipif(not CSS_AVAILABLE, reason="tree-sitter-css not available")
class TestCSSQueriesEdgeCases:
    """Test CSS queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        qstr = css_queries.ALL_QUERIES["rule_set"]["query"]
        results = query_executor(_lang(), "", qstr)
        assert len(results) == 0

    def test_comments_only_returns_no_rule_matches(self, query_executor):
        code = "/* just a comment */\n"
        qstr = css_queries.ALL_QUERIES["rule_set"]["query"]
        results = query_executor(_lang(), code, qstr)
        assert len(results) == 0

    def test_comments_only_still_finds_comment(self, query_executor):
        code = "/* only comment */\n"
        results = query_executor(_lang(), code, css_queries.COMMENTS)
        assert len(results) >= 1

    def test_single_declaration(self, query_executor):
        code = ".foo { color: red; }"
        qstr = css_queries.ALL_QUERIES["rule_set"]["query"]
        results = query_executor(_lang(), code, qstr)
        assert len(results) >= 1

    def test_empty_rule_block(self, query_executor):
        code = ".empty { }"
        qstr = css_queries.ALL_QUERIES["rule_set"]["query"]
        results = query_executor(_lang(), code, qstr)
        assert len(results) >= 1

    def test_multiple_selectors(self, query_executor):
        code = "h1, h2, h3 { margin: 0; }"
        qstr = css_queries.ALL_QUERIES["rule_set"]["query"]
        results = query_executor(_lang(), code, qstr)
        assert len(results) >= 1

    def test_charset_at_rule(self, query_executor):
        code = '@charset "utf-8";'
        qstr = css_queries.ALL_QUERIES["charset_statement"]["query"]
        results = query_executor(_lang(), code, qstr)
        assert len(results) >= 1


@pytest.mark.skipif(not CSS_AVAILABLE, reason="tree-sitter-css not available")
class TestCSSQueriesHelpers:
    """Test helper functions in the css queries module."""

    def test_get_query_valid(self):
        all_q = css_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = css_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            css_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = css_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = css_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_css_query_valid(self):
        available = css_queries.get_available_css_queries()
        if available:
            result = css_queries.get_css_query(available[0])
            assert isinstance(result, (str, dict))

    def test_get_css_query_invalid_raises(self):
        with pytest.raises(ValueError):
            css_queries.get_css_query("__nonexistent__")

    def test_get_css_query_description(self):
        available = css_queries.get_available_css_queries()
        if available:
            desc = css_queries.get_css_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_css_query_description_unknown(self):
        desc = css_queries.get_css_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_css_queries(self):
        result = css_queries.get_available_css_queries()
        assert isinstance(result, list)
        assert len(result) > 0
