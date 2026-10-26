"""#1821：封存时不得有其他连接打开私有构建库。

WAL 模式下任何打开过的连接（哪怕空闲）都在主库上持有 SHARED 锁；``seal()`` 的
``PRAGMA journal_mode=DELETE`` 需要排他锁且不经忙等待，立即报
``database is locked``。``wal_checkpoint(TRUNCATE)`` 却能成功，所以只有封存失败。
"""

from __future__ import annotations

import gc
import os
import sqlite3
import threading
import traceback
import weakref

import pytest


class _Tracker:
    def __init__(self) -> None:
        self.opened: list[tuple[weakref.ref[sqlite3.Connection], str, str, str]] = []
        self._subclasses: dict[type, type] = {}
        self._connect = sqlite3.connect

    def connect(self, *args, **kwargs):
        factory = kwargs.get("factory", sqlite3.Connection)
        if factory not in self._subclasses:
            # sqlite3.Connection 不支持弱引用；Python 子类自带 __weakref__。
            self._subclasses[factory] = type(
                f"Tracked{factory.__name__}", (factory,), {}
            )
        kwargs["factory"] = self._subclasses[factory]
        conn = self._connect(*args, **kwargs)
        database = str(args[0] if args else kwargs.get("database"))
        self.opened.append(
            (
                weakref.ref(conn),
                database,
                threading.current_thread().name,
                "".join(traceback.format_stack(limit=12)[:-1]),
            )
        )
        return conn

    def open_on(self, database: str) -> list[str]:
        target = os.path.normcase(os.path.realpath(database))
        leaks = []
        for ref, path, thread, stack in self.opened:
            conn = ref()
            if conn is None:
                continue
            try:
                conn.total_changes  # noqa: B018 - 已关闭连接在此抛出
            except sqlite3.ProgrammingError as exc:
                if "closed" in str(exc):
                    continue
            plain = path.removeprefix("file:").split("?", 1)[0]
            if plain.startswith("///"):
                plain = plain[3:] if os.name == "nt" else plain[2:]
            if os.path.normcase(os.path.realpath(plain)) == target:
                leaks.append(f"{path} (thread {thread})\n{stack}")
        return leaks


@pytest.mark.parametrize("published", [False, True])
def test_private_build_never_waits_on_a_lock_another_cache_holds(
    tmp_path, monkeypatch, published
):
    # #1819：另一个缓存（同一数据库）持有读事务时，私有构建的 WAL 初始化、写入与
    # 封存都不需要等它的锁：私有库是新文件，别的连接不知道它的路径。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    source = tmp_path / "a.py"
    source.write_text("def saved(): pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    other = ASTCache(str(tmp_path))
    watcher = FileWatcherDaemon(cache)
    try:
        if published:
            assert watcher.trigger_sync()["new_files"] == 1
            other.release_thread_connection()  # 重新解析到已发布版本
            source.write_text("def changed(): pass\n", encoding="utf-8")
        reader = other.get_conn()
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        real_connect = sqlite3.connect

        def no_wait(*args, **kwargs):
            # 发布租约库按设计等待（LEASE_TIMEOUT_S）；其余连接一旦等锁立即失败。
            if "publication.lock" not in str(args[0] if args else ""):
                kwargs["timeout"] = 0
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", no_wait)
        result = watcher.trigger_sync()
        assert (result["new_files"], result["updated_files"]) == (
            (0, 1) if published else (1, 0)
        )
        reader.rollback()
    finally:
        watcher.stop()
        other.close()
        cache.close()


@pytest.mark.parametrize("files", [1, 2])
def test_seal_finds_no_other_connection_on_the_build_database(
    tmp_path, monkeypatch, files
):
    # gc 关闭后，靠循环回收才关闭的连接在封存时必然仍打开（CI 上的偶发即此时序）。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_store

    for index in range(files):
        (tmp_path / f"m{index}.py").write_text(
            "def f():\n    return g()\n\n\ndef g():\n    return 1\n", encoding="utf-8"
        )
    tracker = _Tracker()
    monkeypatch.setattr(sqlite3, "connect", tracker.connect)
    seal = generation_store.GenerationStore.seal
    leaks: list[str] = []

    def checked_seal(self, selector):
        leaks.extend(tracker.open_on(str(self.database(selector))))
        return seal(self, selector)

    monkeypatch.setattr(generation_store.GenerationStore, "seal", checked_seal)
    enabled = gc.isenabled()
    gc.disable()
    try:
        cache = ASTCache(str(tmp_path))
        try:
            assert cache.index_project()["published"] is True
        finally:
            cache.close()
    finally:
        if enabled:
            gc.enable()
    assert leaks == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["full", "incremental"])
