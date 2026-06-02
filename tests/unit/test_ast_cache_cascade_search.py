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
    assert _name_match_bonus("HandlerFunc", "hf") > 0
    assert _bounded_levenshtein("abcdef", "z", 2) == 3
    assert _bounded_levenshtein("abcdef", "zzzzzz", 2) == 3

    row = conn.execute("SELECT name FROM ast_symbol_rows LIMIT 1").fetchone()
    assert _row_get({}, "missing", "fallback") == "fallback"
    assert _row_get(row, "file", "fallback") == "fallback"

    conn.execute("DROP TABLE ast_symbol_rows")
    assert _like_rows(conn, "handle", None, 10) == []
    assert _fuzzy_rows(conn, None, 10) == []
