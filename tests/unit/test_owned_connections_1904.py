"""#1904：连接随所有者关闭；封存忙时指出私有构建库上连接的创建者。

Python 3.13 上从未关闭的连接由终结器关闭，但语句缓存仍在，SQLite 保留文件与锁，
Python 层却显示"已关闭"。这里覆盖两件事：

* 生产代码中从不显式关闭的连接（其他线程的线程本地写连接、未索引锚连接、路由
  缓存连接）在所有者消失时被显式关闭；
* 版本存储 ``index.db`` 上的连接记下创建栈，封存忙的证据里带上它。
"""

from __future__ import annotations

import gc
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.cache import connection_owners, seal_creators


def _record_closes(monkeypatch) -> list[tuple[int, sqlite3.Connection, str]]:
    """记录所有者终结器关闭的连接、关闭所在线程，以及关闭后的状态。"""
    closed: list[tuple[int, sqlite3.Connection, str]] = []
    real = connection_owners.close_owned

    def recording(connection: sqlite3.Connection) -> None:
        real(connection)
        try:
            connection.total_changes  # noqa: B018 - 已关闭的连接在此抛出
            state = "open"
        except sqlite3.ProgrammingError as exc:
            state = "closed" if "closed" in str(exc) else f"error: {exc}"
        closed.append((threading.get_ident(), connection, state))

    monkeypatch.setattr(connection_owners, "close_owned", recording)
    return closed


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _is_closed(connection: sqlite3.Connection) -> bool:
    try:
        connection.total_changes  # noqa: B018
    except sqlite3.ProgrammingError as exc:
        return "closed" in str(exc)
    return False


def test_thread_local_writer_closes_in_its_thread_when_the_thread_exits(
    tmp_path, monkeypatch
):
    # cache.close() 只关闭调用线程的连接；工作线程的 WAL 写连接原本在线程退出后
    # 只被引用环持有，打开到下次垃圾回收为止。
    from tree_sitter_analyzer.ast_cache import ASTCache

    closed = _record_closes(monkeypatch)
    cache = ASTCache(str(tmp_path), str(tmp_path / "custom" / "index.db"))
    made: dict[str, object] = {}

    def work() -> None:
        connection = cache.get_conn()
        connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        made["thread"] = threading.get_ident()
        made["connection"] = connection

    worker = threading.Thread(target=work)
    worker.start()
    worker.join()
    try:
        assert _wait_for(lambda: any(c is made["connection"] for _, c, _s in closed))
        thread, _connection, state = next(
            entry for entry in closed if entry[1] is made["connection"]
        )
        assert (thread, state) == (made["thread"], "closed")
    finally:
        cache.close()


def test_explicitly_closed_thread_connection_is_not_closed_again_elsewhere(
    tmp_path, monkeypatch
):
    from tree_sitter_analyzer.ast_cache import ASTCache

    closed = _record_closes(monkeypatch)
    cache = ASTCache(str(tmp_path), str(tmp_path / "custom" / "index.db"))
    connection = cache.get_conn()
    cache.close()
    assert _is_closed(connection)
    # 显式关闭后令牌随即释放：终结器在本线程对已关闭连接是空操作。
    assert [state for _t, c, state in closed if c is connection] in ([], ["closed"])
    reopened = cache.get_conn()
    try:
        assert reopened is not connection
        reopened.execute("SELECT 1").fetchone()
    finally:
        cache.close()


def test_unindexed_anchor_closes_with_its_cache(tmp_path, monkeypatch):
    # 尚未索引的项目上，读者使用进程内共享空库；调用方未 close 缓存对象时，
    # 锚连接原本只能等回收器的终结器关闭。
    from tree_sitter_analyzer.ast_cache import ASTCache

    closed = _record_closes(monkeypatch)
    cache = ASTCache(str(tmp_path))
    anchor = cache._unindexed_anchor
    assert anchor is not None
    cache.close()  # close() 按约定保留锚连接
    assert not _is_closed(anchor)
    del cache
    gc.collect()
    assert _is_closed(anchor)
    assert [state for _t, c, state in closed if c is anchor] == ["closed"]


