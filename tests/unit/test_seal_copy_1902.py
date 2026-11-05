"""#1902：封存时私有库仍被另一句柄打开，POSIX 上改为封存字节副本并照常发布。

CI 上 ``INDEX_GENERATION_SEAL_BUSY`` 的持有者在本进程、只有主线程，Python 层却看不到
对应的连接或游标（``holders []``）；等满 10 s 后刷新不发布，``nav context`` 刷新、
``test_edge_store``、``--watch-health`` 与监视器重试测试都因此超时。这里用一个在封存
前打开、封存期间一直不关闭的读者确定性地重现“切回回滚日志永远失败”的条件。
"""

from __future__ import annotations

import os
import sqlite3
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Windows cannot replace a file another handle holds"
)


def _hold_build_database(monkeypatch, holders: list[sqlite3.Connection]) -> None:
    """封存前在私有构建库上打开一个空闲 WAL 读者，并一直保持打开。"""
    from tree_sitter_analyzer.cache import generation_store

    seal = generation_store.GenerationStore.seal

    def held_seal(self, selector):
        reader = sqlite3.connect(
            self.database(selector).as_uri() + "?mode=ro", uri=True
        )
        reader.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        holders.append(reader)
        return seal(self, selector)

    monkeypatch.setattr(generation_store.GenerationStore, "seal", held_seal)


def _published_database(root) -> str:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(str(root))
    assert location.published is True
    return str(location.path)


def _record_seal_path(monkeypatch) -> dict[str, list]:
    """记录封存内部的忙等待参数、实际睡眠、结局、副本调用与封存耗时。

    #1909：旧断言把整个 ``index_project()`` 的墙钟与 10 s 忙等待期限比较，慢 macOS
    上到过 10.34 s。探针显示几乎全部是封存本身：短等待之外，期满时的堆扫描取证在
    CPU 不足的 runner 上要数秒（已改为副本路径跳过）。墙钟仍随 runner 漂移，这里改为
    断言结构：只请求了短期限、睡眠总量不超过它、等满仍忙、走了副本。
    """
    from tree_sitter_analyzer.cache import generation_store

    seen: dict[str, list] = {
        "waits": [],
        "slept": [],
        "outcomes": [],
        "copies": [],
        "seals": [],
    }
    leave_wal = generation_store.leave_wal
    reseal = generation_store.reseal_by_copy
    seal = generation_store.GenerationStore.seal

    def counting_sleep(seconds: float) -> None:
        seen["slept"].append(seconds)
        time.sleep(seconds)

    def recording_leave_wal(connection, **kwargs):
        seen["waits"].append((kwargs.get("timeout"), kwargs.get("fallback")))
        try:
            journal = leave_wal(connection, sleep=counting_sleep, **kwargs)
        except generation_store.SealBusy:
            seen["outcomes"].append("busy")
            raise
        seen["outcomes"].append(journal)
        return journal

    def recording_reseal(database, cause=None):
        seen["copies"].append(type(cause).__name__)
        return reseal(database, cause=cause)

    def timed_seal(self, selector):
        started = time.monotonic()
        try:
            return seal(self, selector)
        finally:
            seen["seals"].append(time.monotonic() - started)

    monkeypatch.setattr(generation_store, "leave_wal", recording_leave_wal)
    monkeypatch.setattr(generation_store, "reseal_by_copy", recording_reseal)
    monkeypatch.setattr(generation_store.GenerationStore, "seal", timed_seal)
    return seen


