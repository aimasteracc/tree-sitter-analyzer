"""Tests for cascade symbol search fallbacks."""

from __future__ import annotations

import sqlite3


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE ast_symbol_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            file_path TEXT NOT NULL,
            language TEXT NOT NULL,
            line INTEGER NOT NULL DEFAULT 0,
            end_line INTEGER NOT NULL DEFAULT 0
        )"""
    )
    return conn


def _insert(
    conn: sqlite3.Connection,
    name: str,
    kind: str = "function",
    file_path: str = "app.py",
    language: str = "python",
    line: int = 1,
) -> None:
    conn.execute(
        "INSERT INTO ast_symbol_rows "
        "(name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, kind, file_path, language, line, line + 3),
    )


def test_cascade_search_exact_tier_scores_first() -> None:
    from tree_sitter_analyzer._ast_cache_search import search_symbols_cascade

    conn = _make_conn()
    _insert(conn, "HandlerFunc", kind="import", file_path="imports.py")
    _insert(conn, "HandlerFunc", kind="function", file_path="handlers.py")

    results = search_symbols_cascade(conn, "HandlerFunc", fts5_available=False)

    assert [result["match_tier"] for result in results] == ["exact", "exact"]
    assert results[0]["kind"] == "function"


def test_cascade_search_like_fallback() -> None:
    from tree_sitter_analyzer._ast_cache_search import search_symbols_cascade

    conn = _make_conn()
    _insert(conn, "handle_request", file_path="routes.py")

    results = search_symbols_cascade(conn, "request", fts5_available=False)

    assert results
    assert results[0]["name"] == "handle_request"
    assert results[0]["match_tier"] == "like"


def test_cascade_search_fuzzy_fallback_handles_typo() -> None:
    from tree_sitter_analyzer._ast_cache_search import search_symbols_cascade

    conn = _make_conn()
    _insert(conn, "handleFunc", file_path="handlers.py")

    results = search_symbols_cascade(conn, "HandlerFunc", fts5_available=False)

    assert results
    assert results[0]["name"] == "handleFunc"
    assert results[0]["match_tier"] == "fuzzy"


def test_cascade_search_respects_language_filter() -> None:
    from tree_sitter_analyzer._ast_cache_search import search_symbols_cascade

    conn = _make_conn()
    _insert(conn, "build", language="python", file_path="py.py")
    _insert(conn, "build", language="go", file_path="go.go")

    results = search_symbols_cascade(conn, "build", language="go", fts5_available=False)

    assert [result["language"] for result in results] == ["go"]


def test_cascade_search_short_or_empty_queries_stop_early() -> None:
    from tree_sitter_analyzer._ast_cache_search import search_symbols_cascade

    conn = _make_conn()
    _insert(conn, "x")

    assert search_symbols_cascade(conn, "   ", fts5_available=False) == []
    assert search_symbols_cascade(conn, "x", limit=0, fts5_available=False) == []
    assert search_symbols_cascade(conn, "x", fts5_available=False)[0]["name"] == "x"
    assert search_symbols_cascade(conn, "xy", fts5_available=False) == []


def test_cascade_private_fallback_helpers_cover_error_paths() -> None:
    from tree_sitter_analyzer._ast_cache_search import (
        _bounded_levenshtein,
        _extend_fuzzy_results,
        _fuzzy_rows,
        _like_rows,
        _name_match_bonus,
        _row_get,
    )

    conn = _make_conn()
    _insert(conn, "handleFunc", line=1)
    _insert(conn, "handlerFun", line=2)
    _insert(conn, "handlerFn", line=3)

    results: list[dict[str, object]] = []
    seen: set[tuple[str, str, int]] = set()
    _extend_fuzzy_results(conn, "!!!", None, 1, results, seen)
    assert results == []

    _extend_fuzzy_results(conn, "handlerFunc", None, 1, results, seen)
    assert len(results) == 3

    assert _name_match_bonus("HandlerFunc", "") == 0.0
    assert _name_match_bonus("HandlerFunc", "hf")
    assert _bounded_levenshtein("abcdef", "z", 2) == 3
    assert _bounded_levenshtein("abcdef", "zzzzzz", 2) == 3

    row = conn.execute("SELECT name FROM ast_symbol_rows LIMIT 1").fetchone()
    assert _row_get({}, "missing", "fallback") == "fallback"
    assert _row_get(row, "file", "fallback") == "fallback"

    conn.execute("DROP TABLE ast_symbol_rows")
    assert _like_rows(conn, "handle", None, 10) == []
    assert _fuzzy_rows(conn, None, 10) == []


# ---------------------------------------------------------------------------
# Issue #607 — test-file demotion must survive the cascade's final re-sort.
#
# fts_search_ranked demotes test files internally, but search_symbols_cascade
# re-sorted purely by relevance_score, so long descriptive test_* names (which
# match more conceptual-query tokens, hence better BM25) buried every
# production symbol below the truncation window.
# ---------------------------------------------------------------------------

_Q3_STYLE_QUERY = "where are stop words filtered out of search queries"


def _make_fts_conn() -> sqlite3.Connection:
    """In-memory conn with the production FTS5 schema (porter, #604/#606)."""
    conn = _make_conn()
    conn.execute(
        """CREATE VIRTUAL TABLE ast_symbols_fts
           USING fts5(name, kind, file_path, language, content='',
                      tokenize='porter unicode61')"""
    )
    return conn


def _insert_fts(
    conn: sqlite3.Connection,
    name: str,
    kind: str = "function",
    file_path: str = "app.py",
    language: str = "python",
    line: int = 1,
) -> None:
    _insert(conn, name, kind=kind, file_path=file_path, language=language, line=line)
    row_id = conn.execute(
        "SELECT id FROM ast_symbol_rows WHERE name = ? AND file_path = ? AND line = ?",
        (name, file_path, line),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO ast_symbols_fts(rowid, name, kind, file_path, language) "
        "VALUES (?, ?, ?, ?, ?)",
        (row_id, name, kind, file_path, language),
    )


_Q3_STYLE_TEST_NAMES = (
    "test_stop_words_filtered_out_of_search_queries",
    "test_stop_word_filter_applies_to_search_query",
    "test_filtered_stop_words_removed_from_search_queries",
    "test_search_query_stop_words_filtered",
    "test_stop_words_are_filtered_from_queries",
    "test_query_search_filters_out_stop_words",
)


def _seed_q3_style_rows(conn: sqlite3.Connection) -> None:
    """1 production symbol + 6 test symbols sharing MORE query tokens."""
    _insert_fts(
        conn,
        "filter_stop_words",
        file_path="tree_sitter_analyzer/search_filters.py",
    )
    for i, name in enumerate(_Q3_STYLE_TEST_NAMES, start=1):
        _insert_fts(
            conn,
            name,
            file_path="tests/unit/test_search_filters.py",
            line=i * 10,
        )


def test_cascade_conceptual_query_promotes_production_above_tests() -> None:
    """#607 RED: top-`limit` window must not be saturated by test symbols."""
    from tree_sitter_analyzer._ast_cache_search import search_symbols_cascade
    from tree_sitter_analyzer.utils.test_detection import is_test_file

    conn = _make_fts_conn()
    _seed_q3_style_rows(conn)

    out = search_symbols_cascade(conn, _Q3_STYLE_QUERY, limit=5)

    assert len(out) == 5
    assert out[0]["name"] == "filter_stop_words"
    assert [is_test_file(str(r["file"])) for r in out] == [
        False,
        True,
        True,
        True,
        True,
    ]


def test_cascade_test_intent_query_keeps_test_symbols_on_top() -> None:
    """Counter-direction pin: a query that asks about tests is NOT demoted."""
    from tree_sitter_analyzer._ast_cache_search import search_symbols_cascade
    from tree_sitter_analyzer.utils.test_detection import is_test_file

    conn = _make_fts_conn()
    _seed_q3_style_rows(conn)

    out = search_symbols_cascade(
        conn, "tests for stop words filtered out of search queries", limit=5
    )

    assert len(out) == 5
    # query_wants_tests('tests ...') is True -> no demotion: the descriptive
    # test_* names keep their better BM25 rank, exactly as before the fix.
    assert [is_test_file(str(r["file"])) for r in out] == [
        True,
        True,
        True,
        True,
        True,
    ]