def test_route_cache_connections_close_with_the_cache(tmp_path):
    # MCP 工具持有的检测器随服务丢弃，从不调用 close()。
    from tree_sitter_analyzer.registry.route_cache import RouteCache

    cache = RouteCache(tmp_path / "routes.db")
    connection = cache._conn()
    other: list[sqlite3.Connection] = []
    worker = threading.Thread(target=lambda c: other.append(c._conn()), args=(cache,))
    worker.start()
    worker.join()
    del cache
    gc.collect()
    assert _is_closed(connection)
    assert _is_closed(other[0])


def test_generation_database_paths_are_recognized():
    build = os.path.join("p", ".ast-cache", "index-generations", "generations", "g1")
    assert seal_creators.is_generation_database(os.path.join(build, "index.db"))
    # Python 3.10 passes the path to the audit hook as file-system bytes.
    assert seal_creators.is_generation_database(
        os.fsencode(os.path.join(build, "index.db"))
    )
    assert seal_creators.is_generation_database(
        "file:///p/.ast-cache/index-generations/generations/g1/index.db?mode=ro"
    )
    assert not seal_creators.is_generation_database("/p/.ast-cache/index.db")
    assert not seal_creators.is_generation_database(":memory:")
    assert not seal_creators.is_generation_database(
        "/p/.ast-cache/index-generations/lease.db"
    )
    assert not seal_creators.is_generation_database(None)


def _generation_database(tmp_path) -> str:
    directory = tmp_path / "index-generations" / "generations" / "g1"
    directory.mkdir(parents=True)
    return str(directory / "index.db")


def _open_reader_for_the_creators_test(database: str) -> sqlite3.Connection:
    return sqlite3.connect(database)


def test_creators_name_the_code_that_opened_a_live_connection(tmp_path):
    database = _generation_database(tmp_path)
    seal_creators.install()
    holder = _open_reader_for_the_creators_test(database)
    unrelated = sqlite3.connect(str(tmp_path / "other.db"))
    try:
        found = seal_creators.creators(database)
        assert len(found) == 1
        assert found[0]["state"] == "open"
        assert found[0]["thread"] == threading.current_thread().name
        assert any(
            "_open_reader_for_the_creators_test" in frame for frame in found[0]["stack"]
        )
        assert seal_creators.creators(database, exclude=holder) == []
        holder.close()
        # 已关闭却仍存活的连接照常列出：它可能是仍持锁的僵尸连接。
        assert [entry["state"] for entry in seal_creators.creators(database)] == [
            "closed"
        ]
    finally:
        holder.close()
        unrelated.close()
    del holder
    gc.collect()
    assert seal_creators.creators(database) == []


def test_creator_records_do_not_survive_address_reuse():
    # 记录按 id 存放；同一地址上的新连接（任何路径）都会覆盖或清除旧记录。
    connection = sqlite3.connect(":memory:")
    try:
        seal_creators._audit(
            "sqlite3.connect", ("/p/index-generations/generations/g/index.db",)
        )
        seal_creators._audit("sqlite3.connect/handle", (connection,))
        assert id(connection) in seal_creators._records
        seal_creators._audit("sqlite3.connect", (":memory:",))
        seal_creators._audit("sqlite3.connect/handle", (connection,))
        assert id(connection) not in seal_creators._records
    finally:
        connection.close()


def test_creator_records_are_bounded(monkeypatch):
    monkeypatch.setattr(seal_creators, "_records", type(seal_creators._records)())
    monkeypatch.setattr(seal_creators, "MAX_RECORDS", 3)
    objects = [object() for _ in range(5)]
    for obj in objects:
        seal_creators._audit(
            "sqlite3.connect", ("/p/index-generations/generations/g/index.db",)
        )
        seal_creators._audit("sqlite3.connect/handle", (obj,))
    assert list(seal_creators._records) == [id(obj) for obj in objects[2:]]


def _hold_build_database(monkeypatch, holders: list[sqlite3.Connection]) -> None:
    from tree_sitter_analyzer.cache import generation_store

    seal = generation_store.GenerationStore.seal

    def held_seal(self, selector):
        holders.append(
            sqlite3.connect(self.database(selector).as_uri() + "?mode=ro", uri=True)
        )
        holders[-1].execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        return seal(self, selector)

    monkeypatch.setattr(generation_store.GenerationStore, "seal", held_seal)


