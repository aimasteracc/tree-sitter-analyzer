"""Tests for watch_start/watch_stop/watch_status modes in ASTCacheTool."""

import asyncio
import threading
from unittest.mock import Mock

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.subscription_lifecycle import SubscriptionLifecycleManager
from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def hello():\n    pass\n")
    (src / "util.py").write_text("def add(a, b):\n    return a + b\n")
    return tmp_path


@pytest.fixture
def cache(project):
    c = ASTCache(str(project))
    yield c
    c.close()


@pytest.fixture
def tool(project):
    manager = SubscriptionLifecycleManager(str(project))
    t = ASTCacheTool(str(project), manager)
    yield t
    if t._watcher is not None and t._watcher.is_running():  # noqa: SLF001 — teardown cleanup
        t._watcher.stop()  # noqa: SLF001
    if t.cache_initialized:
        t.get_cache().close()


@pytest.mark.asyncio
class TestWatchStart:
    async def test_watch_start_starts_watcher(self, tool, project):
        result = await tool.execute({"mode": "watch_start"})
        assert result["success"] is True
        assert result["status"] == "started"
        assert result["mode"] == "watch_start"
        tool._watcher.stop()

    async def test_watch_start_idempotent(self, tool, project):
        await tool.execute({"mode": "watch_start"})
        result = await tool.execute({"mode": "watch_start"})
        assert result["status"] == "already_running"
        tool._watcher.stop()

    async def test_watch_start_custom_interval(self, tool, project):
        result = await tool.execute(
            {"mode": "watch_start", "poll_interval": 2.0, "backend": "poll"}
        )
        assert result["success"] is True
        assert result["poll_interval"] == 2.0
        assert result["backend"] == "poll"
        tool._watcher.stop()

    async def test_watch_start_can_sync_after_start(self, tool, cache, project):
        await tool.execute({"mode": "watch_start"})
        sync_result = await tool.execute({"mode": "sync"})
        assert sync_result["success"] is True
        # #1405：启动对齐可先完成，手动同步仍必须完整处理两个源码文件。
        assert sync_result["new_files"] + sync_result["unchanged_files"] == 2
        tool._watcher.stop()


@pytest.mark.asyncio
class TestWatchStop:
    async def test_watch_stop_when_not_running(self, tool, project):
        result = await tool.execute({"mode": "watch_stop"})
        assert result["success"] is True
        assert result["status"] == "not_running"

    async def test_watch_stop_stops_running_watcher(self, tool, project):
        await tool.execute({"mode": "watch_start"})
        result = await tool.execute({"mode": "watch_stop"})
        assert result["success"] is True
        assert result["status"] == "stopped"
        assert "final_stats" in result

    async def test_watch_stop_includes_stats(self, tool, project):
        await tool.execute({"mode": "watch_start"})
        import time

        time.sleep(0.2)
        result = await tool.execute({"mode": "watch_stop"})
        assert result["success"] is True
        assert "final_stats" in result
        assert "uptime_seconds" in result["final_stats"]


@pytest.mark.asyncio
class TestWatchStatus:
    async def test_watch_status_no_watcher(self, tool, project):
        result = await tool.execute({"mode": "watch_status"})
        assert result["success"] is True
        assert result["running"] is False
        assert result["watcher_created"] is False

    async def test_watch_status_running(self, tool, project):
        await tool.execute({"mode": "watch_start"})
        result = await tool.execute({"mode": "watch_status"})
        assert result["success"] is True
        assert result["running"] is True
        assert result["watcher_created"] is True
        assert "stats" in result
        tool._watcher.stop()

    async def test_watch_status_after_stop(self, tool, project):
        await tool.execute({"mode": "watch_start"})
        await tool.execute({"mode": "watch_stop"})
        result = await tool.execute({"mode": "watch_status"})
        assert result["watcher_created"] is True
        assert result["running"] is False


@pytest.mark.asyncio
class TestWatchModeValidation:
    async def test_watch_modes_in_valid_modes(self, tool, project):
        for mode in ("watch_start", "watch_stop", "watch_status"):
            result = await tool.execute({"mode": mode})
            assert result["success"] is True, f"mode {mode} failed"

    async def test_invalid_mode_rejected(self, tool, project):
        with pytest.raises(ValueError, match="Invalid mode"):
            await tool.execute({"mode": "invalid_mode"})


