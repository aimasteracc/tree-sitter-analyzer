"""#1730：一次编辑只触发一次监视器同步。

#1708 门禁里，一次源码编辑让监视器跑了约 6 次同步。原因：项目里有稳定的单文件
失败（缺少可选语法的 swift / lua 文件，#1554 / #1671）时，每次同步的
``result.errors`` 都非零，监视器把它当作临时失败，按 1、2、4、8……秒退避重试，
之后每 60 秒一次，永不停止。稳定失败的重试只会得到同一失败（同一字节、同一原因），
不应安排重试；读写失败等临时错误照旧退避重试。
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

_REASON = 'Swift grammar not installed — pip install "tree-sitter-analyzer[swift]"'


@pytest.fixture
def project(tmp_path, monkeypatch):
    from tree_sitter_analyzer.core.parser import Parser
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (root / "broken.py").write_text("def broken():\n    return 2\n", encoding="utf-8")
    original = Parser.parse_code

    def parse_code(self, source_code, language, filename=None, *args, **kwargs):
        if filename is not None and os.path.basename(filename) == "broken.py":
            return SimpleNamespace(success=False, error_message=_REASON)
        return original(self, source_code, language, filename, *args, **kwargs)

    monkeypatch.setattr(Parser, "parse_code", parse_code)
    auto_index_guard.reset()
    yield str(root)
    auto_index_guard.reset()


@pytest.fixture
def watcher(project):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    cache = ASTCache(project)
    daemon = FileWatcherDaemon(cache, poll_interval=1, debounce=0)
    yield daemon
    daemon.stop()
    cache.close()


def _pending_retry(daemon) -> bool:
    with daemon._pending_lock:
        return daemon._sync_requested or any(
            timer.is_alive() for timer in daemon._timers
        )


def test_stable_failures_do_not_schedule_a_retry(project, watcher, monkeypatch) -> None:
    # 一次编辑 → 一次同步；稳定失败照旧报告，但不安排重试同步。
    # 运行中的监视器才安排重试；这里不启动轮询线程（它会另做一次启动对齐）。
    monkeypatch.setattr(watcher, "is_running", lambda: True)
    path = os.path.join(project, "a.py")
    with open(path, "a", encoding="utf-8") as stream:
        stream.write("\n\ndef beta():\n    return alpha()\n")
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))

    result = watcher.trigger_sync()

    assert (result["errors"], watcher.get_stats()["syncs_triggered"]) == (1, 1)
    assert _pending_retry(watcher) is False


def test_transient_errors_still_retry(project, watcher, monkeypatch) -> None:
    # 临时失败（这里：读取失败）仍按退避重试。
    from tree_sitter_analyzer.incremental_sync_support import SyncResult

    def transient(*_args, **_kwargs):
        return SyncResult(
            errors=1,
            details=[{"file": "a.py", "status": "error", "reason": "locked"}],
        )

    monkeypatch.setattr(watcher._sync, "sync", transient)
    monkeypatch.setattr(watcher, "is_running", lambda: True)

    watcher.trigger_sync()

    assert _pending_retry(watcher) is True


@pytest.mark.slow_ok
def test_one_edit_produces_one_sync_with_the_watcher_running(project, watcher) -> None:
    # 端到端：启动对齐一次，然后一次编辑只多一次同步——监视器自己写 .ast-cache
    # （新版本、stat 证据、图记忆）也不会再触发同步，稳定失败不会引发退避重试。
    import time

    def syncs() -> int:
        return int(watcher.get_stats()["syncs_triggered"])

    def wait_for(count: int, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while syncs() < count and time.monotonic() < deadline:
            time.sleep(0.1)

    watcher.start()
    wait_for(1, 30)
    assert syncs() == 1  # 启动对齐（#1405）
    path = os.path.join(project, "a.py")
    with open(path, "a", encoding="utf-8") as stream:
        stream.write("\n\ndef gamma():\n    return alpha()\n")
    wait_for(2, 30)
    # 退避重试原本在 1、2、4 秒后各来一次：观察 8 秒。
    time.sleep(8)

    assert syncs() == 2
