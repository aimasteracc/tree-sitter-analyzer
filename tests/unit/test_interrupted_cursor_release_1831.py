"""#1831：期限在两行之间中断读取时，未读完的语句不得继续锁住索引库。

清单盖戳在期限内逐行读取 ``ast_index``。期限在两行之间到期时抛出的异常，其
traceback 引用持有游标的帧；保留该异常的任何人（pytest 的日志捕获、带
``exc_info`` 的日志记录）都让游标存活。游标的语句未结束，读事务就不结束，
连接关闭后成为僵尸、继续持有锁：私有版本封存时 ``wal_checkpoint`` 或切回回滚
日志一直忙，索引不发布（CI 上 10 s 后 ``published=False``）。
"""

from __future__ import annotations

import sqlite3
import time

import pytest

_SOURCES = {
    "pkg/__init__.py": "from .core import helper\n",
    "pkg/core.py": "def helper(x):\n    return x + 1\n\nhelper(0)\n",
    "app.py": "from pkg.core import helper\n\ndef main():\n    return helper(3)\n",
}


def _deadline_after_first_row(monkeypatch) -> None:
    """让清单读取在第一行之后、读完之前到期（与负载下的真实期限中断相同的位置）。"""
    from tree_sitter_analyzer import _recorded_source_rows as rows

    real = rows._iter_payload_rows

    def first_row_then_deadline(cursor, **kwargs):
        payload = real(cursor, **kwargs)
        yield next(payload)
        raise TimeoutError

    monkeypatch.setattr(rows, "_iter_payload_rows", first_row_then_deadline)


@pytest.mark.asyncio
async def test_certification_deadline_mid_read_still_publishes(tmp_path, monkeypatch):
    from tree_sitter_analyzer.cache import generation_seal
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in _SOURCES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(generation_seal, "SEAL_BUSY_TIMEOUT_S", 0.2)
    _deadline_after_first_row(monkeypatch)

    result = await CodeGraphFullIndexTool(str(tmp_path)).execute({"mode": "full"})

    # 盖戳期限耗尽只让本次发布为未认证（#1684），不是“什么都没发布”。
    assert result["published"] is True, result.get("error")
    assert result.get("manifest_warning") == "INDEX_CERTIFICATION_DEADLINE"


def _wal_index(path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE ast_index (file_path TEXT, content_hash TEXT, language TEXT)"
        )
        conn.executemany(
            "INSERT INTO ast_index VALUES (?, ?, ?)",
            [("a.py", "h1", "python"), ("b.py", "h2", "python")],
        )
        conn.commit()
    finally:
        conn.close()


def test_interrupted_read_leaves_no_lock_while_the_error_is_kept(tmp_path, monkeypatch):
    from tree_sitter_analyzer._recorded_source_rows import read_recorded_source_rows

    database = tmp_path / "index.db"
    _wal_index(database)
    _deadline_after_first_row(monkeypatch)
    reader = sqlite3.connect(database)
    kept: list[BaseException] = []
    try:
        read_recorded_source_rows(
            reader,
            effective_deadline=time.monotonic() + 60,
            monotonic=time.monotonic,
            row_budget=10,
            cell_byte_budget=1024,
            total_byte_budget=4096,
        )
    except TimeoutError as exc:
        kept.append(exc)  # 与日志记录保留 exc_info 相同：traceback 与帧都存活
    finally:
        reader.close()
    assert kept, "the deadline must interrupt the read"

    sealer = sqlite3.connect(database, timeout=0)
    try:
        assert sealer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
        assert sealer.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
    finally:
        sealer.close()


def test_interrupted_schema_validation_leaves_no_lock(tmp_path, monkeypatch):
    from tree_sitter_analyzer import index_snapshot_schema

    database = tmp_path / "index.db"
    conn = sqlite3.connect(database)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE ast_schema_version (version INTEGER)")
    conn.executemany(
        "INSERT INTO ast_schema_version VALUES (?)",
        [(index_snapshot_schema.SNAPSHOT_SCHEMA_VERSION,), (1,)],
    )
    conn.commit()
    conn.close()
    calls = iter(range(1_000))

    def deadline_on_second_row(_deadline: float) -> None:
        if next(calls) == 1:
            raise RuntimeError("INDEX_FINGERPRINT_DEADLINE")

    monkeypatch.setattr(
        index_snapshot_schema, "_check_deadline", deadline_on_second_row
    )
    reader = sqlite3.connect(database)
    kept: list[BaseException] = []
    try:
        index_snapshot_schema.validate_snapshot_schema(reader)
    except RuntimeError as exc:
        kept.append(exc)
    finally:
        reader.close()
    assert kept

    sealer = sqlite3.connect(database, timeout=0)
    try:
        assert sealer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
        assert sealer.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
    finally:
        sealer.close()
