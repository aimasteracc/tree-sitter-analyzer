"""#1602 剖析出的两处热点：单文件健康评分等待被丢弃的整图构建、逐文件全表孤儿注释扫描。

全部用调用计数或事件顺序断言，不依赖墙钟时间。
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

import tree_sitter_analyzer.health_scorer as health
from tests.unit._ast_cache_helpers import legacy_cache
from tree_sitter_analyzer.project_graph import DependencyGraph

_ORPHAN_SWEEP = "NOT EXISTS (SELECT 1 FROM ast_symbol_rows"


@pytest.fixture
def python_file(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("import os\n", encoding="utf-8")
    return path


def _blocked_builder(release: threading.Event, finished: list[bool]):
    def build(_root: str) -> object:
        release.wait(5.0)
        finished.append(True)
        return object()

    return build


def test_single_file_timeout_does_not_wait_for_discarded_graph(
    python_file, monkeypatch
) -> None:
    # #1602: 超时后已回退，单文件评分不得再等整图构建（实测占 health file 54/68 s）。
    release = threading.Event()
    finished: list[bool] = []
    monkeypatch.setattr(health, "_build_dep_graph", _blocked_builder(release, finished))
    monkeypatch.setattr(health, "_DEP_GRAPH_TIMEOUT_S", 0.01)
    try:
        score = health.score_dependencies(str(python_file))
        observed = list(finished)
    finally:
        release.set()

    assert (score, observed) == (100.0, [])


def test_project_scope_timeout_still_waits_to_warm_the_graph(
    python_file, monkeypatch
) -> None:
    # #1602: 项目评分保持原语义，等构建完成以预热进程级缓存，但不写入本次作用域。
    release = threading.Event()
    finished: list[bool] = []
    monkeypatch.setattr(health, "_build_dep_graph", _blocked_builder(release, finished))
    monkeypatch.setattr(health, "_DEP_GRAPH_TIMEOUT_S", 0.01)
    graphs: dict[str, object] = {}
    token = health._PROJECT_DEPENDENCY_GRAPHS.set(graphs)
    timer = threading.Timer(0.05, release.set)
    timer.start()
    try:
        score = health.score_dependencies(str(python_file))
        observed = list(finished)
    finally:
        release.set()
        timer.cancel()
        health._PROJECT_DEPENDENCY_GRAPHS.reset(token)

    assert (score, observed, graphs) == (100.0, [True], {})


def test_concurrent_caller_waits_for_in_flight_graph_build(
    tmp_path, monkeypatch
) -> None:
    # #1602: 后台构建继续运行时，同根的并发调用者不得拿到半成品图。
    started = threading.Event()
    release = threading.Event()

    def slow_build(self: DependencyGraph) -> None:
        started.set()
        release.wait(5.0)
        self._nodes.add("built.py")

    monkeypatch.setattr(DependencyGraph, "_build", slow_build)
    monkeypatch.setattr(DependencyGraph, "_global_cache", {})
    first = threading.Thread(target=DependencyGraph, args=(str(tmp_path),))
    first.start()
    assert started.wait(5.0)
    seen: list[bool] = []
    second = threading.Thread(
        target=lambda: seen.append("built.py" in DependencyGraph(str(tmp_path))._nodes)
    )
    second.start()
    second.join(1.0)
    release.set()
    first.join(5.0)
    second.join(5.0)

    assert seen == [True]


def _write_file(conn: sqlite3.Connection, rel_path: str) -> None:
    from tree_sitter_analyzer.cache.write import write_fts5_symbols_from_tuples

    write_fts5_symbols_from_tuples(
        conn, rel_path, "python", [("f", "function", 1, 2)], fts5_available=False
    )


def test_per_file_symbol_rewrite_does_not_scan_all_comments(tmp_path) -> None:
    # #1602: 逐文件孤儿扫描每次全表扫描注释（实测 2,433 文件累计 51 s）。
    cache = legacy_cache(str(tmp_path))
    try:
        conn = cache.get_conn()
        statements: list[str] = []
        conn.set_trace_callback(statements.append)
        for index in range(3):
            _write_file(conn, f"m{index}.py")
        conn.set_trace_callback(None)
        sweeps = [sql for sql in statements if _ORPHAN_SWEEP in sql]
    finally:
        cache.close()

    assert sweeps == []


def test_rewrite_still_removes_the_files_own_comments(tmp_path) -> None:
    # PR #1352 语义保留：替换文件后旧注释不得残留。
    cache = legacy_cache(str(tmp_path))
    try:
        conn = cache.get_conn()
        _write_file(conn, "m.py")
        symbol_id = conn.execute("SELECT id FROM ast_symbol_rows").fetchone()[0]
        conn.execute(
            "INSERT INTO ast_symbol_comments(symbol_id,line,text,kind) "
            "VALUES (?,1,'old','inline')",
            (symbol_id,),
        )
        _write_file(conn, "m.py")
        remaining = conn.execute("SELECT count(*) FROM ast_symbol_comments").fetchone()
    finally:
        cache.close()

    assert remaining[0] == 0


def test_pruning_unindexed_symbol_rows_also_drops_their_comments(tmp_path) -> None:
    # #1602: 孤儿只会在投影修复删除未入索引的符号行时产生，清扫随之移到那里。
    from tree_sitter_analyzer.cache.symbol_comments import (
        prune_unindexed_symbol_rows,
    )

    cache = legacy_cache(str(tmp_path))
    try:
        conn = cache.get_conn()
        _write_file(conn, "gone.py")
        symbol_id = conn.execute("SELECT id FROM ast_symbol_rows").fetchone()[0]
        conn.execute(
            "INSERT INTO ast_symbol_comments(symbol_id,line,text,kind) "
            "VALUES (?,1,'stale','inline')",
            (symbol_id,),
        )
        prune_unindexed_symbol_rows(conn)
        counts = (
            conn.execute("SELECT count(*) FROM ast_symbol_rows").fetchone()[0],
            conn.execute("SELECT count(*) FROM ast_symbol_comments").fetchone()[0],
        )
    finally:
        cache.close()

    assert counts == (0, 0)
