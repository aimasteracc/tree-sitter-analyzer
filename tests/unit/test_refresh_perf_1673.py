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
