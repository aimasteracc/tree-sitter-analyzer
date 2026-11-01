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

from .admission import INDEX_WRITER_BUSY, IndexWriteAdmissionError
from .seal_diagnostics import holder_evidence
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

    def __init__(self) -> None:
        super().__init__(SEAL_BUSY)


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
) -> str:
    """执行 ``PRAGMA journal_mode=DELETE`` 并返回结果模式；忙时有界重试。

    #1831：第一次忙时先记下持有者证据，再做一次循环回收——只被引用环引用、
    尚未关闭的本进程连接在回收时关闭，不必等满期限。
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    budget = SEAL_BUSY_TIMEOUT_S if timeout is None else timeout
    deadline = clock() + budget
    outcome = _switch(connection)
    if isinstance(outcome, str):
        return outcome
    first = holder_evidence(database)
    gc.collect()
    outcome = _switch(connection)
    if isinstance(outcome, str):
        logger.warning("%s released by garbage collection: %s", SEAL_BUSY, first)
        return outcome
    delay = _FIRST_DELAY_S
    while (remaining := deadline - clock()) > 0:
        sleep(min(delay, remaining))
        delay = min(delay * 2, _MAX_DELAY_S)
        outcome = _switch(connection)
        if isinstance(outcome, str):
            return outcome
    # #1848：期满后（不占用忙等待期限）再指出持有者对象及其引用链。
    logger.warning(
        "%s after %.1f s: first busy %s; at deadline %s; holders %s",
        SEAL_BUSY,
        budget,
        first,
        holder_evidence(database),
        holder_objects(database, exclude=connection),
    )
    raise SealBusy() from outcome
