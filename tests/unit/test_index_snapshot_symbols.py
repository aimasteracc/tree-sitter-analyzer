"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


class TestSnapshotFailureContracts:
    @staticmethod
    def _certified_cache(root):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = root / "sample.py"
        source.write_text("value = 1\n")
        cache = ASTCache(str(root))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(root))
        cache.close()

    @pytest.fixture(autouse=True)
    def _close_registry(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    def test_no_fts_schema_still_creates_ordinary_symbol_rows(self):
        from tree_sitter_analyzer.cache import schema

        conn = sqlite3.connect(":memory:")
        available = schema.init_db(conn, None, lambda _conn: False, [])
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        assert available is False
        assert "ast_symbol_rows" in tables
        assert "ast_symbols_fts" not in tables

    @staticmethod
    def _legacy_symbol_connection(raw_symbols: str) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
        )
        conn.execute(
            "INSERT INTO ast_index VALUES ('a.py', 'python', ?)", (raw_symbols,)
        )
        return conn

    @staticmethod
    def _symbol_table_count(conn: sqlite3.Connection) -> int:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='ast_symbol_rows'"
            ).fetchone()[0]
        )


def test_exact_v12_projection_certification_preserves_all_symbol_references(tmp_path):
    # PR #1253 thread 3756769301: certification must never renumber exact rows.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    source = tmp_path / "app.py"
    source.write_text(
        "def target():\n    return 1\ndef caller():\n    return target()\n"
    )
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ast_symbol_activation "
        "(symbol_id, file_path, computed_at, git_state) VALUES (1, 'app.py', 1, 'clean')"
    )
    before = {
        "rows": [
            tuple(row)
            for row in conn.execute("SELECT id, name FROM ast_symbol_rows ORDER BY id")
        ],
        "fts": [
            tuple(row)
            for row in conn.execute("SELECT rowid FROM ast_symbols_fts ORDER BY rowid")
        ],
        "activation": [
            tuple(row)
            for row in conn.execute(
                "SELECT symbol_id, file_path FROM ast_symbol_activation ORDER BY symbol_id"
            )
        ],
        "callees": [
            tuple(row)
            for row in conn.execute(
                "SELECT callee_symbol_id FROM edges WHERE kind='calls' ORDER BY id"
            )
        ],
    }
    conn.execute("DELETE FROM ast_cache_metadata WHERE key='symbol_rows_projection_v1'")
    conn.execute("DELETE FROM ast_symbol_projection_state")
    conn.commit()

    assert ensure_symbol_rows_backfilled(conn) is True
    after = {
        "rows": [
            tuple(row)
            for row in conn.execute("SELECT id, name FROM ast_symbol_rows ORDER BY id")
        ],
        "fts": [
            tuple(row)
            for row in conn.execute("SELECT rowid FROM ast_symbols_fts ORDER BY rowid")
        ],
        "activation": [
            tuple(row)
            for row in conn.execute(
                "SELECT symbol_id, file_path FROM ast_symbol_activation ORDER BY symbol_id"
            )
        ],
        "callees": [
            tuple(row)
            for row in conn.execute(
                "SELECT callee_symbol_id FROM edges WHERE kind='calls' ORDER BY id"
            )
        ],
    }
    cache.close()

    assert after == before


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
class TestSnapshotProjectionCompleteness:
    @pytest.fixture(autouse=True)
    def _close_snapshot_capabilities(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    @staticmethod
    def _certified_cache(root):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = root / "sample.py"
        source.write_text("def answer():\n    return 42\n")
        cache = ASTCache(str(root))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(root))
        cache.close()

    @pytest.mark.asyncio
    async def test_inexact_symbol_projection_makes_snapshot_partial(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3763655050: completeness includes exact projection.
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        monkeypatch.setattr(owner, "symbol_projection_is_exact", lambda *a, **k: False)

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert (result["completeness"], result["oracle_reason"]) == (
            "partial",
            "SYMBOL_PROJECTION_INCOMPLETE",
        )