async def test_full_index_tool_leaves_no_connection_on_the_build_database(
    tmp_path, monkeypatch, mode
):
    # #1831：index action=full 走 run_full_index，而不是 ASTCache.index_project；
    # 它的各阶段（共享缓存、增量同步、统计、清单盖戳）同样不得在封存时留下连接。
    from tree_sitter_analyzer.cache import generation_store
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text(
        "from .core import helper\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "core.py").write_text(
        "def helper(x):\n    return x + 1\n\nhelper(0)\n", encoding="utf-8"
    )
    (tmp_path / "app.py").write_text(
        "from pkg.core import helper\n\ndef main():\n    return helper(3)\n",
        encoding="utf-8",
    )
    tracker = _Tracker()
    monkeypatch.setattr(sqlite3, "connect", tracker.connect)
    seal = generation_store.GenerationStore.seal
    leaks: list[str] = []

    def checked_seal(self, selector):
        leaks.extend(tracker.open_on(str(self.database(selector))))
        return seal(self, selector)

    monkeypatch.setattr(generation_store.GenerationStore, "seal", checked_seal)
    enabled = gc.isenabled()
    gc.disable()
    try:
        result = await CodeGraphFullIndexTool(str(tmp_path)).execute({"mode": mode})
    finally:
        if enabled:
            gc.enable()
    assert result["published"] is True, result.get("error")
    assert leaks == [], "\n\n".join(leaks)


def _hold_build_database(monkeypatch, holders: list[sqlite3.Connection]) -> None:
    """封存前在私有构建库上打开一个空闲读者（WAL 模式下持有 SHARED 锁）。"""
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


def test_seal_waits_for_a_transient_holder_instead_of_failing(tmp_path, monkeypatch):
    # #1821：切回回滚日志不经 SQLite 忙处理器；持有者在期限内释放时封存照常完成。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_seal

    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    holders: list[sqlite3.Connection] = []
    _hold_build_database(monkeypatch, holders)
    waits: list[float] = []

    def release_then_wait(seconds: float) -> None:
        waits.append(seconds)
        holders[0].close()  # 第一次忙等待期间持有者释放

    monkeypatch.setattr(generation_seal.time, "sleep", release_then_wait)
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_project()["published"] is True
        assert cache.get_stats()["total_files"] == 1
    finally:
        cache.close()
    assert len(waits) == 1


def test_seal_still_held_after_the_wait_is_a_typed_busy_error(tmp_path, monkeypatch):
    # #1821：期满仍被占用时报告类型化 INDEX_WRITER_BUSY，不发布、不跳过日志切换。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_seal
    from tree_sitter_analyzer.cache.admission import admission_failure_of
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    holders: list[sqlite3.Connection] = []
    _hold_build_database(monkeypatch, holders)
    monkeypatch.setattr(generation_seal, "SEAL_BUSY_TIMEOUT_S", 0.05)
    cache = ASTCache(str(tmp_path))
    try:
        with pytest.raises(generation_seal.SealBusy) as raised:
            cache.index_project()
    finally:
        for holder in holders:
            holder.close()
        cache.close()
    failure = admission_failure_of(raised.value)
    assert failure is not None
    assert (failure.code, failure.cause_code, failure.contract.retryable) == (
        "INDEX_WRITER_BUSY",
        "INDEX_GENERATION_SEAL_BUSY",
        True,
    )
    assert isinstance(raised.value.__cause__, sqlite3.OperationalError)
    assert resolve_index_location(str(tmp_path)).published is False
    # 可重试：持有者释放后，同一调用重新建库并发布。
    monkeypatch.undo()
    retry = ASTCache(str(tmp_path))
    try:
        assert retry.index_project()["published"] is True
    finally:
        retry.close()