def test_seal_busy_evidence_names_the_holder_creator(tmp_path, monkeypatch, caplog):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_seal, generation_store

    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    holders: list[sqlite3.Connection] = []
    _hold_build_database(monkeypatch, holders)
    monkeypatch.setattr(generation_seal, "SEAL_BUSY_TIMEOUT_S", 0.05)
    monkeypatch.setattr(generation_store, "reseal_supported", lambda: False)
    cache = ASTCache(str(tmp_path))
    try:
        with caplog.at_level("WARNING", logger=generation_seal.__name__):
            with pytest.raises(generation_seal.SealBusy):
                cache.index_project()
    finally:
        for holder in holders:
            holder.close()
        cache.close()
    assert "creators [{" in caplog.text
    assert "held_seal" in caplog.text


@pytest.mark.skipif(os.name != "posix", reason="the copy seal is POSIX-only")
def test_sealed_copy_warning_names_the_holder_creator(tmp_path, monkeypatch, caplog):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_store

    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    holders: list[sqlite3.Connection] = []
    _hold_build_database(monkeypatch, holders)
    monkeypatch.setattr(generation_store, "SEAL_HOLDER_WAIT_S", 0.05)
    cache = ASTCache(str(tmp_path))
    try:
        with caplog.at_level("WARNING", logger=generation_store.__name__):
            assert cache.index_project()["published"] is True
    finally:
        for holder in holders:
            holder.close()
        cache.close()
    copied = [
        r.getMessage() for r in caplog.records if "sealed a byte copy" in r.getMessage()
    ]
    assert len(copied) == 1
    assert "held_seal" in copied[0]


def test_close_owned_tolerates_the_wrong_thread_and_close_errors(caplog):
    made: list[sqlite3.Connection] = []
    worker = threading.Thread(target=lambda: made.append(sqlite3.connect(":memory:")))
    worker.start()
    worker.join()
    with caplog.at_level("DEBUG", logger=connection_owners.__name__):
        connection_owners.close_owned(made[0])  # 其他线程创建：不能在此关闭

        class Failing:
            def close(self) -> None:
                raise sqlite3.OperationalError("injected close failure")

        connection_owners.close_owned(Failing())  # type: ignore[arg-type]
    assert "not closed from this thread" in caplog.text
    assert "injected close failure" in caplog.text


def test_route_cache_finalizer_logs_a_failing_close(caplog):
    import tree_sitter_analyzer.registry.route_cache as route_cache

    class Failing:
        def close(self) -> None:
            raise sqlite3.OperationalError("injected close failure")

    connections = {Failing()}
    with caplog.at_level("DEBUG", logger=route_cache.__name__):
        route_cache._close_connections(connections, threading.Lock())  # type: ignore[arg-type]
    assert connections == set()
    assert "injected close failure" in caplog.text


def test_creators_report_states_uris_and_never_raise(tmp_path, monkeypatch):
    seal_creators.install()
    seal_creators.install()  # 幂等
    database = _generation_database(tmp_path)
    assert seal_creators.creators(None) == []
    uri = Path(database).as_uri() + "?mode=rwc"
    opened, release = threading.Event(), threading.Event()

    def hold_in_another_thread() -> None:
        connection = sqlite3.connect(uri, uri=True)
        opened.set()
        release.wait(10)
        connection.close()

    worker = threading.Thread(target=hold_in_another_thread)
    worker.start()
    try:
        assert opened.wait(10)
        found = seal_creators.creators(database)
        assert [entry["state"] for entry in found] == ["open (other thread)"]

        def broken():
            raise RuntimeError("injected scan failure")

        monkeypatch.setattr(seal_creators, "sqlite_objects", broken)
        assert seal_creators.creators(database)[0]["error"].startswith("RuntimeError")
        monkeypatch.undo()
    finally:
        release.set()
        worker.join()


def test_audit_hook_never_raises_on_odd_arguments():
    seal_creators._audit("sqlite3.connect", ())
    seal_creators._audit("sqlite3.connect/handle", ())
    seal_creators._audit("open", ("x", "r", 0))
