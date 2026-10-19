"""#1673：刷新路径成本削减的失败与平台分支。

* 并发摘要绑定：不可读文件记为标记、其余照常绑定；整批字节预算越界是类型化
  失败；意外异常原样上抛，不被吞成预算失败。
* 封存父版本的字节复制：复制期间父版本变化时退回 backup，目标恢复为空库文件。
* Windows 变更时间：原生读取失败时为 ``None``（不得复用摘要）。
* Windows 目录级 realpath 与校验阶段的 lstat 复用（在任何平台上按 Windows 分支
  运行，真实文件系统）。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from tree_sitter_analyzer import file_change_time, indexing_snapshot, source_hash_cache
from tree_sitter_analyzer.cache import generation_store
from tree_sitter_analyzer.cache.generation_store import GenerationStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    for name in ("a", "b", "c"):
        (root / f"{name}.py").write_text(f"def {name}(): return 1\n", encoding="utf-8")
    monkeypatch.setattr(generation_store, "_PATH_ONLY_SOURCE", True)
    monkeypatch.setattr(
        source_hash_cache, "SOURCE_HASHES", source_hash_cache.SourceHashCache()
    )
    return GenerationStore(str(root), str(tmp_path / "storage"))


def test_unreadable_file_is_bound_as_a_marker(store, monkeypatch) -> None:
    from tree_sitter_analyzer import index_source_stream
    from tree_sitter_analyzer.index_source_stream import (
        SourceUnreadable,
        unreadable_source_reason,
    )

    original = index_source_stream.hash_source_at

    def locked_b(directory_fd, name, *args, **kwargs):
        if os.path.basename(name) == "b.py":
            raise SourceUnreadable(PermissionError(13, "locked by another process"))
        return original(directory_fd, name, *args, **kwargs)

    monkeypatch.setattr(index_source_stream, "hash_source_at", locked_b)

    bound = generation_store._bind_source_hashes(store._snapshot())
    digests = {
        entry.rel_path: entry.fingerprint.content_hash
        for entry in bound.selected_entries
    }

    assert (
        unreadable_source_reason(digests["b.py"]) is not None,
        len(digests["a.py"]),
        len(digests["c.py"]),
    ) == (True, 64, 64)


def test_batch_byte_budget_is_a_typed_failure(store, monkeypatch) -> None:
    monkeypatch.setattr(generation_store, "SOURCE_HASH_BYTE_BUDGET", 30)

    with pytest.raises(generation_store.SourceHashBudgetExceeded) as caught:
        generation_store._bind_source_hashes(store._snapshot())

    assert caught.value.selected == 3


def test_unexpected_binding_error_is_not_reported_as_budget(store, monkeypatch):
    from tree_sitter_analyzer import index_source_stream

    def broken(*_args, **_kwargs):
        raise ZeroDivisionError("bug in a hash routine")

    monkeypatch.setattr(index_source_stream, "hash_source_at", broken)

    with pytest.raises(ZeroDivisionError):
        generation_store._bind_source_hashes(store._snapshot())


def _sqlite_file(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE t (v TEXT)")
        connection.execute("INSERT INTO t VALUES ('x')")
        connection.commit()
    finally:
        connection.close()


def test_parent_that_changes_during_the_copy_falls_back(tmp_path, monkeypatch):
    parent = tmp_path / "parent.db"
    _sqlite_file(parent)
    private = tmp_path / "private.db"
    private.touch()
    real_stat = os.stat
    calls: list[str] = []

    def drifting(path, *args, **kwargs):
        info = real_stat(path, *args, **kwargs)
        if str(path) == str(parent):
            calls.append("stat")
            if len(calls) == 2:  # 复制之后再取：模拟父版本被改写
                return os.stat_result((*info[:8], info.st_mtime + 1, info[9]))
        return info

    monkeypatch.setattr(generation_store.os, "stat", drifting)

    assert (
        generation_store._copy_sealed_database(parent, private),
        os.path.getsize(private),
    ) == (False, 0)


def test_windows_change_time_failure_means_no_reuse(tmp_path, monkeypatch) -> None:
    path = tmp_path / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    info = os.lstat(path)
    monkeypatch.setattr(file_change_time, "IS_WINDOWS", True)

    def denied(_path):
        raise PermissionError(5, "access denied")

    monkeypatch.setattr(file_change_time, "_windows_change_time_ns", denied)
    failed = file_change_time.change_time_ns(str(path), info)
    monkeypatch.setattr(file_change_time, "_windows_change_time_ns", lambda _p: 42)

    assert (
        failed,
        source_hash_cache.evidence(str(path), info),
        file_change_time.change_time_ns(str(path), info),
    ) == (None, source_hash_cache.stat_key(info, 42), 42)


def test_cache_clear_forgets_entries_and_counters(monkeypatch) -> None:
    cache = source_hash_cache.SourceHashCache()
    info = os.stat(__file__)
    key = source_hash_cache.stat_key(info, int(info.st_mtime_ns))
    monkeypatch.setattr(source_hash_cache, "_now_ns", lambda: 2**62)
    cache.store("a", key, "d" * 64)
    cache.lookup("a", key)
    cache.lookup("b", key)
    cache.clear()

    # 计数在最后一次查找之前读取：clear 之后为零。
    assert (len(cache), cache.hits, cache.misses, cache.lookup("a", key)) == (
        0,
        0,
        0,
        None,
    )


@pytest.fixture
def windows_paths(monkeypatch):
    monkeypatch.setattr(indexing_snapshot, "_IS_WINDOWS", True)


def _snapshot(root: Path):
    from tree_sitter_analyzer.constants import EXCLUDE_DIRS
    from tree_sitter_analyzer.project_graph import _language_from_ext

    return indexing_snapshot.build_index_candidate_snapshot(
        str(root),
        max_files=100,
        exclude_patterns=frozenset(),
        walk_fn=lambda r: indexing_snapshot.walk_index_candidate_entries(
            r, excluded_dir_names=frozenset(EXCLUDE_DIRS)
        ),
        language_fn=_language_from_ext,
    )


def test_windows_route_snapshot_matches_realpath(tmp_path, windows_paths) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "top.py").write_text("y = 2\n", encoding="utf-8")
    directories: dict[str, str] = {}
    paths = [tmp_path / "pkg" / "m.py", tmp_path / "top.py"]

    resolved = [
        indexing_snapshot._realpath_of_regular_file(str(p), os.lstat(p), directories)
        for p in paths
    ]
    snapshot = _snapshot(tmp_path)
    indexing_snapshot.validate_index_candidate_snapshot(str(tmp_path), 100, snapshot)

    assert (resolved, sorted(e.rel_path for e in snapshot.selected_entries)) == (
        [os.path.realpath(p) for p in paths],
        ["pkg/m.py", "top.py"],
    )


def test_windows_route_validation_skips_deleted_entries(tmp_path, windows_paths):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    snapshot = _snapshot(tmp_path)
    (tmp_path / "b.py").unlink()

    # 删除由 changed_since_snapshot 报告；校验本身不失败。
    indexing_snapshot.validate_index_candidate_snapshot(str(tmp_path), 100, snapshot)


def test_windows_route_validation_rejects_a_non_regular_entry(
    tmp_path, windows_paths
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    snapshot = _snapshot(tmp_path)
    (tmp_path / "a.py").unlink()
    (tmp_path / "a.py").mkdir()

    with pytest.raises(ValueError, match="symlinked or non-regular"):
        indexing_snapshot.validate_index_candidate_snapshot(
            str(tmp_path), 100, snapshot
        )