def test_seal_collects_a_holder_kept_alive_only_by_a_reference_cycle(
    tmp_path, monkeypatch, caplog
):
    # #1831：本进程中已无人使用、只被引用环引用的连接仍持有 SHARED 锁，直到循环
    # 回收运行；忙重试循环几乎不分配对象，回收可能 10 s 都不发生，于是封存等满
    # 期限后不发布。第一次忙时回收一次，这样的持有者立即释放。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_seal, generation_store

    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    seal = generation_store.GenerationStore.seal

    def seal_after_abandoned_reader(self, selector):
        reader = sqlite3.connect(
            self.database(selector).as_uri() + "?mode=ro", uri=True
        )
        reader.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        cycle: list[object] = [reader]
        cycle.append(cycle)
        del reader, cycle  # 引用计数不归零：只有循环回收能关闭它
        return seal(self, selector)

    monkeypatch.setattr(
        generation_store.GenerationStore, "seal", seal_after_abandoned_reader
    )
    monkeypatch.setattr(generation_seal, "SEAL_BUSY_TIMEOUT_S", 0.3)
    enabled = gc.isenabled()
    gc.disable()
    cache = ASTCache(str(tmp_path))
    try:
        with caplog.at_level("WARNING", logger=generation_seal.__name__):
            assert cache.index_project()["published"] is True
    finally:
        cache.close()
        if enabled:
            gc.enable()
    assert "released by garbage collection" in caplog.text


def test_seal_busy_logs_holder_evidence(tmp_path, monkeypatch, caplog):
    # #1831：期满仍被占用时，警告日志写出持有者证据（本进程连接数、线程，Linux 上
    # 还有该 inode 的 POSIX 锁与本进程描述符），CI 偶发时可据此定位持有者。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_seal

    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    holders: list[sqlite3.Connection] = []
    _hold_build_database(monkeypatch, holders)
    monkeypatch.setattr(generation_seal, "SEAL_BUSY_TIMEOUT_S", 0.05)
    cache = ASTCache(str(tmp_path))
    try:
        with caplog.at_level("WARNING", logger=generation_seal.__name__):
            with pytest.raises(generation_seal.SealBusy):
                cache.index_project()
    finally:
        for holder in holders:
            holder.close()
        cache.close()
    assert generation_seal.SEAL_BUSY in caplog.text
    assert "open_connections" in caplog.text
    if os.path.exists("/proc/locks"):
        assert f"POSIX READ {os.getpid()}" in caplog.text


def test_holder_evidence_without_a_database_is_still_bounded():
    from tree_sitter_analyzer.cache.seal_diagnostics import holder_evidence

    evidence = holder_evidence(None)
    assert evidence["pid"] == os.getpid()
    assert threading.current_thread().name in evidence["threads"]
    assert type(evidence["open_connections"]) is int
    assert "posix_locks" not in evidence


def test_seal_does_not_retry_errors_other_than_busy():
    from tree_sitter_analyzer.cache.generation_seal import leave_wal

    class Broken:
        def execute(self, _sql):
            raise sqlite3.OperationalError("disk I/O error")

    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        leave_wal(Broken(), sleep=lambda _s: pytest.fail("must not wait"))
