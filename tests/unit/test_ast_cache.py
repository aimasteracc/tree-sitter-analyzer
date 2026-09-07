"""#1376：test_ast_cache 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import sqlite3
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import patch

import pytest

import tests.unit._ast_cache_helpers as _fixtures
import tree_sitter_analyzer.ast_cache as ast_cache_module
from tree_sitter_analyzer.ast_cache import (
    _AST_CACHE_EXTRACTOR_VERSION,
    _EXT_TO_LANG,
    ASTCache,
    _content_hash,
    _extract_symbols,
    _has_fts5,
)
from tree_sitter_analyzer.core.parser import Parser

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


class TestContentHash:
    def test_deterministic(self):
        assert _content_hash("hello") == _content_hash("hello")

    def test_different_content(self):
        assert _content_hash("hello") != _content_hash("world")

    def test_bytes_input(self):
        assert _content_hash(b"hello") == _content_hash("hello")


def test_check_cache_read_reports_source_open_error(tmp_path):
    # PR #1253: 不可读的过期源码必须返回精确的逐文件归因。
    from tree_sitter_analyzer.cache.indexer import check_cache_or_read

    cache = ASTCache(str(tmp_path))
    try:
        with patch("builtins.open", side_effect=OSError("read denied")):
            result = check_cache_or_read(
                cache.get_conn(),
                "missing.py",
                str(tmp_path / "missing.py"),
                SimpleNamespace(st_mtime_ns=1, st_size=2),
                lambda source: source,
                _AST_CACHE_EXTRACTOR_VERSION,
            )
    finally:
        cache.close()

    assert result == {
        "file": "missing.py",
        "status": "error",
        "reason": "read denied",
    }


def test_facade_fts_hook_controls_schema_initialization(tmp_project, monkeypatch):
    """实现拆分之后，保留的 facade hook 必须仍生效。"""
    # PR #1187 Codex review (2026-07-27): 复制的绑定曾忽略 monkeypatch。
    monkeypatch.setattr(ast_cache_module, "_has_fts5", lambda _conn: False)

    cache = ASTCache(str(tmp_project), str(tmp_project / "no-fts.db"))

    assert cache.fts5_available is False
    cache.close()


def test_parser_property_type_hint_resolves_at_runtime() -> None:
    """运行时 API 内省必须能够解析公开的 parser 类型注解。"""
    # PR #1187 Codex review (2026-07-27): TYPE_CHECKING 曾在运行时隐藏 Parser。
    assert get_type_hints(ASTCache.parser.fget)["return"] is Parser


def test_symbol_query_propagates_connection_acquisition_failures(monkeypatch) -> None:
    """数据库不可用不能伪装成空的旧版表。"""
    # PR #1187 Codex review (2026-07-27): 只有旧版查询采用尽力而为策略。
    cache = ASTCache.__new__(ASTCache)

    def fail_connection():
        raise sqlite3.OperationalError("database unavailable")

    monkeypatch.setattr(cache, "_get_conn", fail_connection)

    with pytest.raises(sqlite3.OperationalError, match="database unavailable"):
        cache.get_symbols_by_kind("class")


class TestIndexFile:
    def test_index_python_file(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        result = cache.index_file(f)
        assert result["status"] == "indexed"
        assert result["symbols"] == 2

    def test_index_unsupported_language(self, cache, tmp_project):
        f = str(tmp_project / "readme.md")
        result = cache.index_file(f)
        assert result["status"] == "skipped"

    def test_index_nonexistent_file(self, cache, tmp_project):
        f = str(tmp_project / "nonexistent.py")
        result = cache.index_file(f)
        assert result["status"] == "error"

    def test_cached_on_second_index(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        result = cache.index_file(f)
        assert result["status"] == "cached"

    def test_content_unchanged_refreshes_file_metadata(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        conn = cache._get_conn()
        conn.execute(
            "UPDATE ast_index SET mtime_ns = 0 WHERE file_path = ?", ("src/main.py",)
        )
        conn.commit()

        result = cache.index_file(f)

        assert result == {
            "file": "src/main.py",
            "status": "cached",
            "reason": "content unchanged",
        }

    def test_stale_extractor_version_reindexes_unchanged_file(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        conn = cache._get_conn()
        conn.execute("UPDATE ast_index SET extractor_version = 0")
        conn.commit()

        result = cache.index_file(f)

        assert result["status"] == "indexed"
        version = conn.execute(
            "SELECT extractor_version FROM ast_index WHERE file_path = ?",
            ("src/main.py",),
        ).fetchone()[0]
        assert version == _AST_CACHE_EXTRACTOR_VERSION

    def test_init_migrates_legacy_index_without_extractor_version(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                language TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                file_size INTEGER NOT NULL,
                symbols_json TEXT NOT NULL DEFAULT '{}',
                imports_json TEXT NOT NULL DEFAULT '[]',
                structure_json TEXT NOT NULL DEFAULT '{}',
                indexed_at TEXT NOT NULL,
                PRIMARY KEY (file_path)
            )"""
        )
        conn.commit()
        conn.close()

        migrated = ASTCache(str(tmp_path), db_path=str(db_path))
        try:
            columns = {
                row[1]
                for row in migrated._get_conn()
                .execute("PRAGMA table_info(ast_index)")
                .fetchall()
            }
            version_row = (
                migrated._get_conn()
                .execute("SELECT version FROM ast_schema_version WHERE version = 7")
                .fetchone()
            )

            assert "extractor_version" in columns
            assert version_row is not None
        finally:
            migrated.close()

    def test_init_reports_migration_metadata_failure_and_closes_connection(
        self, tmp_path, monkeypatch
    ):
        # PR #1350：使用真实 SQLite connection 的故障边界，不绕过 schema 校验器。
        class FlakyConnection(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if "PRAGMA table_info(ast_index)" in sql:
                    raise sqlite3.OperationalError("metadata temporarily unavailable")
                return super().execute(sql, *args, **kwargs)

        connect = sqlite3.connect
        opened = []

        def connect_with_failure(*args, **kwargs):
            conn = connect(*args, **kwargs, factory=FlakyConnection)
            opened.append(conn)
            return conn

        monkeypatch.setattr(sqlite3, "connect", connect_with_failure)
        try:
            with pytest.raises(
                sqlite3.OperationalError, match="metadata temporarily unavailable"
            ):
                ASTCache(str(tmp_path), db_path=str(tmp_path / "flaky.db"))
            assert len(opened) == 1
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                opened[0].execute("SELECT 1")
        finally:
            for conn in opened:
                conn.close()

    def test_index_with_explicit_language(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        result = cache.index_file(f, language="python")
        assert result["status"] == "indexed"


class TestLookup:
    def test_lookup_indexed_file(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        result = cache.lookup(f)
        assert result is not None
        assert result["language"] == "python"
        assert "symbols" in result
        assert "structure" in result

    def test_lookup_missing_file(self, cache):
        result = cache.lookup("/nonexistent/file.py")
        assert result is None


class TestStats:
    def test_stats_empty(self, cache):
        stats = cache.get_stats()
        assert stats["total_files"] == 0
        assert stats["total_symbols"] == 0

    def test_stats_after_index(self, cache):
        cache.index_project()
        stats = cache.get_stats()
        assert stats["total_files"] == 2
        assert stats["total_symbols"] == 3
        assert "python" in stats["by_language"]

    def test_stats_uses_symbol_rows_when_fts_available(self, cache):
        cache.index_project()
        if not cache.fts5_available:
            pytest.skip("FTS5 not available")

        with patch(
            "tree_sitter_analyzer.ast_cache.json.loads",
            side_effect=AssertionError("get_stats should not scan symbols_json"),
        ):
            stats = cache.get_stats()

        assert stats["total_symbols"] == stats["fts_indexed_symbols"]
        assert stats["total_symbols"] == 3

    def test_stats_falls_back_to_symbols_json_without_fts(self, cache):
        cache.index_project()
        cache._fts5_available = False  # 强制使用非 FTS5 路径进行测试。

        stats = cache.get_stats()

        assert stats["total_symbols"] == 3
        assert stats["fts5_available"] is False

    def test_stats_falls_back_when_symbol_rows_table_missing(self, cache):
        cache.index_project()
        if not cache.fts5_available:
            pytest.skip("FTS5 not available")

        conn = cache._get_conn()
        conn.execute("DROP TABLE ast_symbol_rows")

        stats = cache.get_stats()

        assert stats["total_symbols"] == 3

    def test_clear_activation_for_file_ignores_missing_table(self, cache):
        conn = sqlite3.connect(":memory:")

        ASTCache._clear_activation_for_file(conn, "src/main.py")

        conn.close()


class TestInvalidate:
    def test_invalidate_existing(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        assert cache.invalidate(f) is True
        assert cache.lookup(f) is None

    def test_invalidate_nonexistent(self, cache):
        assert cache.invalidate("/nonexistent.py") is False


class TestExtractSymbols:
    def test_extract_from_none_tree(self):
        result = _extract_symbols(None, "x = 1", "python")
        assert result["symbols"] == []
        assert result["node_count"] == 0


class TestExtToLang:
    def test_common_extensions(self):
        assert _EXT_TO_LANG[".py"] == "python"
        assert _EXT_TO_LANG[".js"] == "javascript"
        assert _EXT_TO_LANG[".ts"] == "typescript"
        assert _EXT_TO_LANG[".java"] == "java"
        assert _EXT_TO_LANG[".go"] == "go"
        assert _EXT_TO_LANG[".c"] == "c"
        assert _EXT_TO_LANG[".cpp"] == "cpp"


class TestDbPersistence:
    def test_cache_persists_across_instances(self, tmp_project):
        c1 = ASTCache(str(tmp_project))
        f = str(tmp_project / "src" / "main.py")
        c1.index_file(f)
        stats1 = c1.get_stats()
        c1.close()

        c2 = ASTCache(str(tmp_project), db_path=c1.db_path)
        stats2 = c2.get_stats()
        assert stats2["total_files"] == stats1["total_files"]
        c2.close()


class TestHasFts5:
    def test_detects_fts5(self):
        conn = sqlite3.connect(":memory:")
        result = _has_fts5(conn)
        conn.close()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# ASTCache.get_conn() 公共访问器，以 TDD 替换私有 _get_conn 用法。
# ---------------------------------------------------------------------------


class TestASTCacheGetConnPublicAccessor:
    """get_conn() 必须暴露与 _get_conn() 相同的 SQLite 连接。"""

    def test_get_conn_returns_sqlite_connection(self, tmp_project):
        """get_conn() 必须返回存活的 sqlite3.Connection，而不是 None。"""
        cache = ASTCache(str(tmp_project))
        conn = cache.get_conn()
        assert isinstance(conn, sqlite3.Connection)

    def test_get_conn_same_as_private_get_conn(self, tmp_project):
        """get_conn() 和 _get_conn() 必须返回同一个连接对象。"""
        cache = ASTCache(str(tmp_project))
        assert cache.get_conn() is cache._get_conn()

    def test_get_conn_thread_local_stable(self, tmp_project):
        """同一线程中重复调用 get_conn() 必须返回同一个对象。"""
        cache = ASTCache(str(tmp_project))
        conn1 = cache.get_conn()
        conn2 = cache.get_conn()
        assert conn1 is conn2