def test_a_held_build_database_is_sealed_as_a_copy_and_published(
    tmp_path, monkeypatch, caplog
):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_store

    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    holders: list[sqlite3.Connection] = []
    seen = _record_seal_path(monkeypatch)
    _hold_build_database(monkeypatch, holders)
    cache = ASTCache(str(tmp_path))
    try:
        with caplog.at_level("WARNING", logger=generation_store.__name__):
            assert cache.index_project()["published"] is True
        assert cache.get_stats()["total_files"] == 1
        # 残留句柄仍可用，但它读的是已被替换的旧 inode，不影响发布的文件。
        assert holders[0].execute("SELECT 1").fetchone() == (1,)
    finally:
        for holder in holders:
            holder.close()
        cache.close()
    # 只等短期限、等满仍忙、改走副本——而不是旧路径的 10 s 忙等待。
    assert (seen["waits"], seen["outcomes"], seen["copies"]) == (
        [(generation_store.SEAL_HOLDER_WAIT_S, True)],
        ["busy"],
        ["SealBusy"],
    )
    # 旧路径要睡满 SEAL_BUSY_TIMEOUT_S（10 s）；这里请求的睡眠总量以短期限为界，
    # 与 runner 快慢无关。封存墙钟只随失败信息报告。
    slept = sum(seen["slept"])
    assert 0 < slept <= generation_store.SEAL_HOLDER_WAIT_S + 1e-9, seen
    assert len(seen["seals"]) == 1, seen
    assert "sealed a byte copy" in caplog.text, seen
    database = _published_database(tmp_path)
    assert not any(
        os.path.lexists(database + suffix) for suffix in ("-wal", "-shm", "-journal")
    )
    assert not os.path.lexists(database + ".sealing")
    with open(database, "rb") as handle:
        header = handle.read(20)
    assert header[18:20] == b"\x01\x01"  # 回滚日志模式（WAL 为 2）
    assert not os.access(database, os.W_OK)
    reader = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert reader.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reader.close()


def test_a_build_database_written_during_the_copy_is_not_published(
    tmp_path, monkeypatch
):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_seal, seal_copy
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    holders: list[sqlite3.Connection] = []
    _hold_build_database(monkeypatch, holders)
    copy = seal_copy._copy_bytes

    def copy_then_touch(source, destination):
        copy(source, destination)
        stamp = os.stat(source).st_mtime_ns + 1_000_000
        os.utime(source, ns=(stamp, stamp))  # 复制期间源文件变化

    monkeypatch.setattr(seal_copy, "_copy_bytes", copy_then_touch)
    cache = ASTCache(str(tmp_path))
    try:
        with pytest.raises(generation_seal.SealBusy):
            cache.index_project()
    finally:
        for holder in holders:
            holder.close()
        cache.close()
    assert resolve_index_location(str(tmp_path)).published is False
    leftovers = [
        name
        for _root, _dirs, files in os.walk(tmp_path)
        for name in files
        if name.endswith(seal_copy.SEALING_SUFFIX)
    ]
    assert leftovers == []


def test_reseal_by_copy_switches_only_the_copy(tmp_path):
    from tree_sitter_analyzer.cache.generation_seal import SealBusy, leave_wal
    from tree_sitter_analyzer.cache.seal_copy import reseal_by_copy

    database = tmp_path / "index.db"
    writer = sqlite3.connect(database)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE t (x)")
    writer.execute("INSERT INTO t VALUES (7)")
    writer.commit()
    holder = sqlite3.connect(database)
    holder.execute("SELECT * FROM t").fetchall()
    try:
        assert writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
        with pytest.raises(SealBusy):
            leave_wal(writer, database=database, timeout=0.05)
        writer.close()
        reseal_by_copy(database)
        assert holder.execute("SELECT * FROM t").fetchall() == [(7,)]
    finally:
        holder.close()
    sealed = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        assert sealed.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert sealed.execute("SELECT * FROM t").fetchall() == [(7,)]
    finally:
        sealed.close()


def test_reseal_refuses_a_wal_that_gained_frames(tmp_path):
    from tree_sitter_analyzer.cache.generation_seal import SealBusy
    from tree_sitter_analyzer.cache.seal_copy import reseal_by_copy

    database = tmp_path / "index.db"
    writer = sqlite3.connect(database)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE t (x)")
        writer.commit()  # 帧留在 WAL 中，主库字节不代表整个库
        with pytest.raises(SealBusy):
            reseal_by_copy(database)
    finally:
        writer.close()
