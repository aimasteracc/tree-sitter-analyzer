"""#1718 step 0（RFC-0039）：刷新不再给未变文件重写 ``ast_index.certified_at``。

旧行为：每次刷新把新增、更新**与未变**文件的 ``certified_at`` 都改成当前时间，
一次 1 文件刷新因此改写全部 ``ast_index`` 行（本仓库 2,565 行），任何增量认证都
无从谈起。读者只检查 ``certified_at`` 是否为 NULL，时间值本身没有读者，因此：

* 新增、更新的文件照常盖上本轮时间；
* 未变且已有认证的文件保留原值；
* 未变但为 NULL 的文件（尚未认证）补盖本轮时间。
"""

from __future__ import annotations

import sqlite3

import pytest


def _stamp_table() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT PRIMARY KEY, certified_at INTEGER)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("new.py", None),
            ("upd.py", 100),
            ("same.py", 100),
            ("null.py", None),
            ("err.py", 7),
        ],
    )
    return conn


def test_stamp_keeps_unchanged_files_and_fills_nulls() -> None:
    from tree_sitter_analyzer.incremental_sync_support import stamp_certified_at

    conn = _stamp_table()
    actions = {
        "new.py": "new",
        "upd.py": "updated",
        "same.py": "unchanged",
        "null.py": "unchanged",
        "err.py": "error",
    }

    stamp_certified_at(conn, actions, 500)

    assert dict(conn.execute("SELECT file_path, certified_at FROM ast_index")) == {
        "new.py": 500,
        "upd.py": 500,
        "same.py": 100,
        "null.py": 500,
        "err.py": 7,  # 错误文件由既有的清除路径处理，不在此盖戳
    }

    # 本轮没有成功处理的文件：不执行任何写入。
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    stamp_certified_at(conn, {"err.py": "error"}, 900)
    assert statements == []


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync

    cache = ASTCache(str(root))
    try:
        return IncrementalSync(cache).sync()
    finally:
        cache.close()


def _certified(root) -> dict[str, int | None]:
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(str(root))
    conn = sqlite3.connect(f"file:{location.path}?mode=ro", uri=True)
    try:
        return dict(conn.execute("SELECT file_path, certified_at FROM ast_index"))
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _fresh_guard():
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    auto_index_guard.reset()
    yield
    auto_index_guard.reset()


def test_one_file_refresh_rewrites_only_that_files_certified_at(
    tmp_path, monkeypatch
) -> None:
    import os

    from tree_sitter_analyzer import incremental_sync

    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text(
            f"def {name[0]}():\n    return 1\n", encoding="utf-8"
        )
    monkeypatch.setattr(incremental_sync.time, "time", lambda: 1_000_000_000.0)
    _sync(tmp_path)
    assert set(_certified(tmp_path).values()) == {1_000_000_000}

    (tmp_path / "a.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    info = os.stat(tmp_path / "a.py")
    os.utime(tmp_path / "a.py", ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
    monkeypatch.setattr(incremental_sync.time, "time", lambda: 2_000_000_000.0)
    result = _sync(tmp_path)

    assert result.updated_files == 1
    assert _certified(tmp_path) == {
        "a.py": 2_000_000_000,
        "b.py": 1_000_000_000,
        "c.py": 1_000_000_000,
    }


def test_an_empty_project_refresh_stamps_nothing(tmp_path) -> None:
    result = _sync(tmp_path)
    assert (result.new_files, result.updated_files, result.errors) == (0, 0, 0)
