"""#1707：``cache.stat_evidence`` 的键、竞争窗口、失败语义与读者合并规则。

一条记录 ``路径 -> (mtime_ns, file_size, content_hash)`` 只在三者都与“磁盘戳记 +
该行的内容摘要”相同时才为该行作证；任何一项不同都不作证（读者退回原有规则：
读文件、比较摘要或判定为变更）。
"""

from __future__ import annotations

import os
import time

import pytest

from tree_sitter_analyzer.cache import stat_evidence

_HASH = "a" * 64
_PAST = time.time_ns() - 3_600 * 1_000_000_000


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".ast-cache").mkdir()
    return str(tmp_path)


def test_record_round_trips_and_vouches_only_for_the_exact_key(project) -> None:
    assert stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)}) == 1
    stamps = stat_evidence.load(project)

    assert stat_evidence.vouches(stamps, "a.py", (_PAST, 10), (10, _HASH)) is True
    assert stat_evidence.vouches(stamps, "a\\b.py", (_PAST, 10), (10, _HASH)) is False
    # 每个键都必须相同：mtime、磁盘大小、行的大小、行的摘要、路径。
    assert stat_evidence.vouches(stamps, "a.py", (_PAST + 1, 10), (10, _HASH)) is False
    assert stat_evidence.vouches(stamps, "a.py", (_PAST, 11), (10, _HASH)) is False
    assert stat_evidence.vouches(stamps, "a.py", (_PAST, 10), (11, _HASH)) is False
    assert stat_evidence.vouches(stamps, "a.py", (_PAST, 10), (10, "b" * 64)) is False
    assert stat_evidence.vouches(stamps, "b.py", (_PAST, 10), (10, _HASH)) is False


def test_racy_window_is_measured_from_the_capture(project) -> None:
    # 字节在捕获时读取：mtime 距捕获开始不足竞争窗口即不记录，即使记录时已过了 5 s。
    captured = time.time_ns() - 60 * 1_000_000_000
    written = stat_evidence.record(
        project,
        {
            "racy_at_capture.py": (captured - 1_000_000_000, 10, _HASH),
            "old.py": (captured - 10_000_000_000, 10, _HASH),
        },
        captured_at_ns=captured,
    )

    assert (written, sorted(stat_evidence.load(project))) == (1, ["old.py"])


def test_backslash_paths_are_looked_up_in_posix_form(project) -> None:
    stat_evidence.record(project, {"pkg/a.py": (_PAST, 10, _HASH)})
    stamps = stat_evidence.load(project)

    assert stat_evidence.vouches(stamps, "pkg\\a.py", (_PAST, 10), (10, _HASH)) is True


def test_racy_and_future_stamps_are_not_recorded(project) -> None:
    now = time.time_ns()
    written = stat_evidence.record(
        project,
        {
            "racy.py": (now - 1_000_000_000, 10, _HASH),
            "future.py": (now + 60_000_000_000, 10, _HASH),
            "old.py": (_PAST, 10, _HASH),
        },
    )

    assert (written, sorted(stat_evidence.load(project))) == (1, ["old.py"])


def test_record_replaces_and_empty_record_clears(project) -> None:
    stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)})
    stat_evidence.record(project, {"b.py": (_PAST, 12, _HASH)})
    assert sorted(stat_evidence.load(project)) == ["b.py"]

    stat_evidence.record(project, {})
    assert stat_evidence.load(project) == {}
    assert not os.path.exists(
        os.path.join(project, ".ast-cache", "evidence-memo", "stat-stamps.bin")
    )


def test_store_off_records_nothing(project, monkeypatch) -> None:
    monkeypatch.setenv("TSA_EVIDENCE_STORE", "off")
    assert stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)}) == 0
    monkeypatch.delenv("TSA_EVIDENCE_STORE")
    assert stat_evidence.load(project) == {}


def test_no_ast_cache_directory_records_nothing(tmp_path) -> None:
    assert stat_evidence.record(str(tmp_path), {"a.py": (_PAST, 10, _HASH)}) == 0
    assert stat_evidence.load(str(tmp_path)) == {}


@pytest.mark.parametrize(
    "payload",
    [
        b"not marshal",
        b"",
    ],
)
def test_corrupt_record_is_no_record(project, payload) -> None:
    stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)})
    path = os.path.join(project, ".ast-cache", "evidence-memo", "stat-stamps.bin")
    with open(path, "wb") as stream:
        stream.write(payload)

    assert stat_evidence.load(project) == {}


def test_record_of_another_root_is_no_record(project, tmp_path) -> None:
    import marshal

    stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)})
    path = os.path.join(project, ".ast-cache", "evidence-memo", "stat-stamps.bin")
    other = os.path.normcase(os.path.realpath(str(tmp_path / "elsewhere")))
    with open(path, "wb") as stream:
        stream.write(
            marshal.dumps(
                (stat_evidence.FORMAT, other, {"a.py": (_PAST, 10, _HASH)}), 4
            )
        )

    assert stat_evidence.load(project) == {}


def test_malformed_entries_are_no_record(project) -> None:
    import marshal

    stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)})
    path = os.path.join(project, ".ast-cache", "evidence-memo", "stat-stamps.bin")
    root = os.path.normcase(os.path.realpath(project))
    with open(path, "wb") as stream:
        stream.write(
            marshal.dumps((stat_evidence.FORMAT, root, {"a.py": (_PAST, 10, "")}), 4)
        )

    assert stat_evidence.load(project) == {}


