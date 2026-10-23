"""#1708：长驻进程在发布新版本时就为它构图，发布后的第一次调用不再逐边解析。

dogfood 第 9 轮：长驻 MCP 服务器里，发布刷新之后的第一次 ``nav callers`` 要
7.5–16 s（新启动进程 5.6 s）。构图输入变了，#1663 的内存记忆与 #1675 的落盘解析
按输入摘要都未命中，第一次调用付出约 19 万条边的整份解析。修复后发布的同一进程
在后台线程构图（``call_graph_warm``），刷新立即返回；之后新建的图按同一摘要命中
（构建期间到达的调用等待这次在途构建），且与全新构建逐字段相同。
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

from tree_sitter_analyzer import (
    call_graph,
    call_graph_memo,
    call_graph_store,
    call_graph_warm,
)
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.call_graph import CachedCallGraph

_SOURCES = {
    "pkg/__init__.py": "from .core import helper\n",
    "pkg/core.py": (
        "def helper(x):\n    return x + 1\n\n"
        "class Engine:\n"
        "    def run(self):\n        return self.step() + helper(1)\n\n"
        "    def step(self):\n        return 2\n"
    ),
    "app.py": (
        "from pkg.core import Engine, helper\n\n"
        "def main():\n    e = Engine()\n    e.run()\n    return helper(3)\n"
    ),
}
_EDITED_APP = _SOURCES["app.py"] + "\n\ndef extra():\n    return helper(4) + main()\n"


@pytest.fixture
def project(tmp_path):
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    for rel, text in _SOURCES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    auto_index_guard.reset()
    call_graph_memo.clear()
    call_graph_warm.disable()
    yield str(tmp_path)
    call_graph_warm.wait(timeout=60)
    call_graph_warm.disable()
    call_graph_memo.clear()
    auto_index_guard.reset()


@pytest.fixture
def resolutions(monkeypatch):
    """记录逐边解析的次数（落盘重放与记忆命中都不经过它）。"""
    seen: list[int] = []
    original = call_graph._resolve_edge

    def counted(*args, **kwargs):
        seen.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(call_graph, "_resolve_edge", counted)
    return seen


def _refresh(root: str, *, settle: bool = True, watcher: bool = True) -> dict:
    """刷新；缺省如同监视器驱动（预构图只为监视器驱动的刷新运行）。"""
    cache = ASTCache(root)
    try:
        if watcher:
            with call_graph_warm.watcher_refresh():
                result = cache.index_project(workers=0)
        else:
            result = cache.index_project(workers=0)
    finally:
        cache.close()
    if settle:
        # 后台构建结束后再断言（并发行为另有专门的测试）。
        assert call_graph_warm.wait(timeout=60) is True
    return result


def _edit(root: str) -> None:
    path = os.path.join(root, "app.py")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(_EDITED_APP)
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))


def _graph(root: str, *, persist: bool = True) -> CachedCallGraph:
    cache = ASTCache(root)
    graph = CachedCallGraph(root, cache=cache, fallback=False, persist=persist)
    try:
        graph.build()
    finally:
        cache.close()
    assert graph.is_built
    return graph


def _key(ref):
    return (
        ref.file_path,
        ref.name,
        ref.start_line,
        ref.end_line,
        ref.language,
        ref.receiver,
    )


def _snapshot(graph: CachedCallGraph) -> dict:
    def adj(mapping):
        return {_key(k): [_key(v) for v in vs] for k, vs in mapping.items()}

    return {
        "functions": [_key(r) for r in graph._functions],
        "callees": adj(graph._callees),
        "callers": adj(graph._callers),
        "possible_callees": adj(graph._possible_callees),
        "possible_callers": adj(graph._possible_callers),
        "call_edges": [(_key(a), _key(b), line) for a, b, line in graph._call_edges],
        "edge_bindings": dict(graph._edge_bindings),
    }


def _fresh_snapshot(root: str) -> dict:
    """全新构建：清空进程内记忆并移走落盘结果后从索引行构图。"""
    call_graph_memo.clear()
    directory = Path(root) / ".ast-cache" / call_graph_store.DIR_NAME
    for path in directory.glob("*.bin"):
        path.unlink()
    return _snapshot(_graph(root, persist=False))


def test_first_graph_after_a_publishing_refresh_does_not_resolve(
    project, resolutions
) -> None:
    call_graph_warm.enable()
    assert _refresh(project)["published"] is True
    _edit(project)
    result = _refresh(project)
    resolutions.clear()

    graph = _graph(project)

    # 发布后已在后台构图：其后新建的图按输入摘要命中，不再逐边解析。
    assert (
        result["published"],
        result["call_graph_warm"]["scheduled"],
        call_graph_warm.last_outcome(project)["warmed"],
        resolutions,
    ) == (True, True, True, [])
    # 命中的状态与全新构建逐字段相同（包括编辑新增的调用）。
    warm = _snapshot(graph)
    assert warm == _fresh_snapshot(project)
    assert any(edge[0][1] == "extra" for edge in warm["call_edges"])


def test_warm_persists_the_resolutions_for_a_cold_process(project, resolutions) -> None:
    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    _refresh(project)
    call_graph_memo.clear()  # 新进程：没有进程内记忆
    resolutions.clear()

    _graph(project)

    assert resolutions == []  # 重放发布时写下的落盘结果


def test_without_enable_the_first_graph_resolves(project, resolutions) -> None:
    # 一次性进程（CLI、测试）默认不预构图：刷新不会因此变慢。
    _refresh(project)
    _edit(project)
    result = _refresh(project)
    resolutions.clear()

    _graph(project)

    assert ("call_graph_warm" in result, bool(resolutions)) == (False, True)


def test_env_off_disables_the_warm(project, resolutions, monkeypatch) -> None:
    call_graph_warm.enable()
    monkeypatch.setenv(call_graph_warm.ENV_VAR, "off")
    _refresh(project)
    _edit(project)
    _refresh(project)
    resolutions.clear()

    _graph(project)

    assert resolutions


def test_unpublished_refresh_does_not_warm(project, monkeypatch) -> None:
    call_graph_warm.enable()
    _refresh(project)
    _refresh(project)  # 第二次：带收敛记录
    calls: list[str] = []
    monkeypatch.setattr(call_graph_warm, "after_publish", calls.append)

    result = _refresh(project)

    assert (result["published"], calls) == (False, [])


def test_warm_failure_does_not_fail_the_refresh(project, monkeypatch) -> None:
    call_graph_warm.enable()

    def broken(self):
        raise RuntimeError("graph build failed for the test")

    monkeypatch.setattr(CachedCallGraph, "build", broken)
    result = _refresh(project)

    # 构建失败只记日志：刷新已发布，结果记为未预构图。
    assert (
        result["published"],
        result["call_graph_warm"]["scheduled"],
        call_graph_warm.last_outcome(project)["warmed"],
    ) == (True, True, False)


def test_sync_route_warms(project, resolutions) -> None:
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    scope = make_source_scope_descriptor()
    cache = ASTCache(project)
    try:
        with call_graph_warm.watcher_refresh():
            synced = IncrementalSync(cache).sync(
                max_files=scope.certification_max_files,
                exclude_patterns=scope.effective_excludes,
                source_scope=scope,
            )
    finally:
        cache.close()
    assert call_graph_warm.wait(timeout=60) is True
    resolutions.clear()

    _graph(project)

    assert (synced.published, resolutions) == (True, [])


def test_full_index_warms(project, resolutions) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    call_graph_warm.enable()
    with call_graph_warm.watcher_refresh():
        result = asyncio.run(CodeGraphFullIndexTool(project).execute({"mode": "full"}))
    assert call_graph_warm.wait(timeout=60) is True
    resolutions.clear()

    _graph(project)

    assert (
        result["published"],
        result["call_graph_warm"]["scheduled"],
        resolutions,
    ) == (
        True,
        True,
        [],
    )


def test_mcp_server_main_enables_the_warm(monkeypatch) -> None:
    from tree_sitter_analyzer.mcp import server as server_module

    class _Server:
        def __init__(self, project_root):
            self.project_root = project_root

        async def run(self):
            return None

    call_graph_warm.disable()
    monkeypatch.setattr(server_module, "TreeSitterAnalyzerMCPServer", _Server)
    try:
        with pytest.raises(SystemExit):
            asyncio.run(server_module.main())
        assert call_graph_warm.enabled() is True
    finally:
        call_graph_warm.disable()


def _blocking_warm(monkeypatch):
    """让后台构建停在第一条边的解析上，直到放行；按线程名统计解析次数。"""
    gate, started = threading.Event(), threading.Event()
    per_thread: Counter[str] = Counter()
    original = call_graph._resolve_edge

    def slow(*args, **kwargs):
        name = threading.current_thread().name
        per_thread[name] += 1
        if name == "tsa-call-graph-warm":
            started.set()
            gate.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(call_graph, "_resolve_edge", slow)
    return gate, started, per_thread


def test_refresh_returns_before_the_background_build_finishes(
    project, monkeypatch
) -> None:
    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    gate, started, _per_thread = _blocking_warm(monkeypatch)
    try:
        result = _refresh(project, settle=False)

        # 刷新答复不等构图：此时后台构建仍停在解析上。
        assert started.wait(30) is True
        assert (result["published"], result["call_graph_warm"]["scheduled"]) == (
            True,
            True,
        )
        assert call_graph_warm.wait(project, timeout=0.2) is False
    finally:
        gate.set()
    assert call_graph_warm.wait(timeout=60) is True
    assert call_graph_warm.last_outcome(project)["warmed"] is True


def test_concurrent_first_call_waits_for_the_in_flight_build(
    project, monkeypatch
) -> None:
    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    gate, started, per_thread = _blocking_warm(monkeypatch)
    built: dict[str, CachedCallGraph] = {}
    caller = threading.Thread(
        target=lambda: built.update(graph=_graph(project)), name="nav-call"
    )
    try:
        _refresh(project, settle=False)
        assert started.wait(30) is True
        caller.start()
        caller.join(1.0)
        # 第一次调用在等在途构建（同一输入摘要），没有自己开始解析。
        assert (caller.is_alive(), per_thread["nav-call"]) == (True, 0)
    finally:
        gate.set()
    caller.join(60)
    assert call_graph_warm.wait(timeout=60) is True

    # 只构建了一次（后台线程），调用方采用它的结果，且与全新构建相同。
    assert (caller.is_alive(), per_thread["nav-call"]) == (False, 0)
    assert set(per_thread) == {"tsa-call-graph-warm"}
    assert _snapshot(built["graph"]) == _fresh_snapshot(project)


def test_claim_waits_only_for_the_same_input_digest() -> None:
    root = "/project-1708"
    try:
        assert call_graph_memo.claim(root, "digest-a") is None
        # 另一个版本（摘要不同）的构建不等待。
        assert call_graph_memo.claim(root, "digest-b") is None
        pending = call_graph_memo.claim(root, "digest-a")
        assert pending is not None and pending.is_set() is False
        call_graph_memo.release(root, "digest-a")
        assert pending.is_set() is True
        assert call_graph_memo.claim(root, "digest-a") is None
    finally:
        for digest in ("digest-a", "digest-b"):
            call_graph_memo.release(root, digest)


def test_shutdown_stops_scheduling_and_bounds_the_wait(project, monkeypatch) -> None:
    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    gate, started, _per_thread = _blocking_warm(monkeypatch)
    try:
        _refresh(project, settle=False)
        assert started.wait(30) is True
        began = time.monotonic()
        finished = call_graph_warm.shutdown(timeout=0.3)
        elapsed = time.monotonic() - began
        # 在途构建未结束：在预算内返回（不挂住停止），之后不再调度新构建。
        assert (finished, elapsed < 5.0) == (False, True)
        assert call_graph_warm.after_publish(project) is None
    finally:
        gate.set()
    assert call_graph_warm.wait(timeout=60) is True


def test_server_stop_shuts_the_warm_down(monkeypatch) -> None:
    from tree_sitter_analyzer.mcp import server as server_module

    calls: list[float] = []
    monkeypatch.setattr(call_graph_warm, "shutdown", lambda *a, **k: calls.append(1))
    server = server_module.TreeSitterAnalyzerMCPServer(None)

    async def no_loop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(server, "_run_server_loop", no_loop)
    monkeypatch.setattr(server, "create_server", lambda: object())
    try:
        asyncio.run(server.run())
    except Exception:  # noqa: BLE001 — 只关心停止路径是否收尾
        pass

    assert calls == [1]


def test_graph_after_the_warm_does_not_reread_the_rows(project, monkeypatch) -> None:
    # 同一库、身份未变：直接采用预构图的结果，不再读行、算摘要（第一次调用的大头）。
    from tree_sitter_analyzer.cache import graph_input_rows

    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    _refresh(project)
    reads: list[int] = []
    original = graph_input_rows.read_edge_source

    def counted(*args, **kwargs):
        reads.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(graph_input_rows, "read_edge_source", counted)

    graph = _graph(project)

    assert reads == []
    assert _snapshot(graph) == _fresh_snapshot(project)


def test_changed_database_identity_is_not_adopted(project, monkeypatch) -> None:
    # 身份与预构图时不同（库被改动）：不采用，照常读行并按输入摘要判定。
    from tree_sitter_analyzer.cache import graph_input_rows

    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    _refresh(project)
    original_identity = call_graph_warm.database_identity
    monkeypatch.setattr(
        call_graph_warm,
        "database_identity",
        lambda database: (*(original_identity(database) or ()), "changed"),
    )
    reads: list[int] = []
    original = graph_input_rows.read_edge_source

    def counted(*args, **kwargs):
        reads.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(graph_input_rows, "read_edge_source", counted)

    graph = _graph(project)

    assert reads == [1]
    assert _snapshot(graph) == _fresh_snapshot(project)


def test_a_call_on_another_database_does_not_wait(project, monkeypatch) -> None:
    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    gate, started, _per_thread = _blocking_warm(monkeypatch)
    try:
        _refresh(project, settle=False)
        assert started.wait(30) is True
        began = time.monotonic()
        # 另一个库（另一个版本或快照）：不等在途的预构图。
        assert call_graph_warm.adopt(project, os.path.join(project, "other.db")) is None
        assert time.monotonic() - began < 5.0
    finally:
        gate.set()
    assert call_graph_warm.wait(timeout=60) is True


def test_explicit_refresh_does_not_warm(project, resolutions) -> None:
    # 客户端显式刷新与 develop 相同：不在后台构图，第一次调用照常构图。
    call_graph_warm.enable()
    _refresh(project, watcher=False)
    _edit(project)
    result = _refresh(project, watcher=False)
    resolutions.clear()

    _graph(project)

    assert ("call_graph_warm" in result, bool(resolutions)) == (False, True)


def test_always_override_warms_explicit_refreshes(
    project, resolutions, monkeypatch
) -> None:
    call_graph_warm.enable()
    monkeypatch.setenv(call_graph_warm.ENV_VAR, "always")
    _refresh(project, watcher=False)
    _edit(project)
    result = _refresh(project, watcher=False)
    resolutions.clear()

    _graph(project)

    assert (result["call_graph_warm"]["scheduled"], resolutions) == (True, [])


def test_file_watcher_sync_warms_the_published_generation(project, resolutions) -> None:
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    call_graph_warm.enable()
    _refresh(project, watcher=False)
    _edit(project)
    cache = ASTCache(project)
    watcher = FileWatcherDaemon(cache, poll_interval=1, debounce=0)
    try:
        watcher.trigger_sync()
    finally:
        watcher.stop()
        cache.close()
    assert call_graph_warm.wait(timeout=60) is True
    resolutions.clear()

    graph = _graph(project)

    # 监视器驱动的发布已在后台构图：第一次调用直接采用，不再逐边解析。
    assert (call_graph_warm.last_outcome(project)["warmed"], resolutions) == (True, [])
    assert any(edge[0][1] == "extra" for edge in _snapshot(graph)["call_edges"])


def test_publish_during_an_in_flight_build_queues_one_rebuild(
    project, monkeypatch
) -> None:
    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    gate, started, per_thread = _blocking_warm(monkeypatch)
    try:
        _refresh(project, settle=False)
        assert started.wait(30) is True
        # 在途构建期间又一次发布：不并行启动第二个线程，结束后再为活动版本构图。
        with call_graph_warm.watcher_refresh():
            again = call_graph_warm.after_publish(project)
        assert (again["scheduled"], again["queued"], again["incremental"]) == (
            True,
            True,
            False,
        )
    finally:
        gate.set()
    assert call_graph_warm.wait(timeout=60) is True
    resolutions_per_build = per_thread["tsa-call-graph-warm"]
    assert call_graph_warm.last_outcome(project)["warmed"] is True
    # 第二次构建按摘要命中第一次的结果（输入未变），没有再逐边解析。
    assert per_thread["tsa-call-graph-warm"] == resolutions_per_build


def test_database_identity_refuses_unsealed_or_missing_databases(tmp_path) -> None:
    import sqlite3

    database = tmp_path / "index.db"
    conn = sqlite3.connect(database)
    conn.execute("CREATE TABLE ast_index (file_path TEXT, indexed_at TEXT)")
    conn.execute("CREATE TABLE edges (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    identity = call_graph_warm.database_identity(str(database))
    assert identity is not None and identity[4:] == ((0, ""), (0,))
    # 有 WAL 旁路文件（未封存、可能有未检查点的页）、不存在或不是库：不复用。
    (tmp_path / "index.db-wal").write_bytes(b"")
    assert call_graph_warm.database_identity(str(database)) is None
    assert call_graph_warm.database_identity(str(tmp_path / "missing.db")) is None
    assert call_graph_warm.database_identity(None) is None


def test_adoption_falls_back_when_the_memo_was_released(project, resolutions) -> None:
    call_graph_warm.enable()
    _refresh(project)
    _edit(project)
    _refresh(project)
    call_graph_memo.clear()  # 记忆已释放（例如别的项目根挤出）：照常构图或重放
    resolutions.clear()

    graph = _graph(project)

    assert _snapshot(graph) == _fresh_snapshot(project)


def test_waiter_builds_itself_when_the_owner_stores_nothing(
    project, resolutions
) -> None:
    # 认领者结束却没有留下结果（构建失败）：等待者唤醒后自行构建，结果正确。
    _refresh(project, watcher=False)
    first = _graph(project, persist=False)
    digest = first._input_digest
    root = str(first.project_root)
    call_graph_memo.clear()
    assert call_graph_memo.claim(root, digest) is None
    releaser = threading.Timer(0.5, call_graph_memo.release, args=(root, digest))
    releaser.start()
    resolutions.clear()
    try:
        graph = _graph(project, persist=False)
    finally:
        releaser.join()

    assert bool(resolutions) is True
    assert _snapshot(graph) == _snapshot(first)
