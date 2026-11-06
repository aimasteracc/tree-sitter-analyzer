"""#1831：封存忙时记录的持有者证据（锁表、描述符、连接、线程）。"""

from __future__ import annotations

import os
import sqlite3
import threading

import pytest

from tree_sitter_analyzer.cache import seal_diagnostics


def test_lock_table_lines_for_the_inode_are_reported_with_their_pid(
    tmp_path, monkeypatch
):
    table = tmp_path / "locks"
    table.write_text(
        "1: POSIX  ADVISORY  READ 4242 08:01:777 1073741826 1073742335\n"
        "1: -> POSIX  ADVISORY  WRITE 4343 08:01:777 1073741824 1073741824\n"
        "2: FLOCK  ADVISORY  WRITE 99 08:01:778 0 EOF\n"
        "short line\n",
        encoding="ascii",
    )
    monkeypatch.setattr(seal_diagnostics, "PROC_LOCKS", table)
    assert seal_diagnostics.posix_locks(777) == [
        "POSIX READ 4242 1073741826 1073742335",
        "POSIX WRITE 4343 1073741824 1073741824",
    ]
    assert seal_diagnostics.posix_locks(5) == []


def test_missing_lock_table_and_descriptor_directory_are_omitted(tmp_path, monkeypatch):
    monkeypatch.setattr(seal_diagnostics, "PROC_LOCKS", tmp_path / "absent")
    monkeypatch.setattr(seal_diagnostics, "PROC_FDS", tmp_path / "absent-dir")
    database = tmp_path / "index.db"
    database.write_bytes(b"")
    evidence = seal_diagnostics.holder_evidence(database)
    assert "posix_locks" not in evidence
    assert "own_descriptors" not in evidence
    assert evidence["pid"] == os.getpid()


def test_unreadable_descriptor_entries_are_skipped(tmp_path, monkeypatch):
    fds = tmp_path / "fd"
    fds.mkdir()
    (fds / "3").write_text("not a link", encoding="ascii")
    monkeypatch.setattr(seal_diagnostics, "PROC_FDS", fds)
    assert seal_diagnostics.own_descriptors(tmp_path / "index.db") == 0


def test_missing_database_reports_only_process_evidence(tmp_path):
    evidence = seal_diagnostics.holder_evidence(tmp_path / "gone.db")
    assert set(evidence) == {"pid", "threads", "open_connections"}
    assert set(seal_diagnostics.holder_evidence(None)) == set(evidence)


def test_open_connections_count_other_threads_but_not_closed_ones():
    before = seal_diagnostics.open_connection_count()
    opened = threading.Event()
    release = threading.Event()

    def hold() -> None:
        conn = sqlite3.connect(":memory:")  # 只能在本线程使用和关闭
        opened.set()
        release.wait(30)
        conn.close()

    worker = threading.Thread(target=hold)
    worker.start()
    assert opened.wait(30)
    closed = sqlite3.connect(":memory:")
    closed.close()
    try:
        assert seal_diagnostics.open_connection_count() == before + 1
    finally:
        release.set()
        worker.join(30)


class _SubclassedConnection(sqlite3.Connection):
    pass


class _SubclassedCursor(sqlite3.Cursor):
    pass


@pytest.mark.parametrize("via_types", [True, False])
def test_sqlite_objects_finds_connections_cursors_and_subclasses(
    monkeypatch, via_types
):
    # 经由类型的引用者一次找出全部实例；探测不成立时退回逐个遍历全堆，结果相同。
    monkeypatch.setattr(seal_diagnostics, "_type_referrers_work", None)
    if not via_types:
        monkeypatch.setattr(seal_diagnostics, "_probe_type_referrers", lambda: False)
    plain = sqlite3.connect(":memory:")
    sub = sqlite3.connect(":memory:", factory=_SubclassedConnection)
    cursor = plain.cursor()
    sub_cursor = _SubclassedCursor(sub)
    closed = sqlite3.connect(":memory:")
    closed.close()
    try:
        found = {id(obj) for obj in seal_diagnostics.sqlite_objects()}
        assert seal_diagnostics._type_referrers_work is via_types
    finally:
        cursor.close()
        plain.close()
        sub.close()
    assert {id(plain), id(sub), id(cursor), id(sub_cursor), id(closed)} <= found
    assert id(_SubclassedConnection) not in found  # 类型本身不是实例


def test_the_type_referrer_probe_holds_on_this_interpreter():
    # CI 覆盖的每个 Python 版本上都应走快速路径；否则大进程里的取证又会变慢。
    assert seal_diagnostics._probe_type_referrers() is True


def test_a_failing_count_is_reported_not_raised(monkeypatch):
    def broken():
        raise RuntimeError("injected scan failure")

    monkeypatch.setattr(seal_diagnostics, "sqlite_objects", broken)
    evidence = seal_diagnostics.holder_evidence(None)
    assert evidence["open_connections"] == "RuntimeError: injected scan failure"
    # 调用方给出的对象列表直接使用，不再查找。
    assert seal_diagnostics.holder_evidence(None, objects=[])["open_connections"] == 0
