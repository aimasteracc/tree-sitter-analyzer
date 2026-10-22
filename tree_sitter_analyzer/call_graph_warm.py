"""长驻进程在发布新版本后立即构建调用图（#1708）。

dogfood 第 9 轮：长驻 MCP 服务器里，发布刷新之后的第一次 ``nav callers`` 要
7.5–16 s，比新启动进程的第一次调用（5.6 s）还慢。剖析（develop ``ae7cd190``，
本仓库副本，长驻进程内 3 次“编辑 1 个文件 → 刷新 → 第一次调用”）：

* 第一次调用 11.3 / 20.1 / 13.8 s，其中 ``CachedCallGraph._build_from_cache``
  10.2 / 19.2 / 12.5 s：读边 1.7–4.6 s、输入摘要 0.5–1.2 s、物化 1.0–1.5 s、
  **逐边解析约 19 万条边 5.3–8.7 s**、落盘解析结果 0.9–1.7 s；完整性证据只有 0.3 s。
* 构图输入变了（一个文件被编辑），#1663 的内存记忆与 #1675 的落盘解析都按输入
  摘要取用，必然未命中，于是第一次调用付出整份解析。新进程之所以快，是因为它
  重放的正是长驻进程在自己的第一次调用里刚写下的落盘结果。

修复：发布刷新的同一进程在发布、释放写锁之后，在**后台线程**里用与 ``nav`` 相同的
代码为新版本构图一次（``CachedCallGraph(persist=True)``），刷新答复立即返回
（``call_graph_warm: {scheduled: true}``）。构图结果按输入摘要进入进程内记忆
并落盘；之后 ``nav`` 新建的图对象按同一摘要命中，只需读行与计算摘要。摘要仍由
全部输入行计算（RFC-0030），复用规则没有放宽。构建期间到达的 ``nav`` 调用按同一摘要
等待这次在途构建（``call_graph_memo.claim``），不并行构建第二份；另一版本（摘要
不同）的构建互不等待。服务器停止时不再调度新构建，并在 :data:`SHUTDOWN_SECONDS`
内等待在途构建（#1667：停止路径上不启动被取消的工作）；线程是守护线程，超时后
进程照常退出（落盘结果原子替换，不会留下半份文件）。

只在长驻服务器里启用（``enable()``，由 MCP 服务器启动时调用），且只为**监视器驱动**
的刷新运行（``watcher_refresh()``，由 ``FileWatcherDaemon`` 的同步标记）。客户端显式
刷新后紧接着的第一次调用会与后台构建争用 CPU，总时间不会更短（门禁实测），因此
显式刷新与之前完全相同。``TSA_GRAPH_WARM=always`` 让显式刷新也预构图，
``TSA_GRAPH_WARM=off`` 全部关闭。

#1723：刷新的回填范围有界（#1714）且内存里有基于刷新起点版本的图时，后台任务改为
按同一范围**增量更新**那张图（``call_graph_incremental``）。工作量与改动成正比，
因此显式刷新同样运行；``nav`` 只等到增量结果就绪（不等之后的摘要与落盘）。增量
放弃时给出原因，并只在本来就会全量预构图时（监视器驱动或 ``always``）退回全量。"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

#: 关闭发布后预构图的环境变量（值为 ``off`` / ``0`` / ``false``）。
ENV_VAR = "TSA_GRAPH_WARM"
#: 服务器停止时等待在途构建的上限（秒）。
SHUTDOWN_SECONDS = 5.0

_lock = threading.Lock()
_enabled = False
_closed = False
#: 在途的后台构建：项目根 -> 线程。
_threads: dict[str, threading.Thread] = {}
#: 最近一次完成的预构图（项目根 -> 结果），由下一次刷新答复报告。
_last: dict[str, dict[str, Any]] = {}
#: 在途构建正在读取的索引库：项目根 -> 库的真实路径。
_building: dict[str, str] = {}
#: #1723：在途构建结束“在途”状态（就绪或放弃）时置位：项目根 -> 事件。增量结果就绪后
#: 线程还要补算摘要，``nav`` 只等到就绪，不等整个线程结束。
_settled: dict[str, threading.Event] = {}
#: 已完成的预构图：项目根 -> (库身份, 输入摘要)。
_ready: dict[str, tuple[tuple[Any, ...], str]] = {}
#: ``nav`` 等待同一库的在途预构图的上限（秒）；超时后照常自行构图。
_ADOPT_WAIT_SECONDS = 600.0
#: 在途构建期间又发布了新版本的项目根：结束后按这次的任务再构图一次。
_again: dict[str, Any] = {}


def enable() -> None:
    """长驻进程（MCP 服务器）启动时调用：之后每次发布都在后台预先构图。"""
    global _enabled, _closed
    with _lock:
        _enabled = True
        _closed = False


def disable() -> None:
    """关闭预构图（测试与进程内嵌入方使用）；不等待在途构建。"""
    global _enabled
    with _lock:
        _enabled = False


def enabled() -> bool:
    """本进程是否在发布后预构图（还须是监视器驱动的刷新，或 ``TSA_GRAPH_WARM=always``）。"""
    if os.environ.get(ENV_VAR, "").strip().lower() in {"off", "0", "false"}:
        return False
    return _enabled and not _closed


def _always() -> bool:
    return os.environ.get(ENV_VAR, "").strip().lower() == "always"


_origin = threading.local()


@contextmanager
def watcher_refresh() -> Iterator[None]:
    """标记本线程内的刷新由监视器驱动：其发布之后在后台预构图。

    显式刷新（客户端调用 ``index action=cache`` / ``full``）不预构图：紧接着的第一次
    调用会与后台构建争用 CPU，刷新加第一次调用的总时间不会更短（#1708 门禁）。
    """
    previous = getattr(_origin, "watcher", False)
    _origin.watcher = True
    try:
        yield
    finally:
        _origin.watcher = previous


def _watcher_driven() -> bool:
    return bool(getattr(_origin, "watcher", False))


def last_outcome(project_root: str) -> dict[str, Any] | None:
    """``project_root`` 最近一次完成的预构图结果（``warmed``、``seconds``）。"""
    with _lock:
        outcome = _last.get(_key(project_root))
    return dict(outcome) if outcome is not None else None


def _key(project_root: str) -> str:
    return os.path.normcase(os.path.realpath(project_root))


def after_publish(project_root: str) -> dict[str, Any] | None:
    """发布之后在后台线程为活动版本构图；立即返回，未启用时什么都不做。

    返回 ``{"scheduled": True, "previous": <上一次完成的结果或 None>}``。同一项目
    根已有在途构建（上一个版本）时不并行启动第二个，而是让它结束后再为当时的
    活动版本构图一次（``queued``）。
    """
    from . import call_graph_incremental

    # #1723：刷新的范围回填有界时，按同一范围增量更新上一张图——显式刷新同样适用，
    # 因为增量的工作量与改动成正比，紧接着的第一次调用只需等它很短的时间。
    plan = call_graph_incremental.take_plan(project_root)
    incremental = plan is not None and _has_base(project_root, plan)
    full = _watcher_driven() or _always()
    if not enabled() or not (full or incremental):
        return None
    key = _key(project_root)
    previous = last_outcome(project_root)
    job = _Job(plan if incremental else None, full)
    with _lock:
        if _closed:
            return None
        running = _threads.get(key)
        if running is not None and running.is_alive():
            # 在途构建结束后为当时的活动版本再构图一次；增量基础那时已是新图。
            _again[key] = job
            return {"scheduled": True, "queued": True, "previous": previous}
        # 调度时即登记将要读取的库，使紧随其后的 ``nav`` 调用等这次构建。
        _building[key] = _active_database(project_root)
        _settled[key] = threading.Event()
        thread = threading.Thread(
            target=_run,
            args=(project_root, key, job),
            name="tsa-call-graph-warm",
            daemon=True,
        )
        _threads[key] = thread
        thread.start()
    return {"scheduled": True, "incremental": incremental, "previous": previous}


def _has_base(project_root: str, plan: Any) -> bool:
    """内存里有可作增量基础的图：读的正是刷新所基于的版本。"""
    from pathlib import Path

    from . import call_graph_memo

    if plan.base_generation is None:
        return False
    previous = call_graph_memo.latest(str(Path(project_root).resolve()))
    memo = previous.get("_incremental") if previous is not None else None
    return isinstance(memo, dict) and memo.get("generation") == plan.base_generation


class _Job:
    """一次预构图：可选的增量范围，以及增量放弃时是否全量构图。"""

    def __init__(self, plan: Any, full: bool) -> None:
        self.plan = plan
        self.full = full


def _run(project_root: str, key: str, job: _Job) -> None:
    while True:
        started = time.perf_counter()
        outcome: dict[str, Any] = {"warmed": False}
        try:
            outcome.update(_build(project_root, job))
        except Exception:  # nosec B110 — 预构图失败只记日志：发布已经完成
            logger.warning("call-graph warm after publish failed", exc_info=True)
        outcome["seconds"] = round(time.perf_counter() - started, 3)
        with _lock:
            _last[key] = outcome
            queued = _again.pop(key, None)
            if queued is not None and not _closed:
                job = queued
                continue
            if _threads.get(key) is threading.current_thread():
                del _threads[key]
            return


def _build(project_root: str, job: _Job) -> dict[str, Any]:
    """与 ``nav callers`` / ``callees`` 相同的构图代码与参数（``persist=True``）。

    #1723：带范围时先按范围增量更新上一张图，就绪后立即让 ``nav`` 采用，再补算输入
    摘要并落盘（供认证快照上的调用与冷进程按摘要取用）。放弃时给出原因，并只在本次
    构图本来就会运行（监视器驱动或 ``always``）时退回全量。
    """
    from .ast_cache import ASTCache
    from .call_graph import CachedCallGraph

    key = _key(project_root)
    cache = ASTCache(project_root)
    try:
        database = str(getattr(cache, "db_path", "") or "")
        with _lock:
            _building[key] = _real(database)
            _settled.setdefault(key, threading.Event())
            _ready.pop(key, None)
        before = database_identity(database)
        graph = CachedCallGraph(project_root, cache=cache, fallback=False, persist=True)
        outcome: dict[str, Any] = {}
        if job.plan is not None:
            applied = _incremental(graph, key, job.plan, before, database, outcome)
            if applied or not job.full:
                return {**outcome, "warmed": applied}
        graph.build()
        digest = getattr(graph, "_input_digest", None)
        built = bool(getattr(graph, "_built", False))
        if built and digest and before is not None:
            if database_identity(database) == before:
                with _lock:
                    _ready[key] = (before, digest)
        return {**outcome, "warmed": built}
    finally:
        _settle(key)
        cache.close()


def _incremental(
    graph: Any,
    key: str,
    plan: Any,
    before: tuple[Any, ...] | None,
    database: str,
    outcome: dict[str, Any],
) -> bool:
    """增量更新上一张图；成功时登记就绪、补算摘要，结果写入 ``outcome``。"""
    from . import call_graph_incremental, call_graph_memo

    root = str(graph.project_root)
    previous = call_graph_memo.latest(root)
    reason = (
        "NO_PREVIOUS_GRAPH"
        if previous is None
        else "DATABASE_IDENTITY_UNKNOWN"
        if before is None
        else call_graph_incremental.update(graph, previous, plan)
    )
    outcome["incremental"] = {"applied": reason is None, "reason": reason}
    if reason is not None or before is None:  # before 为 None 时 reason 已非空
        return False
    outcome["incremental"].update(graph._incremental_stats)
    memo_key = call_graph_incremental.memo_key(before)
    state = graph._export_state()
    call_graph_memo.store(root, memo_key, state)
    if database_identity(database) == before:
        with _lock:
            _ready[key] = (before, memo_key)
    # 就绪即不再“在途”：紧接着的 ``nav`` 不必等下面的摘要与落盘。
    _settle(key)
    started = time.perf_counter()
    outcome["incremental"]["digest"] = call_graph_incremental.finalize(graph, state)
    outcome["incremental"]["digest_seconds"] = round(time.perf_counter() - started, 3)
    return True


def _settle(key: str) -> None:
    """结束 ``key`` 的“在途”状态并唤醒等待的 ``nav``。"""
    with _lock:
        _building.pop(key, None)
        event = _settled.pop(key, None)
    if event is not None:
        event.set()


def _active_database(project_root: str) -> str:
    try:
        from .cache.generation_routing import resolve_index_location

        return _real(str(resolve_index_location(project_root).path))
    except (OSError, ValueError):
        return ""


def _real(database: str) -> str:
    return os.path.normcase(os.path.realpath(database)) if database else ""


def database_identity(database: str | None) -> tuple[Any, ...] | None:
    """索引库的内容身份：文件 stat 证据加 ``ast_index`` 行数、最新 ``indexed_at``
    与 ``edges`` 最大 rowid——与 ``index_bound_graph`` 判定内存图是否仍可用的身份
    相同（#1564）。库有 WAL / 回滚日志旁路文件或不可读时为 ``None``（不复用）。"""
    import sqlite3
    from pathlib import Path

    if not database:
        return None
    try:
        info = os.stat(database)
        for suffix in ("-wal", "-journal"):
            if os.path.exists(database + suffix):
                return None
        conn = sqlite3.connect(
            Path(database).absolute().as_uri() + "?mode=ro", uri=True
        )
        try:
            files = conn.execute(
                "SELECT COUNT(*), COALESCE(MAX(indexed_at), '') FROM ast_index"
            ).fetchone()
            edges = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM edges").fetchone()
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        return None
    return (
        _real(database),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ino),
        tuple(files),
        tuple(edges),
    )