class TestWatchToolDefinition:
    def test_watch_modes_in_schema(self, tool):
        schema = tool.get_tool_schema()
        modes = schema["properties"]["mode"]["enum"]
        assert "watch_start" in modes
        assert "watch_stop" in modes
        assert "watch_status" in modes

    def test_watch_params_in_schema(self, tool):
        schema = tool.get_tool_schema()
        assert "poll_interval" in schema["properties"]
        assert "backend" in schema["properties"]

    def test_description_mentions_watch(self, tool):
        defn = tool.get_tool_definition()
        assert "watch_start" in defn["description"]
        assert "watch_stop" in defn["description"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_during_start", [False, True])
async def test_watchdog_start_reconciles_existing_sources_without_event(
    tool, monkeypatch, stop_during_start
):
    # #1405：先启用原生观察器，再异步对齐；无需伪造文件事件。
    import sys
    from types import SimpleNamespace

    calls = []

    def start():
        calls.append("start")
        if stop_during_start:
            tool._watcher._stop_event.set()

    observer = SimpleNamespace(
        schedule=lambda *_a, **_kw: calls.append("schedule"),
        start=start,
        stop=lambda: calls.append("stop"),
        join=lambda **_kw: calls.append("join"),
    )
    monkeypatch.setitem(
        sys.modules, "watchdog.observers", SimpleNamespace(Observer=lambda: observer)
    )
    result = await tool.execute({"mode": "watch_start", "backend": "watchdog"})
    assert result["success"] is True
    expected_files = 0 if stop_during_start else 2
    for _ in range(100):
        if tool.get_cache().get_stats()["total_files"] == expected_files:
            break
        await asyncio.sleep(0.05)
    assert tool.get_cache().get_stats()["total_files"] == expected_files
    assert tool._watcher.get_stats()["events_processed"] == 0
    await tool.execute({"mode": "watch_stop"})
    assert calls == ["schedule", "start", "stop", "join"]


@pytest.mark.asyncio
async def test_watch_stop_does_not_claim_success_while_sync_is_alive(tool, monkeypatch):
    # #1405：真实后台任务未退出时不得返回 stopped，调用方仍可查询并重试。
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    watcher = FileWatcherDaemon(tool.get_cache(), debounce=0)
    tool._watcher = watcher
    entered, release = threading.Event(), threading.Event()
    stop = watcher.stop

    def sync():
        entered.set()
        assert release.wait(3)
        return {}

    monkeypatch.setattr(watcher, "_perform_sync", sync)
    monkeypatch.setattr(watcher, "stop", lambda: stop(timeout=0))
    try:
        watcher._request_sync()
        assert entered.wait(3)
        with pytest.raises(TimeoutError, match="background work is still running"):
            await tool.execute({"mode": "watch_stop"})
        assert tool._watcher is watcher
        assert tool._watcher_pending_stop is True
        with pytest.raises(TimeoutError, match="previous.*still"):
            await tool.execute({"mode": "watch_start"})
        status = await tool.execute({"mode": "watch_status"})
        assert status["running"] is True
        release.set()
        stop(timeout=3)
        result = await tool.execute({"mode": "watch_stop"})
        assert result["status"] == "not_running"
        status = await tool.execute({"mode": "watch_status"})
        assert status["watcher_created"] is True
        assert status["running"] is False
    finally:
        release.set()
        stop(timeout=3)


@pytest.mark.asyncio
@pytest.mark.parametrize("application_shutdown", [False, True])
async def test_stop_exception_retains_pending_daemon(
    tool, monkeypatch, application_shutdown
):
    """stop 抛错且 daemon 仍活时必须保留所有权并拒绝 restart。"""
    await tool.execute({"mode": "watch_start"})
    watcher, stop = tool._watcher, tool._watcher.stop
    failure = RuntimeError("stop failed")
    monkeypatch.setattr(watcher, "stop", Mock(side_effect=failure))
    try:
        with pytest.raises(RuntimeError, match="stop failed") as caught:
            if application_shutdown:
                tool.shutdown_application_watcher()
            else:
                await tool.execute({"mode": "watch_stop"})
        assert caught.value is failure
        assert tool._watcher is watcher
        assert tool._watcher_pending_stop is True
        with pytest.raises(TimeoutError, match="previous.*still"):
            await tool.execute({"mode": "watch_start"})
    finally:
        monkeypatch.setattr(watcher, "stop", stop)
        stop()


@pytest.mark.asyncio
async def test_stop_join_window_rejects_replacement_start(tool, monkeypatch):
    """旧 daemon stop/join 未返回前不能报告 already_running 或接管新启动。"""
    await tool.execute({"mode": "watch_start"})
    watcher, stop = tool._watcher, tool._watcher.stop
    entered, release = threading.Event(), threading.Event()

    def paused_stop():
        entered.set()
        assert release.wait(3)
        stop()

    monkeypatch.setattr(watcher, "stop", paused_stop)
    task = asyncio.create_task(
        asyncio.to_thread(asyncio.run, tool.execute({"mode": "watch_stop"}))
    )
    assert await asyncio.to_thread(entered.wait, 3)
    with pytest.raises(TimeoutError, match="shutdown.*still"):
        await tool.execute({"mode": "watch_start"})
    with pytest.raises(TimeoutError, match="already in progress"):
        tool.shutdown_application_watcher()
    release.set()
    assert (await task)["status"] == "stopped"
    monkeypatch.setattr(watcher, "stop", stop)
    assert (await tool.execute({"mode": "watch_start"}))["status"] == "started"
    assert tool._watcher is not watcher


@pytest.mark.asyncio
async def test_watch_start_failure_revokes_token_and_retains_partial_daemon(
    tool, monkeypatch
):
    """daemon 部分启动后失败时撤销 token，并保留实例等待显式清理。"""
    from tree_sitter_analyzer.mcp.tools import ast_cache_tool

    class PartialDaemon:
        poll_interval = 1.0
        backend = "poll"

        def __init__(self, *_args, **_kwargs):
            self.running = False

        def start(self):
            self.running = True
            raise RuntimeError("start failed")

        def is_running(self):
            return self.running

        def stop(self):
            self.running = False

    partial = PartialDaemon()
    monkeypatch.setattr(ast_cache_tool, "FileWatcherDaemon", lambda *_a, **_kw: partial)
    issued = []
    issue = tool._lifecycle_manager.issue_watch_token

    def capture_token(root):
        token = issue(root)
        issued.append(token)
        return token

    monkeypatch.setattr(tool._lifecycle_manager, "issue_watch_token", capture_token)
    try:
        manager = tool._lifecycle_manager
        async with manager.lifespan(None) as owner:
            manager.subscribe(
                owner, object(), asyncio.get_running_loop(), "selector:A", 0
            )
            with pytest.raises(RuntimeError, match="start failed"):
                await tool.execute({"mode": "watch_start"})
            assert len(issued) == 1
            assert manager.snapshot_for_watch(issued[0]) == []
            assert tool._watch_token is None
            assert tool._watcher is partial
            assert tool._watcher_pending_stop is True
            with pytest.raises(TimeoutError, match="previous.*still"):
                await tool.execute({"mode": "watch_start"})
    finally:
        partial.stop()


@pytest.mark.asyncio
async def test_cache_construction_failure_does_not_poison_next_start(tool, monkeypatch):
    """cache 构造失败必须释放预约与 token，使后续启动成功。"""
    from tree_sitter_analyzer.mcp.tools import ast_cache_tool

    real_cache = ast_cache_tool.ASTCache
    monkeypatch.setattr(
        ast_cache_tool, "ASTCache", Mock(side_effect=RuntimeError("cache failed"))
    )
    with pytest.raises(RuntimeError, match="cache failed"):
        await tool.execute({"mode": "watch_start"})
    assert tool._watch_startup is None
    monkeypatch.setattr(ast_cache_tool, "ASTCache", real_cache)
    assert (await tool.execute({"mode": "watch_start"}))["status"] == "started"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["watch_start", "stats"])
