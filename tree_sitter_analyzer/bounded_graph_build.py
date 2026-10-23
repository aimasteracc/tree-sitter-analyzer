"""在墙钟预算内构建项目依赖图（#1602）。

``score_dependencies`` 原先用 ``with ThreadPoolExecutor`` 限时：``fut.result``
超时后确实返回回退评分，但 ``with`` 退出时 ``shutdown(wait=True)`` 仍会等构建
跑完。#1602 剖析 ``health file api/pulse.py``：68 s 中 58.7 s 耗在这次等待上，
而等来的整图随即被丢弃，评分结果仍是回退值。

单文件评分超时后改为立即返回；构建在守护线程中继续，完成后照常进入
``DependencyGraph`` 的进程级缓存，CLI 退出时也不会被它拖住。项目评分保持原语义：
超时后仍等待构建完成以预热缓存，供后续文件复用。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


def build_within(
    build: Callable[[str], Any],
    root: str,
    timeout: float,
    *,
    wait_after_timeout: bool,
) -> Any | None:
    """返回构建结果；超时返回 None，构建在预算内抛出的异常原样重新抛出。"""
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["graph"] = build(root)
        except Exception as exc:  # 交给调用方的既有回退分支处理
            outcome["error"] = exc

    worker = threading.Thread(target=run, name="tsa-dependency-graph", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        if wait_after_timeout:
            worker.join()
        return None
    if "error" in outcome:
        raise outcome["error"]
    return outcome["graph"]
