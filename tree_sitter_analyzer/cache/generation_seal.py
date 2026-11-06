"""封存时把私有版本切回回滚日志：遵守连接的忙等待约定，失败时类型化（#1821）。

SQLite 从 WAL 切到 ``journal_mode=DELETE`` 需要主库排他锁，而这一步
（``sqlite3PagerCloseWal`` → ``pagerExclusiveLock``）**不调用忙处理器**：只要
同一文件上还有任何连接打开（WAL 模式下哪怕空闲也持有 SHARED 锁），语句立即以
``database is locked`` 失败，连接的 ``timeout`` 不起作用。前一步
``wal_checkpoint(TRUNCATE)`` 却照常成功，所以这类失败只在封存时出现。

TSA 其余写入语句都按连接的忙等待（10 s）等待短暂的锁，期满才报告类型化的
``INDEX_WRITER_BUSY``。这里用同样的上限有界重试：持有者在期限内释放时封存照常
完成；期满仍被占用则抛出 :class:`SealBusy`。调用方的 ``abandoning`` 回收私有
版本，活动选择器不变，也不会跳过日志切换——封存要么完整完成，要么不发布。
"""

from __future__ import annotations

import gc
import logging
import os
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from .admission import INDEX_WRITER_BUSY, IndexWriteAdmissionError
from .seal_creators import creators
from .seal_diagnostics import holder_evidence, sqlite_objects
from .seal_holders import holder_objects

logger = logging.getLogger(__name__)

#: 与 ``ASTCache`` 写连接的 ``timeout`` 相同：短暂的锁在此期限内等待。
SEAL_BUSY_TIMEOUT_S = 10.0
SEAL_BUSY = "INDEX_GENERATION_SEAL_BUSY"
_FIRST_DELAY_S = 0.005
_MAX_DELAY_S = 0.2
# SQLITE_BUSY / SQLITE_LOCKED（Python 3.11+ 的 ``sqlite_errorcode``）。
_BUSY_CODES = frozenset({5, 6})
_BUSY_MESSAGES = ("database is locked", "database table is locked")


class SealBusy(IndexWriteAdmissionError):
    """封存期限内私有版本仍被另一连接占用；未发布任何内容，可重试。"""

    default_code = INDEX_WRITER_BUSY

    def __init__(self, first_busy: dict[str, Any] | None = None) -> None:
        super().__init__(SEAL_BUSY)
        #: 第一次忙时的持有者证据（``leave_wal`` 的 ``fallback`` 路径交给调用方记录）。
        self.first_busy = first_busy


def _is_busy(exc: sqlite3.OperationalError) -> bool:
    code = getattr(exc, "sqlite_errorcode", None)
    if code is not None:
        return code in _BUSY_CODES
    return str(exc) in _BUSY_MESSAGES


def _switch(connection: sqlite3.Connection) -> str | sqlite3.OperationalError:
    """切回回滚日志并返回结果模式；忙时返回该忙错误，其他错误原样抛出。"""
    try:
        return str(connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0])
    except sqlite3.OperationalError as exc:
        if not _is_busy(exc):
            raise
        return exc


def leave_wal(
    connection: sqlite3.Connection,
    *,
    database: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    fallback: bool = False,
) -> str:
    """执行 ``PRAGMA journal_mode=DELETE`` 并返回结果模式；忙时有界重试。

    #1831：第一次忙时先记下持有者证据，再做一次循环回收——只被引用环引用、
    尚未关闭的本进程连接在回收时关闭，不必等满期限。

    ``fallback``：调用方期满后另有出路（#1902 封存字节副本）并自行记录创建栈。
    此时跳过期满时的堆扫描取证（第二次证据、``holder_objects`` 引用链、创建栈），
    第一次证据随 :class:`SealBusy` 交给调用方。#1909：这些扫描在大进程里要数秒
    CPU（Linux CI 上整个忙路径 3.4-5.6 s，慢 macOS 上约 10 s），远超 1 s 的短等待。
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    budget = SEAL_BUSY_TIMEOUT_S if timeout is None else timeout
    outcome = _switch(connection)
    if isinstance(outcome, str):
        return outcome
    first = holder_evidence(database)
    gc.collect()
    outcome = _switch(connection)
    if isinstance(outcome, str):
        logger.warning("%s released by garbage collection: %s", SEAL_BUSY, first)
        return outcome
    # #1902：期限从证据与回收之后起算。大进程里两者可能就要 1 s 以上，否则较短的
    # 期限还没等过一次就已用完。
    deadline = clock() + budget
    delay = _FIRST_DELAY_S
    while (remaining := deadline - clock()) > 0:
        sleep(min(delay, remaining))
        delay = min(delay * 2, _MAX_DELAY_S)
        outcome = _switch(connection)
        if isinstance(outcome, str):
            return outcome
    if fallback:
        raise SealBusy(first_busy=first) from outcome
    # #1848：期满后（不占用忙等待期限）再指出持有者对象及其引用链。三项证据共用
    # 一次对 SQLite 对象的查找；查找失败时各自重试并把失败写进各自的证据。
    objects = _sqlite_objects()
    logger.warning(
        "%s after %.1f s: first busy %s; at deadline %s; holders %s; creators %s",
        SEAL_BUSY,
        budget,
        first,
        holder_evidence(database, objects=objects),
        holder_objects(database, exclude=connection, objects=objects),
        # #1904：Python 看不到的持有者（已关闭却仍持锁）由创建栈指出。
        creators(database, exclude=connection, objects=objects),
    )
    del objects  # 异常的回溯保留本帧；列表不得让持有者活得更久
    raise SealBusy() from outcome


def _sqlite_objects() -> list[Any] | None:
    try:
        return sqlite_objects()
    except Exception:  # noqa: BLE001 - 诊断绝不改变封存结果；各项证据自行重试
        return None
