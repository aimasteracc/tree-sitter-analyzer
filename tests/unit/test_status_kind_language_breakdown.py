"""RED-first TDD tests for symbols_by_kind / symbols_by_language / edges_by_kind
in the status response.

Task brief (feature/status-kind-language-breakdown):
- ``get_stats()`` in ``_ast_cache_query.py`` must return
  ``symbols_by_kind``  (dict kind→count) and
  ``symbols_by_language`` (dict language→count)
  sourced from ``ast_symbol_rows`` GROUP-BY queries.
- If ``ast_symbol_rows`` is absent (FTS5 unavailable), degrade to empty dicts.
- ``edges_by_kind`` sourced from ``SELECT kind, COUNT(*) FROM edges GROUP BY kind``.
- These breakdowns must flow through:
    * MCP: ``ast_cache mode=stats`` (via ``_handle_stats`` in ``ast_cache_tool.py``)
    * MCP: ``codegraph_status`` (via ``CodeGraphStatusTool._safe_get_stats``)

IMPORTANT: We assert on STRUCTURE (dicts present, sums to total_symbols),
NOT on specific kind="method" counts — the kind-classification engineer
may still emit those as kind="function" in this worktree.
"""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.cache.query import get_stats

# ---------------------------------------------------------------------------
# Helpers: minimal in-memory SQLite fixtures
# ---------------------------------------------------------------------------


def _make_conn_with_symbols(rows: list[tuple[str, str, str]]) -> sqlite3.Connection:
    """Return a sqlite3.Connection with ast_symbol_rows populated.

    ``rows`` is a list of (name, kind, language) triples.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE ast_index (
            file_path    TEXT,
            language     TEXT,
            symbols_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE ast_symbol_rows (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            kind      TEXT NOT NULL,
            file_path TEXT NOT NULL DEFAULT '',
            language  TEXT NOT NULL DEFAULT '',
            line      INTEGER NOT NULL DEFAULT 0,
            end_line  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE edges (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            source_node_id TEXT NOT NULL DEFAULT '',
            target_node_id TEXT NOT NULL DEFAULT '',
            kind           TEXT NOT NULL,
            line           INTEGER
        )
        """
    )
    # Insert symbol rows
    for name, kind, lang in rows:
        conn.execute(
            "INSERT INTO ast_symbol_rows (name, kind, file_path, language) "
            "VALUES (?, ?, 'f.py', ?)",
            (name, kind, lang),
        )
    # Insert one ast_index row per distinct language so total_files > 0
    langs_seen: set[str] = set()
    for _, _, lang in rows:
        if lang not in langs_seen:
            langs_seen.add(lang)
            conn.execute(
                "INSERT INTO ast_index (file_path, language, symbols_json) "
                "VALUES (?, ?, ?)",
                (f"f_{lang}.py", lang, '{"symbols": []}'),
            )
    conn.commit()
    return conn


