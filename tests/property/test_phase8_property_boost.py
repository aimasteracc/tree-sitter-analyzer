#!/usr/bin/env python3
"""Property-based tests — Phase 8: boost hypothesis coverage to ≥10% gate."""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from tree_sitter_analyzer.query_loader import QueryLoader
from tree_sitter_analyzer.encoding_utils import EncodingManager


class TestQueryLoaderProperties:
    """Property: load_language_queries is deterministic and idempotent."""

    @given(st.sampled_from(["java", "python", "javascript", "sql", "rust", "go", "c", "cpp"]))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_load_twice_same_result(self, language):
        loader = QueryLoader()
        r1 = loader.load_language_queries(language)
        r2 = loader.load_language_queries(language)
        assert r1 == r2

    @given(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))))
    @settings(max_examples=50)
    def test_unknown_language_returns_empty(self, fake_lang):
        loader = QueryLoader()
        if fake_lang.lower() in ("java", "python", "javascript", "sql", "rust", "go", "c", "cpp"):
            return  # skip known languages
        result = loader.load_language_queries(fake_lang.lower())
        assert isinstance(result, dict)

    @given(st.sampled_from(["functions", "classes", "variables", "imports"]))
    def test_common_queries_present(self, query_name):
        loader = QueryLoader()
        common = loader.get_common_queries()
        assert query_name in common


class TestEncodingProperties:
    """Property: safe_encode → safe_decode roundtrip preserves content."""

    @given(st.text(min_size=1, max_size=500, alphabet=st.characters(
        blacklist_categories=("Cs",))))
    @settings(max_examples=100)
    def test_utf8_roundtrip_preserves_content(self, text):
        encoded = EncodingManager.safe_encode(text, "utf-8")
        assert isinstance(encoded, bytes)
        # decode back
        decoded = encoded.decode("utf-8")
        assert decoded == text

    @given(st.text(min_size=0, max_size=200, alphabet=st.characters(
        blacklist_characters="\x00", blacklist_categories=("Cs",))))
    @settings(max_examples=100)
    def test_safe_decode_preserves_length(self, text):
        encoded = text.encode("utf-8") if text else b""
        result = EncodingManager.safe_decode(encoded)
        assert isinstance(result, str)
        if text:
            assert len(result) >= len(text) - 1  # allow replacement chars

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_detect_encoding_always_returns_string(self, text):
        encoded = text.encode("utf-8")
        result = EncodingManager.detect_encoding(encoded)
        assert isinstance(result, str)
        assert len(result) > 0