async def test_cache_build_rebind_cannot_mix_root_identity(
    tool, tmp_path, monkeypatch, mode
):
    """普通访问或启动构造的旧 root cache 都不能冒充新 root 来源。"""
    from tree_sitter_analyzer.mcp.tools import ast_cache_tool

    built, release = threading.Event(), threading.Event()
    real_cache = ast_cache_tool.ASTCache

    def paused_cache(root):
        cache = real_cache(root)
        built.set()
        assert release.wait(3)
        return cache

    monkeypatch.setattr(ast_cache_tool, "ASTCache", paused_cache)
    task = asyncio.create_task(
        asyncio.to_thread(asyncio.run, tool.execute({"mode": mode}))
    )
    assert await asyncio.to_thread(built.wait, 3)
    target = tmp_path / "new-root"
    target.mkdir()
    tool._lifecycle_manager.rebind_project(str(target))
    tool.set_project_path(str(target))
    release.set()
    with pytest.raises(TimeoutError, match="[Pp]roject.*changed"):
        await task
    assert tool._cache is None
    assert tool._watcher is None
    if mode == "stats":
        result = await tool.execute({"mode": "watch_start"})
        assert result["status"] == "started"
        assert tool.get_cache().project_root == str(target.resolve())


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_remains_alive", [False, True])
async def test_rebind_while_candidate_starting_cannot_orphan_daemon(
    tool, tmp_path, monkeypatch, stop_remains_alive
):
    """候选 daemon 发布后 rebind 必须保留所有权并由 starter 收尾。"""
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    entered, release = threading.Event(), threading.Event()
    real_start = FileWatcherDaemon.start
    real_stop = FileWatcherDaemon.stop

    def paused_start(watcher):
        entered.set()
        assert release.wait(3)
        real_start(watcher)

    monkeypatch.setattr(FileWatcherDaemon, "start", paused_start)
    if stop_remains_alive:
        monkeypatch.setattr(FileWatcherDaemon, "stop", lambda _watcher: None)
    task = asyncio.create_task(
        asyncio.to_thread(asyncio.run, tool.execute({"mode": "watch_start"}))
    )
    assert await asyncio.to_thread(entered.wait, 3)
    candidate = tool._watcher
    target = tmp_path / "new-root"
    target.mkdir()
    tool._lifecycle_manager.rebind_project(str(target))
    tool.set_project_path(str(target))
    assert tool._watcher is candidate
    with pytest.raises(TimeoutError, match="startup is still pending"):
        await tool.execute({"mode": "watch_stop"})
    with pytest.raises(TimeoutError, match="startup.*still"):
        await tool.execute({"mode": "watch_start"})
    release.set()
    with pytest.raises(TimeoutError, match="[Pp]roject.*changed"):
        await task
    assert candidate.is_running() is stop_remains_alive
    assert tool._watcher is (candidate if stop_remains_alive else None)
    assert tool._watcher_pending_stop is stop_remains_alive
    if stop_remains_alive:
        monkeypatch.setattr(FileWatcherDaemon, "stop", real_stop)
        real_stop(candidate)


