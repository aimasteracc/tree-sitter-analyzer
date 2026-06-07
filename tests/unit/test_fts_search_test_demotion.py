"""RED-first TDD tests for test-file demotion in fts_search_ranked.

Bug: fts_search_ranked ordered purely by BM25 score with no test-file
demotion. Within a name-match tier, test mock symbols beat production
implementations because they typically have better BM25 scores due to
higher mention density in test files.

Fix: apply rank_tier() / query_wants_tests() demotion as primary sort
key, consistent with semantic_search.SemanticSymbolSearch.search().
"""

from __future__ import annotations

import sqlite3

# ---------------------------------------------------------------------------
# Helpers — build an in-memory FTS5 connection
# ---------------------------------------------------------------------------


def _make_fts_conn() -> sqlite3.Connection:
    """Return an in-memory connection with the FTS5 schema used by fts_search_ranked."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE ast_symbol_rows (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            kind       TEXT NOT NULL,
            file_path  TEXT NOT NULL,
            language   TEXT NOT NULL,
            line       INTEGER NOT NULL DEFAULT 0,
            end_line   INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE VIRTUAL TABLE ast_symbols_fts
           USING fts5(name, kind, file_path, language, content='')"""
    )
    return conn


def _insert(
    conn: sqlite3.Connection,
    name: str,
    *,
    kind: str = "function",
    file_path: str = "src/foo.py",
    language: str = "python",
    line: int = 1,
) -> None:
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, kind, file_path, language, line, line + 10),
    )
    row_id = cur.lastrowid
    conn.execute(
        "INSERT INTO ast_symbols_fts(rowid, name, kind, file_path, language) "
        "VALUES (?, ?, ?, ?, ?)",
        (row_id, name, kind, file_path, language),
    )


# ---------------------------------------------------------------------------
# Tests — these MUST fail on current code (no demotion applied) and pass
# after the fix is implemented.
# ---------------------------------------------------------------------------


class TestFtsSearchRankedTestDemotion:
    """Production symbol must rank above test-file mock with the same name."""

    def test_production_symbol_beats_test_mock_by_default(self) -> None:
        """Core regression: fts_search_ranked returns production file first.

        Mirrors the verified real-world bug: searching `fts_search_ranked`
        returned 8 results all from tests/unit/test_codegraph_context_tool.py
        (mock defs) while the production impl in ast_cache.py ranked below.

        Use multiple test-file occurrences so that BM25 tie-breaks favour the
        test files by insertion order — exactly the real-world failure mode.
        """
        conn = _make_fts_conn()

        # Insert multiple test-file occurrences first (lower rowids = better
        # BM25 tie-break position in raw SQLite ordering).
        for i in range(3):
            _insert(
                conn,
                "foo",
                file_path=f"tests/unit/test_foo_{i}.py",
                kind="function",
                line=10 + i,
            )
        # Insert production symbol last — without demotion it ends up last.
        _insert(
            conn,
            "foo",
            file_path="src/foo.py",
            kind="function",
            line=5,
        )

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        results = fts_search_ranked(conn, "foo")

        assert results, "Expected at least one result"
        # Production file must appear first.
        assert results[0]["file"] == "src/foo.py", (
            f"Expected production file first, got {results[0]['file']!r}. "
            "Test mock is shadowing the production symbol."
        )

    def test_query_wants_tests_allows_test_symbol_up(self) -> None:
        """When query contains 'test', test symbols are NOT demoted."""
        conn = _make_fts_conn()
        _insert(conn, "foo", file_path="src/foo.py", kind="function", line=5)
        _insert(
            conn,
            "foo",
            file_path="tests/unit/test_foo.py",
            kind="function",
            line=10,
        )

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        results = fts_search_ranked(conn, "foo test")

        assert results, "Expected at least one result"
        # Both tiers are now 0 — verify both symbols are present.
        files = {r["file"] for r in results}
        assert "tests/unit/test_foo.py" in files
        assert "src/foo.py" in files

    def test_multiple_test_symbols_demoted_below_single_production(self) -> None:
        """Several test-file symbols all rank below the one production symbol."""
        conn = _make_fts_conn()

        for i in range(3):
            _insert(
                conn,
                "fts_search_ranked",
                file_path=f"tests/unit/test_file_{i}.py",
                kind="function",
                line=i * 10 + 1,
            )
        _insert(
            conn,
            "fts_search_ranked",
            file_path="tree_sitter_analyzer/ast_cache.py",
            kind="function",
            line=167,
        )

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        results = fts_search_ranked(conn, "fts_search_ranked")

        assert results, "Expected results"
        assert results[0]["file"] == "tree_sitter_analyzer/ast_cache.py", (
            f"Expected production implementation first, got {results[0]['file']!r}"
        )

    def test_production_promoted_even_when_buried_past_limit(self) -> None:
        """Codex P2 on #316: over-fetch so a production hit BM25-ranked outside
        the caller's ``limit`` window is still promoted above many test matches.

        Insert 30 test-file matches with EARLIER rowids (better raw BM25 tie
        position) and one production match LAST. With ``limit=5`` and a naive
        ``LIMIT 5`` in SQL, the production row would never be fetched. The
        over-fetch band must pull it in so demotion can rank it first.
        """
        conn = _make_fts_conn()

        for i in range(30):
            _insert(
                conn,
                "widget",
                file_path=f"tests/unit/test_widget_{i}.py",
                kind="function",
                line=i * 5 + 1,
            )
        _insert(
            conn,
            "widget",
            file_path="tree_sitter_analyzer/widget.py",
            kind="function",
            line=42,
        )

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        results = fts_search_ranked(conn, "widget", limit=5)

        assert results, "Expected results"
        assert len(results) == 5, "Result window must respect the caller's limit"
        assert results[0]["file"] == "tree_sitter_analyzer/widget.py", (
            "Production hit must be promoted above test matches even when BM25 "
            f"ranks it past the limit window; got {results[0]['file']!r}"
        )

    def test_secondary_sort_is_relevance_within_same_tier(self) -> None:
        """Within the production tier, relevance_score is set for all results."""
        conn = _make_fts_conn()

        _insert(conn, "foo", file_path="src/primary.py", kind="function", line=1)
        _insert(conn, "foo", file_path="src/secondary.py", kind="function", line=1)

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        results = fts_search_ranked(conn, "foo")

        # Both are non-test; both should be present with relevance_score set.
        assert len(results) >= 2
        prod = [r for r in results if r["file"].startswith("src/")]
        assert all(r.get("relevance_score") is not None for r in prod)

    def test_language_filter_preserved_with_demotion(self) -> None:
        """language= filter still works after demotion is added."""
        conn = _make_fts_conn()
        _insert(
            conn,
            "foo",
            file_path="tests/test_foo.py",
            kind="function",
            language="python",
        )
        _insert(
            conn,
            "foo",
            file_path="src/foo.py",
            kind="function",
            language="python",
        )
        _insert(
            conn,
            "foo",
            file_path="src/foo.go",
            kind="function",
            language="go",
        )

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        results = fts_search_ranked(conn, "foo", language="python")

        assert all(r["language"] == "python" for r in results)
        assert results[0]["file"] == "src/foo.py"

    def test_empty_query_returns_empty(self) -> None:
        """Short queries still short-circuit (unchanged behavior)."""
        conn = _make_fts_conn()
        _insert(conn, "f", file_path="src/f.py")

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        assert fts_search_ranked(conn, "f") == []
        assert fts_search_ranked(conn, "") == []
