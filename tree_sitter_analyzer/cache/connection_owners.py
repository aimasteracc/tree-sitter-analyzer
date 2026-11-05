"""把 SQLite 连接的关闭绑定到它的所有者，而不是留给垃圾回收（#1904）。

Python 3.13 的 ``sqlite3.Connection`` 若未显式关闭，会在终结器里关闭：先发出
``ResourceWarning``，再 ``sqlite3_close_v2``——但不清空语句缓存，SQLite 因而把它留作
"僵尸"，继续打开文件并持有锁，直到缓存释放。在此之前，引用环里的连接一直打开着。
线程本地连接在线程退出、缓存对象被丢弃时都会落入这种状态。

这里用 ``weakref.finalize`` 在所有者消失时显式关闭连接：弱引用回调在同一轮回收中
先于终结器运行，线程退出时则在该线程内同步运行。``sqlite3.Connection`` 本身不支持
弱引用，因此弱引用指向所有者（或一个只代表"本线程这条连接"的令牌）。
"""

from __future__ import annotations

import logging
import sqlite3
import weakref

logger = logging.getLogger(__name__)


class ThreadConnectionToken:
    """存放在线程本地槽里：槽被清空（线程退出或换绑）时关闭对应连接。"""

    __slots__ = ("__weakref__",)


def close_owned(connection: sqlite3.Connection) -> None:
    """关闭所有者已消失的连接；在其他线程上不能关闭时交还给 SQLite 自身的清理。"""
    try:
        connection.close()
    except sqlite3.ProgrammingError as exc:
        # check_same_thread 连接只能在创建它的线程关闭；该线程退出时其令牌另行触发。
        logger.debug("owned SQLite connection not closed from this thread: %s", exc)
    except sqlite3.Error as exc:
        logger.debug("owned SQLite connection close failed: %s", exc)


def close_with(owner: object, connection: sqlite3.Connection) -> weakref.finalize:
    """``owner`` 被回收时关闭 ``connection``；返回的终结器可提前调用（幂等）。"""
    finalizer = weakref.finalize(owner, close_owned, connection)
    # 解释器退出时不代为关闭：此时其他线程的连接不能关闭，SQLite 自行释放。
    finalizer.atexit = False  # type: ignore[misc]  # 文档化的可写属性
    return finalizer