def _add_edges(conn: sqlite3.Connection, edges: list[tuple[str, str]]) -> None:
    """Insert (source, kind) edge rows into an existing connection."""
    for src, kind in edges:
        conn.execute(
            "INSERT INTO edges (source_node_id, target_node_id, kind) VALUES (?, ?, ?)",
            (src, "target", kind),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Tests for get_stats() in _ast_cache_query.py
# ---------------------------------------------------------------------------


class TestGetStatsBreakdowns:
    """RED tests: these fail until symbols_by_kind/by_language are added."""

    def test_symbols_by_kind_present_in_stats(self) -> None:
        """get_stats must return a symbols_by_kind dict."""
        conn = _make_conn_with_symbols(
            [
                ("MyClass", "class", "python"),
                ("my_func", "function", "javascript"),
            ]
        )
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        assert "symbols_by_kind" in stats, (
            "get_stats() must return 'symbols_by_kind' dict"
        )
        assert isinstance(stats["symbols_by_kind"], dict)

    def test_symbols_by_language_present_in_stats(self) -> None:
        """get_stats must return a symbols_by_language dict."""
        conn = _make_conn_with_symbols(
            [
                ("MyClass", "class", "python"),
                ("my_func", "function", "javascript"),
            ]
        )
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        assert "symbols_by_language" in stats, (
            "get_stats() must return 'symbols_by_language' dict"
        )
        assert isinstance(stats["symbols_by_language"], dict)

    def test_symbols_by_kind_values_sum_to_total_symbols(self) -> None:
        """symbols_by_kind values must sum to total_symbols."""
        rows = [
            ("ClassA", "class", "python"),
            ("ClassB", "class", "python"),
            ("func_one", "function", "python"),
            ("func_two", "function", "javascript"),
        ]
        conn = _make_conn_with_symbols(rows)
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        total = stats["total_symbols"]
        kind_sum = sum(stats["symbols_by_kind"].values())
        assert kind_sum == total, (
            f"sum(symbols_by_kind.values())={kind_sum} must equal total_symbols={total}"
        )

    def test_symbols_by_language_counts_correct(self) -> None:
        """symbols_by_language must reflect actual per-language row counts."""
        rows = [
            ("ClassA", "class", "python"),
            ("ClassB", "class", "python"),
            ("func_one", "function", "javascript"),
        ]
        conn = _make_conn_with_symbols(rows)
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        by_lang = stats["symbols_by_language"]
        assert by_lang.get("python") == 2, f"expected python=2, got {by_lang}"
        assert by_lang.get("javascript") == 1, f"expected javascript=1, got {by_lang}"

    def test_symbols_by_kind_counts_correct(self) -> None:
        """symbols_by_kind must count correctly per kind bucket."""
        rows = [
            ("ClassA", "class", "python"),
            ("ClassB", "class", "python"),
            ("func_one", "function", "python"),
        ]
        conn = _make_conn_with_symbols(rows)
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        by_kind = stats["symbols_by_kind"]
        assert by_kind.get("class") == 2, f"expected class=2, got {by_kind}"
        # function count >=1; not asserting exact value because the method-
        # classification engineer may reclassify some entries.
        assert by_kind.get("function", 0)

    def test_symbols_by_kind_includes_constant_bucket(self) -> None:
        """Issue #610 — kind='constant' rows (Python module constants) must
        surface as their own symbols_by_kind bucket."""
        rows = [
            ("MAX_RETRIES", "constant", "python"),
            ("_STOP_WORDS", "constant", "python"),
            ("my_func", "function", "python"),
        ]
        conn = _make_conn_with_symbols(rows)
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        by_kind = stats["symbols_by_kind"]
        assert by_kind.get("constant") == 2, f"expected constant=2, got {by_kind}"

    def test_degrade_gracefully_when_fts5_unavailable(self) -> None:
        """When fts5_available=False, symbols_by_kind/by_language are empty dicts."""
        conn = _make_conn_with_symbols([("ClassA", "class", "python")])
        # Drop ast_symbol_rows to simulate the unavailable path.
        conn.execute("DROP TABLE ast_symbol_rows")
        conn.commit()
        stats = get_stats(conn, fts5_available=False, db_path=":memory:")
        assert stats.get("symbols_by_kind") == {}
        assert stats.get("symbols_by_language") == {}

    def test_degrade_gracefully_when_table_absent_but_flag_true(self) -> None:
        """If ast_symbol_rows is absent and fts5_available=True, empty dicts (no raise)."""
        conn = _make_conn_with_symbols([])
        conn.execute("DROP TABLE ast_symbol_rows")
        conn.commit()
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        assert isinstance(stats.get("symbols_by_kind"), dict)
        assert isinstance(stats.get("symbols_by_language"), dict)

    def test_edges_by_kind_present(self) -> None:
        """edges_by_kind must be present when edges table has a kind column."""
        rows = [("ClassA", "class", "python")]
        conn = _make_conn_with_symbols(rows)
        _add_edges(conn, [("A", "calls"), ("B", "calls"), ("C", "imports")])
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        assert "edges_by_kind" in stats, (
            "edges_by_kind must be present when edges.kind column exists"
        )
        assert isinstance(stats["edges_by_kind"], dict)
        assert stats["edges_by_kind"].get("calls") == 2
        assert stats["edges_by_kind"].get("imports") == 1

    def test_total_edges_reconciles_with_edges_by_kind(self) -> None:
        """Codex P2 #315: total_edges must equal sum(edges_by_kind) — it counts
        ALL edge kinds, not only call edges, so the status reads as a coherent
        all-edge summary."""
        rows = [("ClassA", "class", "python")]
        conn = _make_conn_with_symbols(rows)
        _add_edges(
            conn,
            [("A", "calls"), ("B", "calls"), ("C", "imports"), ("D", "contains")],
        )
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        assert "total_edges" in stats, "total_edges must be present"
        assert stats["total_edges"] == 4
        assert stats["total_edges"] == sum(stats["edges_by_kind"].values()), (
            "total_edges must equal the sum of the edges_by_kind breakdown"
        )

    def test_total_edges_zero_when_edges_table_absent(self) -> None:
        """total_edges degrades to 0 (not raising) when the edges table is gone."""
        conn = _make_conn_with_symbols([("ClassA", "class", "python")])
        conn.execute("DROP TABLE edges")
        conn.commit()
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        assert stats.get("total_edges") == 0

    def test_edges_by_kind_empty_dict_when_edges_table_absent(self) -> None:
        """If edges table is absent, edges_by_kind degrades to {}."""
        conn = _make_conn_with_symbols([("ClassA", "class", "python")])
        conn.execute("DROP TABLE edges")
        conn.commit()
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        assert stats.get("edges_by_kind") == {}

    def test_all_three_breakdown_keys_present(self) -> None:
        """The stats dict must include symbols_by_kind, symbols_by_language, edges_by_kind."""
        rows = [("ClassA", "class", "python"), ("func_b", "function", "go")]
        conn = _make_conn_with_symbols(rows)
        _add_edges(conn, [("A", "calls")])
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        required = {"symbols_by_kind", "symbols_by_language", "edges_by_kind"}
        missing = required - set(stats.keys())
        assert not missing, f"get_stats() is missing required breakdown keys: {missing}"


# ---------------------------------------------------------------------------
# Tests for the MCP ast_cache mode=stats surface
# ---------------------------------------------------------------------------


class TestASTCacheToolStatsBreakdowns:
    """Verify ast_cache mode=stats surfaces the new breakdown keys."""

    @pytest.mark.asyncio
    async def test_handle_stats_surfaces_symbols_by_kind(self, tmp_path: Any) -> None:
        """_handle_stats must pass symbols_by_kind through to the envelope."""
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(project_root=str(tmp_path))
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 3,
            "total_symbols": 5,
            "fts5_available": True,
            "by_language": {"python": 2},
            "symbols_by_kind": {"class": 2, "function": 3},
            "symbols_by_language": {"python": 5},
            "edges_by_kind": {"calls": 10},
        }
        tool._cache = mock_cache  # noqa: SLF001

        result = await tool.execute({"mode": "stats"})
        assert result["success"] is True
        assert "symbols_by_kind" in result, (
            "ast_cache mode=stats envelope must contain symbols_by_kind"
        )
        assert result["symbols_by_kind"] == {"class": 2, "function": 3}

    @pytest.mark.asyncio
    async def test_handle_stats_surfaces_symbols_by_language(
        self, tmp_path: Any
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(project_root=str(tmp_path))
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 3,
            "total_symbols": 5,
            "fts5_available": True,
            "by_language": {"python": 2},
            "symbols_by_kind": {"class": 2, "function": 3},
            "symbols_by_language": {"python": 4, "javascript": 1},
            "edges_by_kind": {},
        }
        tool._cache = mock_cache  # noqa: SLF001

        result = await tool.execute({"mode": "stats"})
        assert "symbols_by_language" in result, (
            "ast_cache mode=stats envelope must contain symbols_by_language"
        )
        assert result["symbols_by_language"] == {"python": 4, "javascript": 1}

    @pytest.mark.asyncio
    async def test_handle_stats_surfaces_edges_by_kind(self, tmp_path: Any) -> None:
        from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool

        tool = ASTCacheTool(project_root=str(tmp_path))
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 3,
            "total_symbols": 5,
            "fts5_available": True,
            "by_language": {},
            "symbols_by_kind": {},
            "symbols_by_language": {},
            "edges_by_kind": {"calls": 42, "imports": 7},
        }
        tool._cache = mock_cache  # noqa: SLF001

        result = await tool.execute({"mode": "stats"})
        assert "edges_by_kind" in result, (
            "ast_cache mode=stats envelope must contain edges_by_kind"
        )
        assert result["edges_by_kind"] == {"calls": 42, "imports": 7}