@pytest.mark.asyncio
@pytest.mark.parametrize("winner_finishes", [True, False])
async def test_competing_watch_starts_keep_only_winner_daemon(
    tool, monkeypatch, winner_finishes
):
    """签 token 后落后的 starter 不能覆盖已成功启动的 winner。"""
    from tree_sitter_analyzer.mcp.tools import ast_cache_tool

    manager, issue = tool._lifecycle_manager, tool._lifecycle_manager.issue_watch_token
    first_issued, release = threading.Event(), threading.Event()
    winner_constructing, release_winner = threading.Event(), threading.Event()
    issued, daemons = [], []

    def paused_first_issue(root):
        token = issue(root)
        issued.append(token)
        if len(issued) == 1:
            first_issued.set()
            assert release.wait(3)
        return token

    real_daemon = ast_cache_tool.FileWatcherDaemon

    def record_daemon(*args, **kwargs):
        if not winner_finishes:
            winner_constructing.set()
            assert release_winner.wait(3)
        daemon = real_daemon(*args, **kwargs)
        daemons.append(daemon)
        return daemon

    monkeypatch.setattr(manager, "issue_watch_token", paused_first_issue)
    monkeypatch.setattr(ast_cache_tool, "FileWatcherDaemon", record_daemon)
    loser = asyncio.create_task(
        asyncio.to_thread(asyncio.run, tool.execute({"mode": "watch_start"}))
    )
    assert await asyncio.to_thread(first_issued.wait, 3)
    winner_task = asyncio.create_task(
        asyncio.to_thread(asyncio.run, tool.execute({"mode": "watch_start"}))
    )
    if winner_finishes:
        winner_result = await winner_task
    else:
        assert await asyncio.to_thread(winner_constructing.wait, 3)
    release.set()
    if winner_finishes:
        loser_result = await loser
        assert loser_result["status"] == "already_running"
    else:
        with pytest.raises(TimeoutError, match="changed during startup"):
            await loser
        release_winner.set()
        winner_result = await winner_task
    winner, winner_token = tool._watcher, tool._watch_token
    assert winner_result["status"] == "started"
    assert tool._watcher is winner and tool._watch_token is winner_token
    assert len(daemons) == 1 and daemons[0].is_running() is True
    assert manager.is_watch_token_current(issued[0]) is False
    assert manager.is_watch_token_current(issued[1]) is True


