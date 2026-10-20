"""#1710：``call_graph_built`` 的记忆只在库文件 stat 证据未变时复用。"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.cache import call_graph_built_memo as memo

_AN_HOUR_NS = 3600 * 1_000_000_000


def _backdate(path: Path, offset_ns: int = _AN_HOUR_NS) -> None:
    stamp = time.time_ns() - offset_ns
    os.utime(path, ns=(stamp, stamp))


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "index.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(x)")
    conn.commit()
    conn.close()
    _backdate(path)
    memo.clear()
    yield path
    memo.clear()


def _counting(results: list[bool]):
    calls: list[int] = []

    def compute() -> bool:
        calls.append(1)
        return results[min(len(calls), len(results)) - 1]

    return compute, calls


def test_the_result_is_reused_while_the_stat_evidence_holds(database: Path) -> None:
    compute, calls = _counting([True])

    assert memo.memoized(str(database), compute) is True
    assert memo.memoized(str(database), compute) is True
    assert len(calls) == 1


def test_a_written_database_is_recomputed(database: Path) -> None:
    compute, calls = _counting([True, False])
    memo.memoized(str(database), compute)

    conn = sqlite3.connect(database)
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    _backdate(database, 2 * _AN_HOUR_NS)

    assert memo.memoized(str(database), compute) is False
    assert len(calls) == 2


def test_a_new_wal_file_is_recomputed(database: Path) -> None:
    compute, calls = _counting([True, False])
    memo.memoized(str(database), compute)
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"x")
    _backdate(wal)

    assert memo.memoized(str(database), compute) is False
    assert len(calls) == 2


def test_a_racy_database_is_never_memoized(database: Path) -> None:
    os.utime(database, None)  # mtime = now
    compute, calls = _counting([True])

    memo.memoized(str(database), compute)
    memo.memoized(str(database), compute)

    assert len(calls) == 2


def test_a_change_during_the_computation_is_not_reused(database: Path) -> None:
    calls: list[int] = []

    def compute() -> bool:
        calls.append(1)
        _backdate(database, (3 + len(calls)) * _AN_HOUR_NS)
        return True

    memo.memoized(str(database), compute)
    memo.memoized(str(database), compute)

    assert len(calls) == 2


def test_memory_and_unknown_databases_always_compute() -> None:
    compute, calls = _counting([True])

    memo.memoized(None, compute)
    memo.memoized(":memory:", compute)
    memo.memoized("", compute)

    assert len(calls) == 3


def test_an_unreadable_database_always_computes(tmp_path: Path) -> None:
    compute, calls = _counting([True])
    missing = tmp_path / "absent.db"

    memo.memoized(str(missing), compute)
    memo.memoized(str(missing), compute)

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_ast_cache_call_graph_built_follows_index_writes(tmp_path: Path) -> None:
    import stat as stat_module

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    return g()\n\n\ndef g():\n    return 1\n")
    result = await CodeGraphFullIndexTool(str(root)).execute({"mode": "full"})
    assert result["published"] is True
    database = Path(resolve_index_path(str(root)))
    _backdate(database)
    memo.clear()

    cache = ASTCache(str(root))
    try:
        assert cache.call_graph_built() is True
        assert cache.call_graph_built() is True
    finally:
        cache.close()

    os.chmod(database, stat_module.S_IREAD | stat_module.S_IWRITE)
    conn = sqlite3.connect(database)
    conn.execute("UPDATE ast_call_graph_state SET built = 0")
    conn.commit()
    conn.close()
    _backdate(database, 2 * _AN_HOUR_NS)

    cache = ASTCache(str(root))
    try:
        assert cache.call_graph_built() is False
    finally:
        cache.close()


def test_an_unstatable_database_always_computes(database: Path, monkeypatch) -> None:
    compute, calls = _counting([True])

    def refuse(*_args, **_kwargs):
        raise PermissionError

    monkeypatch.setattr(memo.os, "stat", refuse)
    memo.memoized(str(database), compute)
    memo.memoized(str(database), compute)

    assert len(calls) == 2


def test_the_memo_is_bounded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(memo, "MAX_ENTRIES", 2)
    paths = []
    for index in range(3):
        path = tmp_path / f"db{index}"
        path.write_bytes(b"x")
        _backdate(path)
        paths.append(str(path))
        memo.memoized(str(path), lambda: True)

    assert sorted(memo._MEMO) == sorted(os.path.abspath(p) for p in paths[1:])
