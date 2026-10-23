"""#1667：线程握手等待；超时时把所有线程的栈写进失败信息。

握手等待只在出错时才会等满期限，因此期限不是被测量，而是“卡住”的判定。卡住时
只报 ``assert False`` 无从诊断：负载下的 CI 失败需要知道是哪一个线程停在哪里。
"""

from __future__ import annotations

import sys
import threading
import traceback

import pytest


def thread_stacks() -> str:
    """当前进程全部线程的栈（线程名 + 帧）。"""
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    parts = []
    for ident, frame in sys._current_frames().items():
        stack = "".join(traceback.format_stack(frame))
        parts.append(f"--- thread {names.get(ident, '?')} ({ident}) ---\n{stack}")
    return "\n".join(parts)


def wait_or_dump(event: threading.Event, seconds: float, what: str) -> None:
    """等待 ``event``；超时则以全部线程栈为信息使测试失败。"""
    if not event.wait(seconds):
        pytest.fail(f"timed out after {seconds}s waiting for {what}\n{thread_stacks()}")