# ---------------------------------------------------------------------------
# Tests for CodeGraphStatusTool surface
# ---------------------------------------------------------------------------


class TestCodeGraphStatusBreakdowns:
    """Verify codegraph_status exposes the new breakdown keys."""

    @pytest.mark.asyncio
    async def test_codegraph_status_surfaces_symbols_by_kind(
        self, tmp_path: Any
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
            CodeGraphStatusTool,
        )

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"fake-sqlite")

        tool = CodeGraphStatusTool(str(tmp_path))
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 5,
            "total_symbols": 10,
            "fts5_available": True,
            "schema_version": 3,
            "symbols_by_kind": {"class": 4, "function": 6},
            "symbols_by_language": {"python": 8, "javascript": 2},
            "edges_by_kind": {"calls": 20},
        }
        mock_cache.get_cross_file_stats.return_value = {"total": 20}

        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            return_value=mock_cache,
        ):
            result = await tool.execute({"output_format": "json", "include_lag": False})

        assert result["verdict"] == "INFO"
        assert "symbols_by_kind" in result, (
            "codegraph_status must surface symbols_by_kind"
        )
        assert result["symbols_by_kind"] == {"class": 4, "function": 6}

    @pytest.mark.asyncio
    async def test_codegraph_status_surfaces_symbols_by_language(
        self, tmp_path: Any
    ) -> None:
        from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
            CodeGraphStatusTool,
        )

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"fake-sqlite")

        tool = CodeGraphStatusTool(str(tmp_path))
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 5,
            "total_symbols": 10,
            "fts5_available": True,
            "schema_version": 3,
            "symbols_by_kind": {"class": 4, "function": 6},
            "symbols_by_language": {"python": 8, "go": 2},
            "edges_by_kind": {},
        }
        mock_cache.get_cross_file_stats.return_value = {"total": 0}

        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            return_value=mock_cache,
        ):
            result = await tool.execute({"output_format": "json", "include_lag": False})

        assert "symbols_by_language" in result, (
            "codegraph_status must surface symbols_by_language"
        )
        assert result["symbols_by_language"] == {"python": 8, "go": 2}

    @pytest.mark.asyncio
    async def test_codegraph_status_surfaces_edges_by_kind(self, tmp_path: Any) -> None:
        from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import (
            CodeGraphStatusTool,
        )

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"fake-sqlite")

        tool = CodeGraphStatusTool(str(tmp_path))
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_files": 5,
            "total_symbols": 10,
            "fts5_available": True,
            "schema_version": 3,
            "symbols_by_kind": {},
            "symbols_by_language": {},
            "edges_by_kind": {"calls": 15, "imports": 5},
        }
        mock_cache.get_cross_file_stats.return_value = {"total": 20}

        with patch(
            "tree_sitter_analyzer.ast_cache.ASTCache",
            return_value=mock_cache,
        ):
            result = await tool.execute({"output_format": "json", "include_lag": False})

        assert "edges_by_kind" in result, "codegraph_status must surface edges_by_kind"
        assert result["edges_by_kind"] == {"calls": 15, "imports": 5}


