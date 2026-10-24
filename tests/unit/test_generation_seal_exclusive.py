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
