"""Unit tests for _indexed_source_files_are_complete (REQ-U-403)."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock


def _make_conn(rows: list[tuple[int | None]], has_certified_at: bool = True):
    """Create an in-memory DB with ast_index (optionally including certified_at)."""
    conn = sqlite3.connect(":memory:")
    if has_certified_at:
        conn.execute(
            "CREATE TABLE ast_index (file_path TEXT, certified_at INTEGER)"
        )
        conn.executemany(
            "INSERT INTO ast_index (file_path, certified_at) VALUES (?, ?)",
            rows,
        )
    else:
        conn.execute("CREATE TABLE ast_index (file_path TEXT)")
        conn.executemany(
            "INSERT INTO ast_index (file_path) VALUES (?)",
            [(r[0],) for r in rows],
        )
    conn.commit()
    return conn


def _make_mixin(conn: sqlite3.Connection):
    """Minimal mock that exposes _get_conn returning the given connection."""
    from tree_sitter_analyzer._ast_cache_index_mixin import ASTCacheIndexMixin

    mixin = object.__new__(ASTCacheIndexMixin)
    mixin._get_conn = MagicMock(return_value=conn)  # type: ignore[attr-defined]
    return mixin


class TestIndexedSourceFilesAreComplete:
    """REQ-U-403: three correctness cases + fallback case."""

    def test_empty_table_returns_false(self):
        """Case (a): ast_index is empty → False."""
        conn = _make_conn([])
        mixin = _make_mixin(conn)
        assert mixin._indexed_source_files_are_complete() is False

    def test_all_certified_returns_true(self):
        """Case (b): every row has certified_at IS NOT NULL → True."""
        conn = _make_conn(
            [("src/a.py", 1000), ("src/b.py", 1001)],
            has_certified_at=True,
        )
        mixin = _make_mixin(conn)
        assert mixin._indexed_source_files_are_complete() is True

    def test_one_uncertified_returns_false(self):
        """Case (c): one NULL certified_at → False."""
        conn = _make_conn(
            [("src/a.py", 1000), ("src/b.py", None)],
            has_certified_at=True,
        )
        mixin = _make_mixin(conn)
        assert mixin._indexed_source_files_are_complete() is False

    def test_missing_certified_at_column_returns_false(self):
        """Fallback: certified_at absent (pre-v14 DB) → False (safe degradation)."""
        conn = _make_conn([("src/a.py", None)], has_certified_at=False)
        mixin = _make_mixin(conn)
        assert mixin._indexed_source_files_are_complete() is False
