"""Tests for AST cache SQLite storage maintenance (#579)."""

from __future__ import annotations

import sqlite3
from typing import Any

from tree_sitter_analyzer.cache.maintenance import (
    get_db_storage_stats,
    reclaim_storage_after_full_rebuild,
)
from tree_sitter_analyzer.ast_cache import ASTCache


class _Row:
    def __init__(self, value: int) -> None:
        self._value = value

    def __getitem__(self, index: int) -> int:
        assert index == 0
        return self._value


class _Cursor:
    def __init__(self, value: int) -> None:
        self._value = value

    def fetchone(self) -> _Row:
        return _Row(self._value)


class _FakeConn:
    def __init__(self, *, free_pages: int, auto_vacuum: int) -> None:
        self.commands: list[str] = []
        self.commits = 0
        self.free_pages = free_pages
        self.auto_vacuum = auto_vacuum

    def execute(self, sql: str) -> _Cursor:
        self.commands.append(sql)
        if sql == "PRAGMA page_size":
            return _Cursor(4096)
        if sql == "PRAGMA page_count":
            return _Cursor(11)
        if sql == "PRAGMA freelist_count":
            return _Cursor(self.free_pages)
        if sql == "PRAGMA auto_vacuum":
            return _Cursor(self.auto_vacuum)
        if sql == "PRAGMA auto_vacuum=INCREMENTAL":
            self.auto_vacuum = 2
            return _Cursor(0)
        if sql == "VACUUM":
            self.free_pages = 0
            return _Cursor(0)
        if sql == "PRAGMA incremental_vacuum(8)":
            self.free_pages = 0
            return _Cursor(0)
        raise AssertionError(f"unexpected SQL: {sql}")

    def commit(self) -> None:
        self.commits += 1


def test_get_db_storage_stats_reports_exact_page_counters() -> None:
    conn = _FakeConn(free_pages=3, auto_vacuum=0)

    stats = get_db_storage_stats(conn, "/missing/index.db")  # type: ignore[arg-type]

    assert stats == {
        "db_path": "/missing/index.db",
        "db_size_bytes": 45056,
        "db_page_size": 4096,
        "db_page_count": 11,
        "db_free_pages": 3,
        "db_free_bytes": 12288,
        "db_auto_vacuum_mode": 0,
    }


def test_reclaim_storage_skips_when_free_pages_are_below_threshold() -> None:
    conn = _FakeConn(free_pages=4, auto_vacuum=0)

    result = reclaim_storage_after_full_rebuild(  # type: ignore[arg-type]
        conn, "/missing/index.db", min_free_pages=5
    )

    assert result["action"] == "skipped"
    assert result["reason"] == "below_threshold"
    assert result["before"]["db_free_pages"] == 4
    assert result["after"]["db_free_pages"] == 4
    assert conn.commits == 0
    assert conn.commands == [
        "PRAGMA page_size",
        "PRAGMA page_count",
        "PRAGMA freelist_count",
        "PRAGMA auto_vacuum",
    ]


def test_reclaim_storage_vacuums_legacy_auto_vacuum_none_db() -> None:
    conn = _FakeConn(free_pages=8, auto_vacuum=0)

    result = reclaim_storage_after_full_rebuild(  # type: ignore[arg-type]
        conn, "/missing/index.db", min_free_pages=5
    )

    assert result["action"] == "enable_incremental_vacuum"
    assert result["before"]["db_free_pages"] == 8
    assert result["before"]["db_auto_vacuum_mode"] == 0
    assert result["after"]["db_free_pages"] == 0
    assert result["after"]["db_auto_vacuum_mode"] == 2
    assert conn.commits == 2
    assert "PRAGMA auto_vacuum=INCREMENTAL" in conn.commands
    assert "VACUUM" in conn.commands


def test_reclaim_storage_uses_incremental_vacuum_when_enabled() -> None:
    conn = _FakeConn(free_pages=8, auto_vacuum=2)

    result = reclaim_storage_after_full_rebuild(  # type: ignore[arg-type]
        conn, "/missing/index.db", min_free_pages=5
    )

    assert result["action"] == "incremental_vacuum"
    assert result["before"]["db_free_pages"] == 8
    assert result["after"]["db_free_pages"] == 0
    assert conn.commits == 2
    assert "PRAGMA incremental_vacuum(8)" in conn.commands


class _BrokenConn(_FakeConn):
    def execute(self, sql: str) -> _Cursor:
        if sql == "VACUUM":
            raise sqlite3.DatabaseError("disk is busy")
        return super().execute(sql)


def test_reclaim_storage_reports_errors_without_raising() -> None:
    conn = _BrokenConn(free_pages=8, auto_vacuum=0)

    result = reclaim_storage_after_full_rebuild(  # type: ignore[arg-type]
        conn, "/missing/index.db", min_free_pages=5
    )

    assert result["action"] == "error"
    assert result["error"] == "disk is busy"
    assert result["before"]["db_free_pages"] == 8
    assert result["after"]["db_free_pages"] == 8


def test_index_project_force_includes_db_maintenance(tmp_path, monkeypatch) -> None:
    import tree_sitter_analyzer.ast_cache as ast_cache_mod

    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(workers=0)
        observed: dict[str, Any] = {}

        def _fake_reclaim(conn, db_path):
            observed["db_path"] = db_path
            return {"action": "skipped", "reason": "below_threshold"}

        monkeypatch.setattr(
            ast_cache_mod, "_reclaim_storage_after_full_rebuild", _fake_reclaim
        )

        result = cache.index_project(force=True, workers=0)

        assert result["indexed"] == 1
        assert result["db_maintenance"] == {
            "action": "skipped",
            "reason": "below_threshold",
        }
        assert observed["db_path"] == cache.db_path
    finally:
        cache.close()
