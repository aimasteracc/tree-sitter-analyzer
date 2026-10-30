"""#1848：封存期满仍忙时，警告日志指出持有私有版本的对象及引用它的代码。

CI 上两次 ``SealBusy`` 的证据只说明持有者在本进程、只有主线程、该文件上多一个
描述符。每个用例在私有构建库上制造一种持有者，把它挂在一个可辨认的实例上，
断言警告日志写出持有者种类与该实例的类型。
"""

from __future__ import annotations

import gc
import sqlite3
import threading
from pathlib import Path

import pytest


class _LeakedReaderOwner:
    """模拟泄漏连接或游标的代码：属性上挂着持有者。"""

    def __init__(self, held: object) -> None:
        self.held = held


def _seal_with_holder(monkeypatch, make_holder, owners: list[object]) -> None:
    from tree_sitter_analyzer.cache import generation_store

    seal = generation_store.GenerationStore.seal

    def held_seal(self, selector):
        owners.append(_LeakedReaderOwner(make_holder(self.database(selector))))
        return seal(self, selector)

    monkeypatch.setattr(generation_store.GenerationStore, "seal", held_seal)


def _idle_reader(database: Path) -> sqlite3.Connection:
    reader = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    reader.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
    return reader


def _zombie_cursor(database: Path) -> sqlite3.Cursor:
    """连接已关闭、未读完的游标仍存活：关闭的连接成为僵尸并继续持锁。"""
    reader = sqlite3.connect(database)
    cursor = reader.execute(
        "SELECT name FROM sqlite_master UNION ALL SELECT name FROM sqlite_master"
    )
    assert type(cursor.fetchone()[0]) is str  # 读出第一行，语句停在两行之间
    reader.close()
    return cursor


def _zombie_holds_lock(tmp_path: Path) -> bool:
    """旧版 ``sqlite3``（3.10）关闭连接时终结全部语句，不会留下僵尸。"""
    database = tmp_path / "probe.db"
    setup = sqlite3.connect(database)
    setup.execute("PRAGMA journal_mode=WAL")
    setup.execute("CREATE TABLE t (x)")
    setup.executemany("INSERT INTO t VALUES (?)", [(1,), (2,)])
    setup.commit()
    setup.close()
    cursor = _zombie_cursor(database)
    sealer = sqlite3.connect(database, timeout=0)
    try:
        sealer.execute("PRAGMA journal_mode=DELETE").fetchone()
    except sqlite3.OperationalError:
        return True
    finally:
        sealer.close()
        del cursor
    return False


def _busy_seal_log(tmp_path, monkeypatch, caplog, make_holder) -> str:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_seal

    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    owners: list[object] = []
    _seal_with_holder(monkeypatch, make_holder, owners)
    monkeypatch.setattr(generation_seal, "SEAL_BUSY_TIMEOUT_S", 0.05)
    cache = ASTCache(str(project))
    try:
        with caplog.at_level("WARNING", logger=generation_seal.__name__):
            with pytest.raises(generation_seal.SealBusy):
                cache.index_project()
    finally:
        for owner in owners:
            held = owner.held  # type: ignore[attr-defined]
            if isinstance(held, sqlite3.Connection):
                held.close()
        owners.clear()
        gc.collect()
        cache.close()
    return caplog.text


def test_seal_busy_names_an_open_connection_and_its_owner(
    tmp_path, monkeypatch, caplog
):
    text = _busy_seal_log(tmp_path, monkeypatch, caplog, _idle_reader)
    assert "holders [{'kind': 'open_connection'" in text
    assert "_LeakedReaderOwner" in text


def test_seal_busy_names_a_zombie_cursor_and_its_owner(tmp_path, monkeypatch, caplog):
    if not _zombie_holds_lock(tmp_path):
        pytest.skip("this sqlite3 finalizes statements on close; no zombie lock")
    text = _busy_seal_log(tmp_path, monkeypatch, caplog, _zombie_cursor)
    assert "'kind': 'cursor_on_closed_connection'" in text
    assert "_LeakedReaderOwner" in text


def test_holder_objects_reports_a_connection_owned_by_another_thread(tmp_path):
    from tree_sitter_analyzer.cache.seal_holders import holder_objects

    database = tmp_path / "other.db"
    sqlite3.connect(database).close()
    owners: list[_LeakedReaderOwner] = []
    opened, done = threading.Event(), threading.Event()

    def hold() -> None:
        owners.append(_LeakedReaderOwner(sqlite3.connect(database)))
        opened.set()
        done.wait(30)
        owners[0].held.close()  # type: ignore[attr-defined]

    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert opened.wait(30)
        holders = holder_objects(database)
    finally:
        done.set()
        worker.join(30)
    other = [h for h in holders if h["kind"] == "other_thread_connection"]
    assert other, holders
    assert any(
        "_LeakedReaderOwner" in step for holder in other for step in holder["held_by"]
    )


def test_holder_objects_skips_the_excluded_and_unrelated_connections(tmp_path):
    from tree_sitter_analyzer.cache.seal_holders import holder_objects

    database = tmp_path / "mine.db"
    unrelated = tmp_path / "unrelated.db"
    own = sqlite3.connect(database)
    other = sqlite3.connect(unrelated)
    try:
        holders = holder_objects(database, exclude=own)
    finally:
        own.close()
        other.close()
    assert [h for h in holders if h["kind"] == "open_connection"] == []


def test_holder_objects_never_raises(monkeypatch):
    from tree_sitter_analyzer.cache import seal_holders

    def broken():
        raise RuntimeError("heap walk failed")

    monkeypatch.setattr(seal_holders.gc, "get_objects", broken)
    assert seal_holders.holder_objects("x.db") == [
        {"error": "RuntimeError: heap walk failed"}
    ]


