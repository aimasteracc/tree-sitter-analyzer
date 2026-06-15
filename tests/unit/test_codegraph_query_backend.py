"""Contracts for the shared CodeGraph query backend."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.codegraph_query_backend import CodeGraphQueryBackend


class RowCache:
    _fts5_available = False
    fts5_available = False

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_conn(self) -> sqlite3.Connection:
        return self.conn

    def _get_conn(self) -> sqlite3.Connection:  # backward-compat alias
        return self.get_conn()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_backend_resolves_definitions_without_symbol_resolver() -> None:
    conn = _connect()
    conn.execute(
        """CREATE TABLE ast_symbol_rows (
            name TEXT,
            kind TEXT,
            file_path TEXT,
            language TEXT,
            line INTEGER,
            end_line INTEGER
        )"""
    )
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES (?, ?, ?, ?, ?, ?)",
        ("run", "function", "main.py", "python", 3, 5),
    )
    backend = CodeGraphQueryBackend(RowCache(conn))

    with patch("tree_sitter_analyzer.symbol_resolver.SymbolResolver") as resolver_cls:
        resolver_cls.side_effect = AssertionError("backend must not use SymbolResolver")
        results = backend.resolve_definitions("run")

    assert results == [
        {
            "file": "main.py",
            "name": "run",
            "kind": "function",
            "line": 3,
            "end_line": 5,
            "language": "python",
            "confidence": 1.0,
        }
    ]


def test_backend_prefers_fts_definition_rows() -> None:
    cache = MagicMock()
    cache._fts5_available = True
    # G6: _fts_definitions now uses fts_search_ranked; rows carry relevance_score.
    cache.fts_search_ranked.return_value = [
        {
            "name": "run",
            "kind": "reference",
            "file": "ref.py",
            "line": 1,
            "relevance_score": 0.8,
        },
        {
            "name": "run",
            "kind": "function",
            "file": "main.py",
            "line": 3,
            "end_line": 4,
            "language": "python",
            "relevance_score": 1.0,
        },
    ]
    backend = CodeGraphQueryBackend(cache)

    results = backend.resolve_definitions("run")

    assert [item["file"] for item in results] == ["main.py"]
    assert results[0]["confidence"] == pytest.approx(1.0)
    cache.fts_search_ranked.assert_called_once_with("run", limit=50)


def test_backend_falls_back_to_symbols_json() -> None:
    conn = _connect()
    conn.execute(
        """CREATE TABLE ast_index (
            file_path TEXT,
            symbols_json TEXT,
            language TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, ?)",
        (
            "main.py",
            json.dumps(
                {
                    "symbols": [
                        {"name": "ignored", "kind": "function", "line": 1},
                        {
                            "name": "run",
                            "kind": "method",
                            "line": 7,
                            "end_line": 9,
                        },
                    ]
                }
            ),
            "python",
        ),
    )
    backend = CodeGraphQueryBackend(RowCache(conn))

    results = backend.resolve_definitions("run")

    assert results == [
        {
            "file": "main.py",
            "name": "run",
            "kind": "method",
            "line": 7,
            "end_line": 9,
            "language": "python",
            "confidence": 0.9,
        }
    ]


def test_backend_semantic_symbols_rank_token_vector_matches() -> None:
    conn = _connect()
    conn.execute(
        """CREATE TABLE ast_symbol_rows (
            name TEXT,
            kind TEXT,
            file_path TEXT,
            language TEXT,
            line INTEGER,
            end_line INTEGER
        )"""
    )
    conn.executemany(
        "INSERT INTO ast_symbol_rows VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("format_user", "function", "utils.py", "python", 1, 3),
            ("delete_session", "function", "auth.py", "python", 5, 8),
        ],
    )
    backend = CodeGraphQueryBackend(RowCache(conn))

    results = backend.semantic_symbols("user formatting", limit=3)

    assert results[0]["name"] == "format_user"
    assert results[0]["semantic_score"] > 0


def test_backend_semantic_symbols_maps_semantic_score_to_confidence() -> None:
    """semantic_symbols must populate 'confidence' from semantic_score.

    This ensures sort(by='confidence') in the DSL works on semantic()
    results the same way it works on search/explore results.
    """
    conn = _connect()
    conn.execute(
        """CREATE TABLE ast_symbol_rows (
            name TEXT,
            kind TEXT,
            file_path TEXT,
            language TEXT,
            line INTEGER,
            end_line INTEGER
        )"""
    )
    conn.executemany(
        "INSERT INTO ast_symbol_rows VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("handle_request", "function", "server.py", "python", 1, 3),
            ("validate", "function", "util.py", "python", 5, 8),
        ],
    )
    backend = CodeGraphQueryBackend(RowCache(conn))

    results = backend.semantic_symbols("handle request", limit=3)

    assert len(results) >= 1
    for r in results:
        assert "confidence" in r, (
            "semantic_symbols must map semantic_score → confidence"
        )
        assert r["confidence"] == r["semantic_score"]


def test_backend_normalizes_callers_and_callees_from_cache_rows() -> None:
    cache = MagicMock()
    cache.query_callers.return_value = [
        {"caller_name": "entry", "caller_file": "main.py", "caller_line": 3},
        {"caller_name": "", "caller_file": "ignored.py", "caller_line": 1},
    ]
    cache.query_callees.return_value = [
        {"callee_name": "helper", "callee_file": "main.py", "callee_line": 5}
    ]
    backend = CodeGraphQueryBackend(cache)

    assert backend.relation_entries(
        direction="callers",
        name="run",
        file_path="main.py",
        depth=2,
        limit=10,
    ) == [
        {
            "name": "entry",
            "file": "main.py",
            "line": 3,
            "end_line": 3,
            "kind": "function",
            "language": "",
            "depth": None,
        }
    ]
    assert (
        backend.relation_entries(
            direction="callees",
            name="run",
            file_path="main.py",
            depth=1,
            limit=10,
        )[0]["name"]
        == "helper"
    )
    cache.query_callers.assert_called_once_with("run", "main.py", max_depth=2)
    cache.query_callees.assert_called_once_with("run", "main.py", max_depth=1)


def test_backend_resolves_enum_as_definition() -> None:
    """#961 split: ``enum`` rows are definition sites (added to kind filter)."""
    conn = _connect()
    conn.execute(
        """CREATE TABLE ast_symbol_rows (
            name TEXT,
            kind TEXT,
            file_path TEXT,
            language TEXT,
            line INTEGER,
            end_line INTEGER
        )"""
    )
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES (?, ?, ?, ?, ?, ?)",
        ("Color", "enum", "colors.rs", "rust", 4, 9),
    )
    backend = CodeGraphQueryBackend(RowCache(conn))

    results = backend.resolve_definitions("Color")

    assert results == [
        {
            "file": "colors.rs",
            "name": "Color",
            "kind": "enum",
            "line": 4,
            "end_line": 9,
            "language": "rust",
            "confidence": 1.0,
        }
    ]
