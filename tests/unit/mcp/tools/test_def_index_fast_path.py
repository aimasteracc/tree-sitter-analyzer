"""``_build_def_index`` fast path: indexed ``ast_symbol_rows`` lookup.

The body inliner resolves a symbol's line span via ``_build_def_index``. The
indexed lookup against ``ast_symbol_rows`` (``name`` is indexed) replaces a full
``ast_index`` scan + per-file JSON parse (~28 ms/call -> ~0.03 ms). When
``ast_symbol_rows`` is absent (no-FTS5 build / fixtures), it falls back to the
JSON scan so behaviour is preserved.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.call_path_enrich import _build_def_index


def _cache(db: sqlite3.Connection) -> MagicMock:
    cache = MagicMock()
    cache.get_conn.return_value = db
    return cache


def test_indexed_path_returns_spans_from_symbol_rows() -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE ast_symbol_rows "
        "(name TEXT, kind TEXT, file_path TEXT, language TEXT, line INT, end_line INT)"
    )
    db.executemany(
        "INSERT INTO ast_symbol_rows VALUES (?,?,?,?,?,?)",
        [
            ("foo", "function", "a.py", "python", 5, 12),
            ("foo", "method", "b.py", "python", 3, 9),
            ("bar", "class", "c.py", "python", 1, 2),  # class kind is not a def
            ("baz", "function", "d.js", "javascript", 7, 7),
        ],
    )
    db.commit()
    index = _build_def_index(_cache(db), {"foo", "bar", "baz"})
    assert sorted((d["file"], d["line"], d["end_line"]) for d in index["foo"]) == [
        ("a.py", 5, 12),
        ("b.py", 3, 9),
    ]
    assert index["foo"][0]["language"] in ("python",)
    assert "bar" not in index  # class is not a function/method def target
    assert index["baz"][0]["file"] == "d.js"


def test_falls_back_to_scan_when_symbol_rows_absent() -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
    )
    db.execute(
        "INSERT INTO ast_index VALUES (?,?,?)",
        (
            "a.py",
            "python",
            json.dumps(
                {
                    "symbols": [
                        {"name": "foo", "kind": "function", "line": 5, "end_line": 12}
                    ]
                }
            ),
        ),
    )
    db.commit()
    # No ast_symbol_rows table → the indexed query raises → scan fallback.
    index = _build_def_index(_cache(db), {"foo"})
    assert index["foo"][0]["file"] == "a.py"
    assert index["foo"][0]["end_line"] == 12


def test_empty_names_returns_empty() -> None:
    assert _build_def_index(MagicMock(), set()) == {}


def test_falls_back_to_scan_when_symbol_rows_exist_but_empty_for_requested_names() -> (
    None
):
    """ast_symbol_rows exists but has no rows for the requested names.

    This happens with existing .ast-cache databases after the FTS table is
    introduced: unchanged files are not rewritten into ast_symbol_rows, so the
    indexed query succeeds with zero rows. The fallback must scan ast_index for
    the missing names instead of returning an empty body index.
    """
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    # ast_symbol_rows exists but is empty (simulates a cache built before the FTS backfill).
    db.execute(
        "CREATE TABLE ast_symbol_rows "
        "(name TEXT, kind TEXT, file_path TEXT, language TEXT, line INT, end_line INT)"
    )
    db.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
    )
    db.execute(
        "INSERT INTO ast_index VALUES (?,?,?)",
        (
            "a.py",
            "python",
            json.dumps(
                {
                    "symbols": [
                        {"name": "foo", "kind": "function", "line": 5, "end_line": 12}
                    ]
                }
            ),
        ),
    )
    db.commit()
    # ast_symbol_rows has no row for "foo" → must fall back to ast_index scan.
    index = _build_def_index(_cache(db), {"foo"})
    assert "foo" in index, (
        "fallback scan must find foo even when ast_symbol_rows is empty"
    )
    assert index["foo"][0]["file"] == "a.py"
    assert index["foo"][0]["end_line"] == 12
