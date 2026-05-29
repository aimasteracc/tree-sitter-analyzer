"""Tests for SemanticSymbolSearch — cosine reranking over BM25 candidates."""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.semantic_search import SemanticSymbolSearch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE ast_symbol_rows (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    kind     TEXT NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL,
    line     INTEGER DEFAULT 0,
    end_line INTEGER DEFAULT 0
);
CREATE VIRTUAL TABLE ast_symbols_fts
    USING fts5(name, kind, file_path, language, content='');
"""


def _make_cache(rows: list[tuple[str, str, str, str]]) -> Any:
    """Return a mock cache with FTS5 + symbol_rows seeded from rows."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for stmt in _SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    for name, kind, file_path, language in rows:
        row_id = conn.execute(
            "INSERT INTO ast_symbol_rows(name, kind, file_path, language) VALUES(?,?,?,?)",
            (name, kind, file_path, language),
        ).lastrowid
        conn.execute(
            "INSERT INTO ast_symbols_fts(rowid, name, kind, file_path, language) VALUES(?,?,?,?,?)",
            (row_id, name, kind, file_path, language),
        )
    conn.commit()

    cache = MagicMock()
    cache.get_conn.return_value = conn
    cache._fts5_available = True
    # Delegate fts_search_ranked to a real implementation for accuracy.
    from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

    cache.fts_search_ranked.side_effect = lambda q, **kw: fts_search_ranked(
        conn, q, **kw
    )
    return cache


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSemanticSymbolSearchFallback:
    def test_returns_scored_results(self):
        cache = _make_cache(
            [
                ("format_user", "function", "utils.py", "python"),
                ("delete_session", "function", "auth.py", "python"),
            ]
        )
        cache._fts5_available = False  # force full-scan fallback

        results = SemanticSymbolSearch(cache).search("user formatting", limit=5)

        assert len(results) >= 1
        assert results[0]["name"] == "format_user"
        assert results[0]["semantic_score"] > 0

    def test_short_query_uses_full_scan(self):
        """Queries shorter than 2 chars bypass BM25 pre-filter."""
        cache = _make_cache([("a", "function", "a.py", "python")])

        with patch.object(cache, "fts_search_ranked") as mock_fts:
            SemanticSymbolSearch(cache).search("a", limit=5)

        mock_fts.assert_not_called()

    def test_empty_query_returns_empty(self):
        cache = _make_cache([("foo", "function", "foo.py", "python")])
        results = SemanticSymbolSearch(cache).search("", limit=5)
        assert results == []

    def test_no_fts5_uses_full_scan(self):
        cache = _make_cache([("find_user", "function", "users.py", "python")])
        cache._fts5_available = False

        with patch.object(cache, "fts_search_ranked") as mock_fts:
            results = SemanticSymbolSearch(cache).search("find user", limit=5)

        mock_fts.assert_not_called()
        assert any(r["name"] == "find_user" for r in results)


class TestSemanticSymbolSearchBm25Path:
    def test_bm25_prefilter_called_for_long_query(self):
        cache = _make_cache([("format_user", "function", "utils.py", "python")])

        with patch.object(cache, "fts_search_ranked", return_value=[]) as mock_fts:
            SemanticSymbolSearch(cache).search("format user", limit=5)

        mock_fts.assert_called_once()

    def test_falls_back_when_fts_returns_empty(self):
        """When BM25 finds nothing, fall back to full scan."""
        cache = _make_cache([("format_user", "function", "utils.py", "python")])
        cache.fts_search_ranked.return_value = []

        results = SemanticSymbolSearch(cache).search("format user", limit=5)

        assert any(r["name"] == "format_user" for r in results)

    def test_candidate_pool_size_is_multiplied(self):
        """Pool size = limit * _BM25_CANDIDATE_MULTIPLIER."""
        cache = _make_cache([("foo", "function", "a.py", "python")])
        searcher = SemanticSymbolSearch(cache)
        multiplier = searcher._BM25_CANDIDATE_MULTIPLIER

        with patch.object(cache, "fts_search_ranked", return_value=[]) as mock_fts:
            searcher.search("foo bar", limit=10)

        mock_fts.assert_called_once_with("foo bar", limit=10 * multiplier)

    def test_semantic_score_in_results(self):
        cache = _make_cache(
            [
                ("search_documents", "function", "search.py", "python"),
                ("process_data", "function", "process.py", "python"),
            ]
        )

        results = SemanticSymbolSearch(cache).search("search document", limit=5)

        assert any("semantic_score" in r for r in results)
        if results:
            assert results[0]["semantic_score"] > 0.0
