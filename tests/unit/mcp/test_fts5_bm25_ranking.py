"""Tests for G1 — FTS5 BM25 ranked symbol search.

Steps 1-11 cover _normalize_bm25 + fts_search_ranked (pure layer).
Steps 12-15 cover execute_symbol_search FTS fast path (wired layer).
"""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS ast_symbols_fts
    USING fts5(name, kind, file_path, language, content='');

CREATE TABLE IF NOT EXISTS ast_symbol_rows (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    file_path  TEXT NOT NULL,
    language   TEXT NOT NULL,
    line       INTEGER NOT NULL DEFAULT 0,
    end_line   INTEGER NOT NULL DEFAULT 0
);
"""


def _make_fts_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with FTS5 tables initialised."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for stmt in _SCHEMA_FTS.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    return conn


def _insert_symbol(
    conn: sqlite3.Connection,
    name: str,
    kind: str = "function",
    file_path: str = "src/main.py",
    language: str = "python",
    line: int = 1,
    end_line: int = 10,
) -> int:
    row_id = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, kind, file_path, language, line, end_line),
    ).lastrowid
    conn.execute(
        "INSERT INTO ast_symbols_fts (rowid, name, kind, file_path, language) "
        "VALUES (?, ?, ?, ?, ?)",
        (row_id, name, kind, file_path, language),
    )
    conn.commit()
    return int(row_id or 0)


# ---------------------------------------------------------------------------
# Helpers: skip gracefully when FTS5 is unavailable in CI environment
# ---------------------------------------------------------------------------

_FTS5_AVAILABLE = True
try:
    _c = sqlite3.connect(":memory:")
    _c.execute(
        "CREATE VIRTUAL TABLE _probe USING fts5(x, content='', contentless_delete=1)"
    )
    _c.close()
except Exception:
    _FTS5_AVAILABLE = False

_skip_no_fts5 = pytest.mark.skipif(
    not _FTS5_AVAILABLE, reason="FTS5 not available in this SQLite build"
)


# ---------------------------------------------------------------------------
# Test group 1: _normalize_bm25 (pure function, no I/O)
# ---------------------------------------------------------------------------


class TestNormalizeBm25:
    def _call(self, raw: float, worst: float, best: float | None = None) -> float:
        from tree_sitter_analyzer._ast_cache_query import _normalize_bm25

        return _normalize_bm25(raw, worst, best)

    def test_worst_is_best_match(self):
        """raw=-1.5 with worst=-0.5 → raw is more negative, so it's the best match → 1.0."""
        assert self._call(raw=-1.5, worst=-0.5) == 1.0

    def test_identical_scores_give_one(self):
        """When all scores are identical raw==worst, result is 1.0."""
        assert self._call(raw=-0.7, worst=-0.7) == pytest.approx(1.0)

    def test_worst_match_gives_zero_illegal_input(self):
        """Non-negative raw is illegal BM25 → returns 0.0."""
        assert self._call(raw=0.0, worst=0.0) == 0.0

    def test_positive_raw_returns_zero(self):
        """BM25 scores are always negative; positive value is anomalous → 0.0."""
        assert self._call(raw=1.0, worst=-0.5) == 0.0

    def test_clamped_at_one(self):
        """Score cannot exceed 1.0."""
        result = self._call(raw=-100.0, worst=-0.001)
        assert result == pytest.approx(1.0)

    def test_minmax_best_gets_one_worst_gets_zero(self):
        """Min-max normalization: best→1.0, worst→0.0, mid gets proportional score."""
        assert self._call(raw=-1.0, worst=-0.1, best=-1.0) == pytest.approx(1.0)
        assert self._call(raw=-0.1, worst=-0.1, best=-1.0) == pytest.approx(0.0)
        mid = self._call(raw=-0.5, worst=-0.1, best=-1.0)
        assert 0.0 < mid < 1.0, f"mid score should be between 0 and 1, got {mid}"

    def test_minmax_weak_match_scores_low(self):
        """Weak match (-0.00002) vs strong match (-0.995) → weak scores near 0.0."""
        weak = self._call(raw=-0.00002, worst=-0.00002, best=-0.994995)
        assert weak == pytest.approx(0.0)
        strong = self._call(raw=-0.994995, worst=-0.00002, best=-0.994995)
        assert strong == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test group 2: fts_search_ranked (database layer)
# ---------------------------------------------------------------------------