# ---------------------------------------------------------------------------
# CLI / MCP parity test
# ---------------------------------------------------------------------------


class TestCLIMCPParity:
    """--codegraph-status CLI flag must still route to CodeGraphStatusTool."""

    def test_codegraph_status_flag_registered_in_extended_specs(self) -> None:
        # The tuple is private (_EXTENDED_SPECS) but is the canonical source
        # for codegraph_status routing.  We verify the flag is still present.
        from tree_sitter_analyzer.cli.commands.mcp_commands._specs_extended import (
            _EXTENDED_SPECS,
        )

        flag_names = [spec.flag_name for spec in _EXTENDED_SPECS]
        assert "codegraph_status" in flag_names, (
            "--codegraph-status must remain registered in _EXTENDED_SPECS"
        )

    def test_get_stats_breakdown_keys_superset_check(self) -> None:
        """get_stats() must include the three breakdown keys (integration check)."""
        rows = [
            ("ClassA", "class", "python"),
            ("func_b", "function", "go"),
        ]
        conn = _make_conn_with_symbols(rows)
        _add_edges(conn, [("A", "calls")])
        stats = get_stats(conn, fts5_available=True, db_path=":memory:")
        required = {"symbols_by_kind", "symbols_by_language", "edges_by_kind"}
        missing = required - set(stats.keys())
        assert not missing, f"get_stats() is missing required breakdown keys: {missing}"
