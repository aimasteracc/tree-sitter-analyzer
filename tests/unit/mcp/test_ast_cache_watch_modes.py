"""Tests for watch_start/watch_stop/watch_status modes in ASTCacheTool."""

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
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
    t = ASTCacheTool(str(project))
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
    import asyncio
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
    import threading

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
        status = await tool.execute({"mode": "watch_status"})
        assert status["running"] is True
        release.set()
        stop(timeout=3)
        result = await tool.execute({"mode": "watch_stop"})
        assert result["status"] == "not_running"
    finally:
        release.set()
        stop(timeout=3)


@pytest.mark.asyncio
async def test_project_rebind_retains_unfinished_watcher(tool, tmp_path, monkeypatch):
    # #1405：项目切换钩子不能遗失尚未退出的后台任务或提前建立新项目缓存。
    import threading

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
