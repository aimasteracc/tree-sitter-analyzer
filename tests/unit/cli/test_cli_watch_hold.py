"""#1685：CLI 的 watch_start 不得在命令返回后遗留运行中的 watcher。

CI 上 ``test_force_rebuild_skips_per_file_resolution_invalidation`` 偶发看到
``_reset_incoming_edge_resolutions`` 被调用 12-16 次，参数路径全是仓库自身的
``tests/unit/no1_010b/*``：同一 pytest worker 中，``--watch`` 的 CLI 测试在仓库根
启动了 watcher 后立即返回，watcher 留在 worker 里对整个仓库做启动对齐同步，
它的写入落进了之后打桩该函数的测试窗口。

注入方式：只在 ``_watch_hold`` 的驻留循环里调用 ``time.sleep`` 时抛出
``KeyboardInterrupt``（模拟 Ctrl-C），其余调用照常——不依赖后台计时。
"""

from __future__ import annotations

import gc
import sys
import time
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.cli_main import main
from tree_sitter_analyzer.file_watcher import FileWatcherDaemon


def _running_watchers(root: str) -> list[FileWatcherDaemon]:
    return [
        obj
        for obj in gc.get_objects()
        if isinstance(obj, FileWatcherDaemon)
        and obj.is_running()
        and str(obj._cache.project_root) == root
    ]


def _ctrl_c_in_the_hold_loop(monkeypatch, root: str) -> list[int]:
    """在驻留循环第一次 sleep 时注入 Ctrl-C，并记录那一刻运行中的 watcher 数。"""
    seen: list[int] = []
    real_sleep = time.sleep

    def fake_sleep(seconds: float) -> None:
        caller = sys._getframe(1).f_globals.get("__name__", "")
        if caller.endswith("mcp_commands._watch_hold"):
            seen.append(len(_running_watchers(root)))
            raise KeyboardInterrupt
        real_sleep(seconds)

    monkeypatch.setattr(time, "sleep", fake_sleep)
    return seen


def _run_cli(root: str, *argv: str) -> int:
    argv_full = ["tree_sitter_analyzer", "--project-root", root, *argv]
    with patch.object(sys, "argv", argv_full):
        with pytest.raises(SystemExit) as exc_info:
            main()
    return int(exc_info.value.code or 0)


@pytest.mark.parametrize(
    "argv",
    [("--watch",), ("--ast-cache", "--ast-cache-mode", "watch_start")],
    ids=["watch", "ast-cache-watch-start"],
)
def test_cli_watch_start_stops_its_watcher_before_returning(
    tmp_path, monkeypatch, argv
) -> None:
    (tmp_path / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    root = str(tmp_path.resolve())
    seen = _ctrl_c_in_the_hold_loop(monkeypatch, root)

    code = _run_cli(root, *argv)

    assert code == 0
    # 命令驻留期间 watcher 确实在运行；返回时已停止，不留给后续测试。
    assert seen == [1]
    assert _running_watchers(root) == []


def test_hold_releases_without_waiting_when_asked(monkeypatch) -> None:
    from tree_sitter_analyzer.cli.commands.mcp_commands import _watch_hold

    stopped: list[str] = []

    class Tool:
        def shutdown_application_watcher(self) -> None:
            stopped.append("stopped")

    monkeypatch.setattr(
        _watch_hold, "wait_until_interrupted", lambda: pytest.fail("must not hold")
    )

    assert _watch_hold.hold_cli_watcher(Tool(), {"status": "started"}, hold=False) == 0
    assert stopped == ["stopped"]
    # 未启动（如 already_running 以外的失败答复）时什么都不做。
    assert _watch_hold.hold_cli_watcher(Tool(), {"status": "not_running"}) == 0
    assert stopped == ["stopped"]


def test_hold_reports_a_stop_that_did_not_finish(monkeypatch, capsys) -> None:
    from tree_sitter_analyzer.cli.commands.mcp_commands import _watch_hold

    class Tool:
        def shutdown_application_watcher(self) -> None:
            raise TimeoutError("Application watcher shutdown is still pending")

    def interrupted() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(_watch_hold, "wait_until_interrupted", interrupted)

    assert _watch_hold.hold_cli_watcher(Tool(), {"status": "started"}) == 1
    assert "shutdown is still pending" in capsys.readouterr().err