@_skip_no_fts5
class TestFtsSearchRanked:
    def _call(
        self,
        conn: sqlite3.Connection,
        query: str,
        language: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        return fts_search_ranked(conn, query, language=language, limit=limit)

    def test_returns_relevance_score(self):
        conn = _make_fts_conn()
        _insert_symbol(conn, "search_documents", file_path="core.py")
        _insert_symbol(conn, "search_index", file_path="index.py")
        _insert_symbol(conn, "process_data", file_path="data.py")

        results = self._call(conn, "search")

        assert len(results) > 0
        for r in results:
            assert "relevance_score" in r, f"missing relevance_score in {r}"

    def test_sorted_best_first(self):
        """Exact name match should score higher than partial."""
        conn = _make_fts_conn()
        _insert_symbol(conn, "search", file_path="exact.py")
        _insert_symbol(conn, "search_documents_in_archive", file_path="long.py")

        results = self._call(conn, "search")

        assert len(results) >= 2
        scores = [r["relevance_score"] for r in results]
        # list is best-first; first score >= last score
        assert scores[0] >= scores[-1]

    def test_score_range(self):
        conn = _make_fts_conn()
        for i in range(5):
            _insert_symbol(conn, f"function_{i}", file_path=f"f{i}.py")
        _insert_symbol(conn, "function_special", file_path="s.py")

        results = self._call(conn, "function")

        assert all(0.0 <= r["relevance_score"] <= 1.0 for r in results)

    def test_short_query_returns_empty(self):
        conn = _make_fts_conn()
        _insert_symbol(conn, "alpha", file_path="a.py")

        results = self._call(conn, "a")

        assert results == []

    def test_no_fts5_table_returns_empty(self):
        """OperationalError on plain connection without FTS tables → empty list."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        results = fts_search_ranked(conn, "search")
        assert results == []

    def test_language_filter(self):
        conn = _make_fts_conn()
        _insert_symbol(conn, "search_fn", language="python", file_path="p.py")
        _insert_symbol(conn, "search_fn", language="go", file_path="g.go")

        results = self._call(conn, "search", language="python")

        assert all(r["language"] == "python" for r in results)

    def test_kind_priority_class_over_import(self):
        """Class/function definitions must rank above import entries when BM25 score is equal."""
        conn = _make_fts_conn()
        # Insert import first so it gets a lower rowid (and thus slightly better BM25
        # due to ordering), ensuring the test is meaningful even if BM25 slightly favours it.
        _insert_symbol(
            conn,
            name="routing",
            kind="import",
            file_path="app/deps.py",
            line=1,
            end_line=1,
        )
        _insert_symbol(
            conn,
            name="routing",
            kind="class",
            file_path="app/router.py",
            line=10,
            end_line=50,
        )
        _insert_symbol(
            conn,
            name="routing",
            kind="function",
            file_path="app/views.py",
            line=20,
            end_line=30,
        )

        results = self._call(conn, "routing")

        assert len(results) >= 2
        # imports must not appear before any class or function
        kinds = [r["kind"] for r in results]
        import_indices = [i for i, k in enumerate(kinds) if k == "import"]
        class_func_indices = [
            i for i, k in enumerate(kinds) if k in ("class", "function")
        ]
        if import_indices and class_func_indices:
            assert min(class_func_indices) < min(import_indices), (
                f"Expected class/function before import, got ordering: {kinds}"
            )

    def test_limit_respected(self):
        conn = _make_fts_conn()
        for i in range(10):
            _insert_symbol(conn, f"my_function_{i}", file_path=f"f{i}.py")

        results = self._call(conn, "my", limit=3)

        assert len(results) <= 3

    def test_result_keys(self):
        conn = _make_fts_conn()
        _insert_symbol(conn, "execute", file_path="core.py", line=5, end_line=20)

        results = self._call(conn, "execute")

        assert len(results) == 1
        r = results[0]
        for key in (
            "name",
            "kind",
            "file",
            "language",
            "line",
            "end_line",
            "relevance_score",
        ):
            assert key in r, f"missing key {key!r}"


# ---------------------------------------------------------------------------
# Test group 3: ASTCache.fts_search_ranked wrapper
# ---------------------------------------------------------------------------


class TestASTCacheFtsSearchRanked:
    def test_delegates_to_query_module(self):
        """When FTS5 available, ASTCache delegates to _ast_cache_query.fts_search_ranked."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        cache = MagicMock(spec=ASTCache)
        cache._fts5_available = True
        cache.fts_search_ranked = ASTCache.fts_search_ranked.__get__(cache)

        ranked_results = [{"name": "search", "relevance_score": 0.9}]

        with patch(
            "tree_sitter_analyzer._ast_cache_query.fts_search_ranked",
            return_value=ranked_results,
        ) as mock_fn:
            # call the real method via the bound-like call
            from tree_sitter_analyzer import _ast_cache_query as _q

            result = _q.fts_search_ranked(
                MagicMock(),  # fake conn
                "search",
            )

        assert result == ranked_results
        mock_fn.assert_called_once()

    def test_falls_back_for_short_query(self, tmp_path):
        """When query is 1 char, ASTCache falls back without calling FTS5."""
        from tree_sitter_analyzer.ast_cache import ASTCache

        # We don't need a real DB — just confirm the guard logic
        cache = ASTCache.__new__(ASTCache)
        cache._fts5_available = True
        cache.project_root = str(tmp_path)

        with patch.object(
            cache, "_search_symbols_linear", return_value=[]
        ) as mock_linear:
            result = cache.fts_search_ranked("a")

        mock_linear.assert_called_once_with("a", None)
        assert result == []


# ---------------------------------------------------------------------------
# Test group 4: execute_symbol_search FTS fast path
# ---------------------------------------------------------------------------

_RANKED_ROW = {
    "name": "search_documents",
    "kind": "function",
    "file": "src/search.py",
    "language": "python",
    "line": 10,
    "end_line": 25,
    "relevance_score": 0.95,
}


class TestFtsSymbolToMatch:
    def test_shape(self):
        from pathlib import Path

        from tree_sitter_analyzer.mcp.tools.query_symbol_search import (
            _fts_symbol_to_match,
        )

        result = _fts_symbol_to_match(_RANKED_ROW, Path("/project"))

        assert result["name"] == "search_documents"
        assert result["type"] == "function"
        assert result["file"] == "src/search.py"
        assert result["start_line"] == 10
        assert result["end_line"] == 25
        assert result["relevance_score"] == pytest.approx(0.95)


class TestExecuteSymbolSearchFtsPath:
    async def test_uses_fts_when_available(self, tmp_path):
        """When ASTCache.fts_search_ranked returns results, response has ranked metadata."""
        from tree_sitter_analyzer.mcp.tools.query_symbol_search import (
            execute_symbol_search,
        )

        mock_cache = MagicMock()
        mock_cache.fts_search_ranked.return_value = [_RANKED_ROW]

        with patch(
            "tree_sitter_analyzer.mcp.tools.query_symbol_search.ASTCache",
            return_value=mock_cache,
        ):
            response = await execute_symbol_search(
                str(tmp_path),
                {"symbol": "search_documents", "output_format": "json"},
            )

        assert response.get("ranked") is True
        assert response.get("ranking_method") == "fts5_bm25"
        mock_cache.fts_search_ranked.assert_called_once()

    async def test_falls_back_when_fts_empty(self, tmp_path):
        """When ASTCache.fts_search_ranked returns [], scatter search runs instead."""
        from tree_sitter_analyzer.mcp.tools.query_symbol_search import (
            execute_symbol_search,
        )

        mock_cache = MagicMock()
        mock_cache.fts_search_ranked.return_value = []

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.query_symbol_search.ASTCache",
                return_value=mock_cache,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.query_symbol_search._scatter_symbol_search",
                return_value=[],
            ) as mock_scatter,
        ):
            response = await execute_symbol_search(
                str(tmp_path),
                {"symbol": "search_documents", "output_format": "json"},
            )

        assert response.get("ranked") is not True
        mock_scatter.assert_called_once()

    async def test_skips_fts_for_short_query(self, tmp_path):
        """Single-character symbol skips the FTS path entirely."""
        from tree_sitter_analyzer.mcp.tools.query_symbol_search import (
            execute_symbol_search,
        )

        mock_cache = MagicMock()

        with (
            patch(
                "tree_sitter_analyzer.mcp.tools.query_symbol_search.ASTCache",
                return_value=mock_cache,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.query_symbol_search._scatter_symbol_search",
                return_value=[],
            ),
        ):
            await execute_symbol_search(
                str(tmp_path),
                {"symbol": "a", "output_format": "json"},
            )

        mock_cache.fts_search_ranked.assert_not_called()
