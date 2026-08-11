"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

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

    def test_legacy_symbol_migration_row_budget_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.cache.schema as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_ROW_BUDGET", 0)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema._ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_input_budget_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.cache.schema as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_INPUT_BYTE_BUDGET", 1)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema._ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_cell_budget_precedes_json(self, monkeypatch):
        import tree_sitter_analyzer.cache.schema as schema

        conn = self._legacy_symbol_connection("not-json")
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_CELL_BYTE_BUDGET", 1)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema._ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_symbol_budget_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.cache.schema as schema

        conn = self._legacy_symbol_connection('{"symbols": [{"name": "x"}]}')
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_SYMBOL_BUDGET", 0)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema._ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_deadline_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.cache.schema as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_SECONDS", -1.0)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema._ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_byte_cell_budget_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.cache.schema as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        conn.execute("UPDATE ast_index SET symbols_json = ?", (b"{}",))
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_CELL_BYTE_BUDGET", 1)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema._ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_rejects_non_text_cell(self):
        import tree_sitter_analyzer.cache.schema as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        conn.execute("UPDATE ast_index SET symbols_json = NULL")
        with pytest.raises(ValueError, match="^invalid legacy symbols_json$"):
            schema._ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_zero_symbol_migration_writes_global_marker_and_does_not_reparse(
        self, monkeypatch
    ):
        # PR #1253 review thread 3888: empty projections still complete migration.
        import tree_sitter_analyzer.cache.schema as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        schema._ensure_symbol_rows_backfilled(conn)
        marker = conn.execute(
            "SELECT value FROM ast_cache_metadata WHERE key = ?",
            (schema._LEGACY_SYMBOL_MIGRATION_MARKER,),
        ).fetchone()
        monkeypatch.setattr(
            schema.json,
            "loads",
            lambda _raw: pytest.fail("completed legacy migration reparsed JSON"),
        )
        schema._ensure_symbol_rows_backfilled(conn)
        conn.close()

        assert marker == ("complete",)