def adopt(project_root: str, database: str | None) -> str | None:
    """``nav`` 构图前调用：发布后预构图的输入摘要，可直接按它取用内存记忆。

    同一项目根、同一索引库的预构图在途时先等它结束（不并行读行、算摘要、解析）；
    另一个库（另一个版本、快照）的调用不等待。预构图完成且该库的身份与构建前后
    都相同时返回其输入摘要；否则 ``None``，调用方照常读行并按摘要判定。
    """
    if not database:
        return None
    key = _key(project_root)
    target = _real(database)
    with _lock:
        building = _building.get(key) == target
        thread = _threads.get(key) if building else None
        event = _settled.get(key) if building else None
    waiting = thread is not None and thread is not threading.current_thread()
    if event is not None and waiting:
        # 在途构建登记时总带着事件；增量结果就绪即置位（不等之后的摘要与落盘）。
        event.wait(_ADOPT_WAIT_SECONDS)
    with _lock:
        ready = _ready.get(key)
    if ready is None or ready[0][0] != target:
        return None
    identity, digest = ready
    return digest if database_identity(database) == identity else None


def wait(project_root: str | None = None, timeout: float | None = None) -> bool:
    """等待在途构建结束（全部或某个项目根）；全部结束返回 True。"""
    deadline = None if timeout is None else time.monotonic() + timeout
    with _lock:
        threads = [
            thread
            for key, thread in _threads.items()
            if project_root is None or key == _key(project_root)
        ]
    for thread in threads:
        left = None if deadline is None else max(0.0, deadline - time.monotonic())
        thread.join(left)
    return not any(thread.is_alive() for thread in threads)


def shutdown(timeout: float = SHUTDOWN_SECONDS) -> bool:
    """服务器停止：不再调度新构建，并在 ``timeout`` 内等待在途构建。

    超时的构建留在守护线程里，随进程退出（落盘结果原子替换）。返回是否全部结束。
    """
    global _closed
    with _lock:
        _closed = True
    finished = wait(timeout=timeout)
    if not finished:
        logger.warning(
            "call-graph warm still running after %.1f s at shutdown; abandoned",
            timeout,
        )
    return finished