def test_load_memo_hits_and_sees_a_replaced_record(project, monkeypatch) -> None:
    path = os.path.join(project, ".ast-cache", "evidence-memo", "stat-stamps.bin")
    stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)})
    os.utime(path, ns=(_PAST, _PAST))  # 记录文件出了竞争窗口：可以记忆
    assert sorted(stat_evidence.load(project)) == ["a.py"]
    reads: list[int] = []
    original = stat_evidence._read

    def counted(*args):
        reads.append(1)
        return original(*args)

    monkeypatch.setattr(stat_evidence, "_read", counted)
    assert sorted(stat_evidence.load(project)) == ["a.py"]
    assert reads == []  # 记忆命中
    stat_evidence.record(project, {"b.py": (_PAST, 10, _HASH)})
    assert sorted(stat_evidence.load(project)) == ["b.py"]  # 替换后重新读取


def test_effective_stamp_takes_the_live_stamp_only_when_vouched(project) -> None:
    stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)})
    stamps = stat_evidence.load(project)
    row = (1, 10, _HASH)

    assert stat_evidence.effective_stamp(stamps, "a.py", row, (_PAST, 10)) == (
        _PAST,
        10,
    )
    assert stat_evidence.effective_stamp(stamps, "a.py", row, (_PAST + 5, 10)) == (
        1,
        10,
    )
    assert stat_evidence.effective_stamp(stamps, "a.py", row, None) == (1, 10)


# ---- 读者 -------------------------------------------------------------------


def _touch_past(path: str) -> tuple[int, int]:
    with open(path, "rb") as stream:
        data = stream.read()
    with open(path, "wb") as stream:
        stream.write(data)
    os.utime(path, ns=(_PAST, _PAST))
    info = os.stat(path)
    return info.st_mtime_ns, info.st_size


def test_relation_freshness_uses_the_record_instead_of_reading(
    project, monkeypatch
) -> None:
    from tree_sitter_analyzer import incremental_sync_support
    from tree_sitter_analyzer.mcp.tools import relation_freshness

    path = os.path.join(project, "a.py")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write("x = 1\n")
    digest = incremental_sync_support.file_content_hash(path)
    live = _touch_past(path)
    reads: list[str] = []
    original = incremental_sync_support.file_content_hash

    def counted(target: str) -> str:
        reads.append(os.path.basename(target))
        return original(target)

    monkeypatch.setattr(incremental_sync_support, "file_content_hash", counted)
    rows = [("a.py", live[0] - 7, live[1], digest)]

    assert relation_freshness._changed_files(project, rows, None) == []
    assert reads == ["a.py"]  # 没有记录：按摘要比对
    stat_evidence.record(project, {"a.py": (*live, digest)})
    reads.clear()
    assert relation_freshness._changed_files(project, rows, None) == []
    assert reads == []  # 记录作证：不读文件
    # 记录的摘要与该行不同（行之后改过）：不作证，照常比对并判定为变更。
    stale_rows = [("a.py", live[0] - 7, live[1], "f" * 64)]
    assert relation_freshness._changed_files(project, stale_rows, None) == ["a.py"]


def test_reference_freshness_uses_the_record(project, monkeypatch) -> None:
    from tree_sitter_analyzer import incremental_sync_support
    from tree_sitter_analyzer.mcp.tools import callers_reference_freshness

    path = os.path.join(project, "a.py")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write("x = 1\n")
    digest = incremental_sync_support.file_content_hash(path)
    mtime, size = _touch_past(path)
    stat_evidence.record(project, {"a.py": (mtime, size, digest)})

    def no_read(_target: str) -> str:
        raise AssertionError("the record vouches; the file must not be read")

    monkeypatch.setattr(incremental_sync_support, "file_content_hash", no_read)
    stamp = (size, mtime, 0, 0, 0)

    assert (
        callers_reference_freshness._differs(
            path,
            stamp,
            (mtime - 7, size, digest),
            evidence=stat_evidence.load(project),
            rel_path="a.py",
        )
        is False
    )
    # 行的摘要与记录不同（行之后改过）：记录不作证，按摘要比对得出“已变更”。
    monkeypatch.setattr(
        incremental_sync_support, "file_content_hash", lambda _target: digest
    )
    assert (
        callers_reference_freshness._differs(
            path,
            stamp,
            (mtime - 7, size, "f" * 64),
            evidence=stat_evidence.load(project),
            rel_path="a.py",
        )
        is True
    )


def test_dependents_rows_vouched_by_the_record_are_fresh(project) -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils import dependents_index

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, mtime_ns INTEGER, "
        "file_size INTEGER, content_hash TEXT)"
    )
    conn.execute("INSERT INTO ast_index VALUES ('a.py', 1, 10, ?)", (_HASH,))
    conn.execute("INSERT INTO ast_index VALUES ('b.py', 1, 10, ?)", (_HASH,))
    inventory = {"a.py": (_PAST, 10), "b.py": (_PAST, 10)}
    stat_evidence.record(project, {"a.py": (_PAST, 10, _HASH)})

    from pathlib import Path

    assert dependents_index._fresh_rows(conn, inventory, Path(project)) == {"a.py"}
