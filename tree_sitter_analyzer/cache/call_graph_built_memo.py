"""#1710：调用图标记复核（``call_graph_built``）的进程内记忆，按库文件 stat 证据。

``call_graph_built`` 除精确标记外还要证明调用边不悬空：对约 19 万条 ``edges`` 做
两次反连接扫描。它是库内容的纯函数，却在未认证的 ``nav callers`` 路径上每次调用
都重算——实测本仓库每次约 1–2.7 s，是认证捕获被跳过之后热调用的最大开销。

复用条件（RFC-0030：绝不以“仅路径”判定为未变；与 #1651 的 ``index_identity``
记忆同一标准）：

* 键为库文件、``-wal``、``-journal`` 的 ``(size, mtime_ns, ctime_ns, ino, dev)``；
  每次取用都重新 ``stat``，任一不同即重算。任何提交都会改变库或 WAL 的大小或 mtime。
* 结果记在计算**之前**取得的证据下：计算期间的写入会改变证据，之后的取用只会不匹配。
* 时间戳竞争：任一文件 mtime 距当前不足 :data:`RACY_WINDOW_NS` 时不记忆。
* 只记忆库路径可解析的 ``ASTCache``；内存库、认证快照副本不经此处。
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

#: mtime 与当前相差不足此值的库文件不记忆（覆盖 FAT 的 2 s 粒度并留余量）。
RACY_WINDOW_NS = 5_000_000_000
#: 记忆条目上限（每个库文件一条）。
MAX_ENTRIES = 16
_SIDECARS = ("", "-wal", "-journal")

_LOCK = threading.Lock()
_MEMO: dict[str, tuple[tuple[Any, ...], bool]] = {}


def clear() -> None:
    """丢弃全部记忆（测试隔离用）。"""
    with _LOCK:
        _MEMO.clear()


def database_stamps(database: str) -> tuple[Any, ...] | None:
    """库及其旁路文件的 stat 证据；竞争窗口内或不可读为 None（不得复用）。"""
    stamps: list[Any] = []
    now = time.time_ns()
    for suffix in _SIDECARS:
        try:
            info = os.stat(database + suffix)
        except FileNotFoundError:
            if not suffix:
                return None  # 主库不存在：没有可复核的证据
            stamps.append(None)
            continue
        except OSError:
            return None
        if now - info.st_mtime_ns < RACY_WINDOW_NS:
            return None
        stamps.append(
            (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino, info.st_dev)
        )
    return tuple(stamps)


def memoized(database: str | None, compute: Callable[[], bool]) -> bool:
    """证据未变时复用上次结果，否则计算；``database`` 为 None 时总是计算。"""
    if not database or database == ":memory:":
        return compute()
    path = os.path.abspath(database)
    before = database_stamps(path)
    if before is not None:
        with _LOCK:
            cached = _MEMO.get(path)
        if cached is not None and cached[0] == before:
            return cached[1]
    result = compute()
    if before is not None:
        with _LOCK:
            if len(_MEMO) >= MAX_ENTRIES and path not in _MEMO:
                _MEMO.pop(next(iter(_MEMO)))
            _MEMO[path] = (before, result)
    return result
