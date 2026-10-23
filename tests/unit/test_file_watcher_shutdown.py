"""#1667：watch_stop 不得在停止窗口内启动新的同步。

CI（Windows，负载下）偶发 ``Watcher shutdown timed out; background work is still
running``。根因：#1405 起，后台线程在完整基线之后发出一次启动对齐请求
（``_request_sync``：置 ``_sync_requested`` 并启动防抖计时器）。``stop()`` 取消了
这个计时器，但轮询循环的 ``finally`` 随即调用 ``_flush_pending()``——它看到
``_sync_requested`` 仍为真，就在正在停止的线程上同步执行一次完整的候选捕获与
增量同步。停止于是要等一整次索引写入；负载下超过 ``stop()`` 的 5 s 期限，线程仍
存活，``watch_stop`` 报告超时。

这里的测试用注入的事件代替真实的后台计时：防抖期限远大于测试时长（计时器不会
自行触发），同步本身被替换为记录调用的桩。
"""

from __future__ import annotations

import threading

import pytest

from tests.unit._thread_waits import thread_stacks, wait_or_dump
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

#: 握手等待的判定期限（正常情况下立即返回）。
_HANDSHAKE_SECONDS = 5.0


@pytest.fixture
def cache(tmp_path):
    (tmp_path / "main.py").write_text("def hello():\n    pass\n", encoding="utf-8")
    c = ASTCache(str(tmp_path))
    yield c
    c.close()


@pytest.fixture
def watcher(cache):
    # 防抖与轮询期限远大于测试时长：计时器不会自行触发，时序完全由测试注入。
    w = FileWatcherDaemon(cache, poll_interval=600.0, debounce=600.0)
    yield w
    w.stop()


def _record_syncs(watcher: FileWatcherDaemon, monkeypatch) -> list[str]:
    calls: list[str] = []

    def fake_sync() -> dict:
        calls.append(threading.current_thread().name)
        return {}

    monkeypatch.setattr(watcher, "_do_sync", fake_sync)
    return calls


def test_stop_during_debounce_does_not_start_the_cancelled_sync(
    watcher, monkeypatch
) -> None:
    syncs = _record_syncs(watcher, monkeypatch)
    requested = threading.Event()
    original = watcher._request_sync

    def observed_request(**kwargs) -> None:
        original(**kwargs)
        requested.set()

    monkeypatch.setattr(watcher, "_request_sync", observed_request)
    watcher.start()
    wait_or_dump(requested, _HANDSHAKE_SECONDS, "the startup alignment request")

    watcher.stop()

    assert watcher.is_running() is False, thread_stacks()
    # 计时器已被 stop() 取消；退出路径不得把它变成一次同步写入。
    assert syncs == []
    # 请求保留，重新 start 时由启动对齐兑现，不会丢失。
    assert watcher._sync_requested is True


def test_flush_after_stop_request_keeps_pending_work(watcher, monkeypatch) -> None:
    # 已经醒来的防抖回调与 stop() 竞争时，同样不得开始新的同步。
    syncs = _record_syncs(watcher, monkeypatch)
    watcher._enqueue("/fake/a.py")
    watcher._stop_event.set()

    watcher._flush_pending()

    assert syncs == []
    assert (watcher._pending, watcher._sync_requested) == ({"/fake/a.py"}, True)


def test_flush_without_stop_request_still_syncs(watcher, monkeypatch) -> None:
    # 对照组：未请求停止时，排队的变更照常同步一次。
    syncs = _record_syncs(watcher, monkeypatch)
    watcher._debounce = 600.0
    watcher._enqueue("/fake/a.py")

    watcher._flush_pending()

    assert len(syncs) == 1
    assert (watcher._pending, watcher._sync_requested) == (set(), False)
