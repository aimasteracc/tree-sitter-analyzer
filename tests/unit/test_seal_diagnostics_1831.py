"""#1831：封存忙时记录的持有者证据（锁表、描述符、连接、线程）。"""

from __future__ import annotations

import os
import sqlite3
import threading

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
