#!/usr/bin/env python3
"""Property: QueryLoader.is_language_supported and get_query idempotency."""

from hypothesis import given
from hypothesis import strategies as st

from tree_sitter_analyzer.query_loader import QueryLoader


class TestQueryIdempotency:
    """get_query is deterministic for known key-language pairs."""

    @given(
        st.sampled_from(["java", "python", "javascript"]),
        st.sampled_from(["class", "method", "function", "import", "field", "package"]),
    )
    def test_get_query_deterministic(self, language, query_key):
        loader = QueryLoader()
        r1 = loader.get_query(language, query_key)
        r2 = loader.get_query(language, query_key)
        assert r1 == r2

    @given(st.sampled_from(["java", "python", "javascript", "go", "rust", "sql"]))
    def test_is_language_supported_consistent(self, language):
        loader = QueryLoader()
        r1 = loader.is_language_supported(language)
        r2 = loader.is_language_supported(language)
        assert r1 == r2

    @given(st.sampled_from(["java", "python", "javascript"]))
    def test_list_queries_non_empty(self, language):
        loader = QueryLoader()
        queries = loader.list_queries_for_language(language)
        assert isinstance(queries, list)
        assert queries

    @given(st.sampled_from(["java", "python", "javascript"]))
    def test_get_all_queries_has_tuples(self, language):
        loader = QueryLoader()
        result = loader.get_all_queries_for_language(language)
        assert isinstance(result, dict)
        for name, value in result.items():
            assert isinstance(value, tuple), (
                f"{name} should be tuple, got {type(value)}"
            )
            assert len(value) == 2