def _read_until_interrupted(connection: sqlite3.Connection) -> None:
    cursor = connection.execute(
        "SELECT name FROM sqlite_master UNION ALL SELECT name FROM sqlite_master"
    )
    for _row in cursor:
        raise TimeoutError("deadline between rows")


def test_holder_chain_names_the_frame_kept_by_a_retained_exception(tmp_path):
    # #1832 的模式：两行之间抛出的异常被保留，帧的局部游标让关闭的连接成为僵尸。
    from tree_sitter_analyzer.cache.seal_holders import holder_objects

    if not _zombie_holds_lock(tmp_path):
        pytest.skip("this sqlite3 finalizes statements on close; no zombie lock")
    database = tmp_path / "kept.db"
    setup = sqlite3.connect(database)
    setup.execute("CREATE TABLE t (x)")
    setup.commit()
    setup.close()
    kept: list[BaseException] = []
    reader = sqlite3.connect(database)
    try:
        _read_until_interrupted(reader)
    except TimeoutError as exc:
        kept.append(exc)
    finally:
        reader.close()
    owner = _LeakedReaderOwner(kept)
    holders = holder_objects(database)
    zombies = [h for h in holders if h["kind"] == "cursor_on_closed_connection"]
    chains = [" <- ".join(h["held_by"]) for h in zombies]
    assert any("frame _read_until_interrupted" in chain for chain in chains), chains
    del owner


def test_holder_chain_stops_at_the_time_budget(tmp_path, monkeypatch):
    from tree_sitter_analyzer.cache import seal_holders

    database = tmp_path / "budget.db"
    holder = _LeakedReaderOwner(sqlite3.connect(database))
    monkeypatch.setattr(seal_holders, "CHAIN_BUDGET_S", -1.0)
    try:
        holders = seal_holders.holder_objects(database)
    finally:
        holder.held.close()  # type: ignore[attr-defined]
    assert holders[0]["kind"] == "open_connection"
    assert holders[0]["held_by"] == [seal_holders.CHAIN_TRUNCATED]


def test_holder_chain_stops_after_the_step_limit(tmp_path):
    from tree_sitter_analyzer.cache import seal_holders

    database = tmp_path / "deep.db"
    connection = sqlite3.connect(database)
    nested: object = {"held": connection}  # 普通 dict：没有实例所有者
    for _ in range(seal_holders.MAX_CHAIN + 3):
        nested = [nested]
    keep = _LeakedReaderOwner(nested)
    try:
        holders = seal_holders.holder_objects(database)
    finally:
        connection.close()
    chain = holders[0]["held_by"]
    assert len(chain) == seal_holders.MAX_CHAIN
    assert chain == ["builtins.dict"] + ["builtins.list"] * (seal_holders.MAX_CHAIN - 1)
    del keep


class _ClassHolder:
    held: object = None


def test_holder_chain_ends_at_the_class_that_holds_it(tmp_path):
    from tree_sitter_analyzer.cache.seal_holders import holder_objects

    database = tmp_path / "class.db"
    _ClassHolder.held = sqlite3.connect(database)
    try:
        holders = holder_objects(database)
    finally:
        _ClassHolder.held.close()  # type: ignore[attr-defined]
        _ClassHolder.held = None
    chain = holders[0]["held_by"]
    assert chain[-1] == f"class {__name__}._ClassHolder"


def test_describe_names_generators_coroutines_classes_and_exceptions():
    from tree_sitter_analyzer.cache.seal_holders import _describe

    def rows():
        yield 1

    async def answer():
        return 1

    generator = rows()
    coroutine = answer()
    try:
        assert _describe(generator).startswith(
            "generator test_describe_names_generators_coroutines_classes_and_"
            "exceptions.<locals>.rows (tests/unit/test_seal_holders_1848.py:"
        )
        assert _describe(coroutine).startswith("coroutine ")
        assert _describe(_ClassHolder) == f"class {__name__}._ClassHolder"
        assert _describe(TimeoutError("late")) == "exception TimeoutError: late"
        for _ in generator:
            pass
        assert _describe(generator) == (
            "generator test_describe_names_generators_coroutines_classes_and_"
            "exceptions.<locals>.rows"
        )
    finally:
        coroutine.close()


class _BrokenCursor(sqlite3.Cursor):
    @property
    def connection(self):  # type: ignore[override]
        raise RuntimeError("no connection")


class _BrokenTotalChanges:
    @property
    def total_changes(self):
        raise RuntimeError("broken")


def test_classify_skips_objects_it_cannot_inspect(tmp_path):
    from tree_sitter_analyzer.cache import seal_holders

    connection = sqlite3.connect(":memory:")
    try:
        cursor = _BrokenCursor(connection)
        assert seal_holders._classify(cursor, None) is None
        assert seal_holders._is_closed(_BrokenTotalChanges()) is False  # type: ignore[arg-type]
        assert seal_holders._connection_kind(object(), None) is None  # type: ignore[arg-type]
        # 行工厂返回不可索引的行：跳过该行，而不是抛出。
        connection.row_factory = lambda _cursor, _row: object()
        assert seal_holders._connection_kind(connection, str(tmp_path)) is None
    finally:
        connection.close()


def test_dict_owner_is_none_for_a_plain_dict():
    from tree_sitter_analyzer.cache.seal_holders import _dict_owner

    mapping = {"x": 1}
    holder = [mapping]
    assert _dict_owner(mapping, set()) is None
    del holder
