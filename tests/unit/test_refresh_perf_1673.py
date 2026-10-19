"""#1673：刷新路径的成本削减不得改变结果。

* 封存父版本按字节复制成私有副本：内容与 backup 相同、保持 ``begin`` 记录的文件
  身份；父版本带旁路文件时退回 backup。
* 一次项目索引运行只校验候选快照一次（Windows 上每项 ``realpath`` 要开句柄）。
* 普通文件的 realpath 由其目录的 realpath 拼接得到，结果与 ``realpath`` 相同；
  目录联接（junction）仍被解析，越出根目录的路径照常被识别。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess

import pytest

from tree_sitter_analyzer.cache import generation_store
from tree_sitter_analyzer.indexing_snapshot import _realpath_of_regular_file


def test_directory_level_realpath_matches_realpath(tmp_path) -> None:
    nested = tmp_path / "Pkg" / "Sub"
    nested.mkdir(parents=True)
    paths = [nested / "Mod.py", tmp_path / "Pkg" / "x.py", tmp_path / "top.py"]
    for path in paths:
        path.write_text("x = 1\n", encoding="utf-8")
    directories: dict[str, str] = {}

    resolved = [
        _realpath_of_regular_file(str(p), os.lstat(p), directories) for p in paths
    ]

    assert resolved == [os.path.realpath(p) for p in paths]


@pytest.mark.skipif(os.name != "nt", reason="NTFS 目录联接（junction）仅 Windows")
def test_junction_directory_still_resolves_outside_the_root(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.py").write_text("x = 1\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "link"), str(outside)],
        check=True,
        capture_output=True,
    )
    target = root / "link" / "a.py"

    resolved = _realpath_of_regular_file(str(target), os.lstat(target), {})

    assert (resolved, resolved.startswith(str(root))) == (
        os.path.realpath(target),
        False,
    )


def _database(path, rows: int) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        connection.executemany(
            "INSERT INTO t (v) VALUES (?)", [(f"value-{n}" * 20,) for n in range(rows)]
        )
        connection.commit()
    finally:
        connection.close()


def _dump(path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return list(connection.iterdump())
    finally:
        connection.close()


def test_sealed_parent_is_copied_byte_for_byte_into_the_same_file(tmp_path) -> None:
    parent = tmp_path / "parent.db"
    _database(parent, 5000)
    private = tmp_path / "private.db"
    private.touch()
    identity = os.stat(private).st_ino

    copied = generation_store._copy_sealed_database(parent, private)

    assert (
        copied,
        os.stat(private).st_ino == identity,
        private.read_bytes() == parent.read_bytes(),
        _dump(private) == _dump(parent),
    ) == (True, True, True, True)


def test_parent_with_a_sidecar_falls_back_to_backup(tmp_path) -> None:
    parent = tmp_path / "parent.db"
    _database(parent, 10)
    (tmp_path / "parent.db-wal").write_bytes(b"")
    private = tmp_path / "private.db"
    private.touch()

    assert (
        generation_store._copy_sealed_database(parent, private),
        os.path.getsize(private),
    ) == (False, 0)


def test_index_run_validates_the_candidate_once(tmp_path, monkeypatch) -> None:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import indexer, indexer_io

    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    calls: list[str] = []
    original = indexer_io.validate_index_candidate_snapshot

    def counted(*args, **kwargs):
        calls.append("validate")
        return original(*args, **kwargs)

    monkeypatch.setattr(indexer_io, "validate_index_candidate_snapshot", counted)
    monkeypatch.setattr(indexer, "validate_index_candidate_snapshot", counted)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(workers=0)
    finally:
        cache.close()

    # 发布侧捕获之外，私有副本上的运行只校验一次（原为两次）。
    assert calls == ["validate"]


def test_a_slow_projection_check_does_not_rewrite_every_file(tmp_path, monkeypatch):
    # 写入方核验符号投影不用读者的 5 秒期限：未核完被当作“不精确”会重写全部
    # 文件的投影（负载下一次 1 文件刷新曾因此重新提取 2,504 个文件）。
    from tree_sitter_analyzer import index_symbol_projection
    from tree_sitter_analyzer.ast_cache import ASTCache

    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.py").write_text(
            f"def {name}():\n    return 1\n", encoding="utf-8"
        )
    database = tmp_path / "custom" / "index.db"
    database.parent.mkdir()
    cache = ASTCache(str(tmp_path), str(database))
    try:
        assert cache.index_project(workers=0)["indexed"] == 3
        monkeypatch.setattr(index_symbol_projection, "_PROJECTION_SECONDS", 0.0)
        second = cache.index_project(workers=0)
    finally:
        cache.close()

    assert (second["indexed"], second["cached"]) == (0, 3)


def _published_symbols(root) -> list[str]:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    path = resolve_index_location(str(root)).path
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        return [r[0] for r in connection.execute("SELECT name FROM ast_symbol_rows")]
    finally:
        connection.close()


@pytest.mark.parametrize("route", ["index_project", "sync"])
def test_same_size_same_mtime_rewrite_is_reindexed(tmp_path, route) -> None:
    # 路径平台的候选快照不带摘要：缓存判定若只看 mtime 与大小，等长改写并恢复
    # mtime 的文件会保留旧行（RFC-0030 要求内容证据）。捕获绑定的摘要必须参与判定。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    target = tmp_path / "b.py"
    target.write_bytes(b"def beta():\n    return 3\n")
    (tmp_path / "a.py").write_bytes(b"def alpha():\n    return 1\n")
    scope = make_source_scope_descriptor()

    def refresh() -> None:
        cache = ASTCache(str(tmp_path))
        try:
            if route == "index_project":
                cache.index_project(workers=0)
            else:
                IncrementalSync(cache).sync(
                    max_files=scope.certification_max_files,
                    exclude_patterns=scope.effective_excludes,
                    source_scope=scope,
                )
        finally:
            cache.close()

    refresh()
    info = os.stat(target)
    target.write_bytes(b"def betb():\n    return 3\n")
    os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns))
    refresh()

    assert sorted(_published_symbols(tmp_path)) == ["alpha", "betb"]


def test_sync_compares_with_the_digests_bound_at_capture(tmp_path, monkeypatch):
    # 同步路由不为比较重读每个文件：捕获已逐文件摘要（路径平台）。
    from tree_sitter_analyzer import incremental_sync_support
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import generation_store
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    monkeypatch.setattr(generation_store, "_PATH_ONLY_SOURCE", True)
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.py").write_bytes(f"def {name}():\n    return 1\n".encode())
    scope = make_source_scope_descriptor()
    reads: list[str] = []
    original = incremental_sync_support.file_content_hash

    def counted(path):
        reads.append(path)
        return original(path)

    def sync() -> None:
        cache = ASTCache(str(tmp_path))
        try:
            IncrementalSync(cache).sync(
                max_files=scope.certification_max_files,
                exclude_patterns=scope.effective_excludes,
                source_scope=scope,
            )
        finally:
            cache.close()

    sync()
    (tmp_path / "a.py").write_bytes(b"def a2():\n    return 2\n")
    monkeypatch.setattr(incremental_sync_support, "file_content_hash", counted)
    sync()

    assert (reads, sorted(_published_symbols(tmp_path))) == ([], ["a2", "b", "c"])