@pytest.mark.asyncio
async def test_project_rebind_retains_unfinished_watcher(tool, tmp_path, monkeypatch):
    # #1405：项目切换钩子不能遗失尚未退出的后台任务或提前建立新项目缓存。
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    old_cache = tool.get_cache()
    watcher = FileWatcherDaemon(old_cache, debounce=0)
    tool._watcher = watcher
    entered, release = threading.Event(), threading.Event()
    stop = watcher.stop

    def sync():
        entered.set()
        assert release.wait(3)
        return {}

    monkeypatch.setattr(watcher, "_perform_sync", sync)
    monkeypatch.setattr(watcher, "stop", lambda: stop(timeout=0))
    target = tmp_path / "other"
    target.mkdir()
    try:
        watcher._request_sync()
        assert entered.wait(3)
        tool.set_project_path(str(target))
        assert tool._watcher is watcher
        for mode in ("stats", "watch_start"):
            with pytest.raises(TimeoutError, match="previous project"):
                await tool.execute({"mode": mode})
        assert tool._cache is None
        release.set()
        stop(timeout=3)
        result = await tool.execute({"mode": "stats"})
        assert result["success"] is True
        assert tool.get_cache().project_root == str(target.resolve())
        assert tool._watcher is None
    finally:
        release.set()
        stop(timeout=3)
        old_cache.close()


@pytest.mark.asyncio
async def test_2026_09_14_watch_restart_revokes_old_callback(tool, monkeypatch):
    """同 root stop/restart 后，manager 只认可新 watcher token。"""
    from tree_sitter_analyzer.mcp import watch_push_bridge

    manager = tool._lifecycle_manager
    session = object()
    async with manager.lifespan(None) as owner:
        manager.subscribe(owner, session, asyncio.get_running_loop(), "selector:A", 0)
        await tool.execute({"mode": "watch_start"})
        old_callback = tool._watcher._on_sync
        await tool.execute({"mode": "watch_stop"})
        await tool.execute({"mode": "watch_start"})
        new_callback = tool._watcher._on_sync
        calls: list[str | None] = []

        def record_valid(root, _result, lifecycle, token):
            if lifecycle.snapshot_for_watch(token):
                calls.append(root)

        monkeypatch.setattr(watch_push_bridge, "_drive_subscriptions", record_valid)
        try:
            old_callback({})
            new_callback({})
        finally:
            await tool.execute({"mode": "watch_stop"})
    assert calls == [str(tool.project_root)]


@pytest.mark.asyncio
async def test_2026_09_14_same_root_rebind_revokes_old_epoch_callback(
    tool, monkeypatch
):
    """同 root rebind 也增加 epoch，使旧 callback 失效而新 callback 可工作。"""
    from tree_sitter_analyzer.mcp import watch_push_bridge

    manager = tool._lifecycle_manager
    session = object()
    async with manager.lifespan(None) as owner:
        manager.subscribe(owner, session, asyncio.get_running_loop(), "selector:A", 0)
        await tool.execute({"mode": "watch_start"})
        old_callback = tool._watcher._on_sync
        target = tool.project_root
        manager.rebind_project(str(target))
        tool.set_project_path(str(target))
        manager.subscribe(owner, session, asyncio.get_running_loop(), "selector:B", 0)
        await tool.execute({"mode": "watch_start"})
        new_callback = tool._watcher._on_sync
        calls: list[str | None] = []

        def record_valid(root, _result, lifecycle, token):
            if lifecycle.snapshot_for_watch(token):
                calls.append(root)

        monkeypatch.setattr(watch_push_bridge, "_drive_subscriptions", record_valid)
        try:
            old_callback({})
            new_callback({})
        finally:
            await tool.execute({"mode": "watch_stop"})
    assert calls == [str(target)]
