"""记下私有构建库上每个 SQLite 连接是谁创建的，封存忙时指出创建者（#1904）。

#1831 / #1848 的证据说明了封存时的持有者在本进程、只有主线程，却看不到对应的
Python 对象：在 Python 3.13 上，从未关闭、由终结器关闭的连接显示为"已关闭"，
SQLite 却因语句缓存仍在而继续打开文件并持锁。这类持有者只能由创建位置来定位。

这里用一个审计钩子（``sqlite3.connect`` 与 ``sqlite3.connect/handle``）：

* 只有数据库路径是版本存储中的 ``index.db`` 时才取一段有界的调用栈，其余事件
  只做两次字符串比较即返回；
* 记录按 ``id(连接)`` 存放，不持有连接本身（``sqlite3.Connection`` 不支持弱引用）；
  任何新连接的 ``handle`` 事件都会覆盖或清除同一 id 的旧记录，避免地址复用误报；
* 记录数有上限，最早的先丢弃。

证据只用于诊断：任何一步失败都跳过，绝不抛出，也不改变封存结果。
"""

from __future__ import annotations

import gc
import os
import sqlite3
import sys
import threading
import time
import types
from collections import OrderedDict
from typing import Any
from urllib.parse import unquote

#: 版本存储目录名（``generation_selector`` 的布局）；只有其中的主库值得记录。
_STORE_MARKER = "index-generations"
_DATABASE_NAME = "index.db"
MAX_RECORDS = 256
MAX_FRAMES = 12
MAX_CREATORS = 5
_CONNECT = "sqlite3.connect"
_HANDLE = "sqlite3.connect/handle"
_SKIPPED_FILES = (__file__,)

_records: OrderedDict[int, dict[str, Any]] = OrderedDict()
_lock = threading.Lock()
_pending = threading.local()
_installed = False


def is_generation_database(database: object) -> bool:
    """``database`` 是否指向版本存储中的主库（路径、``Path`` 或 ``file:`` URI）。"""
    text = os.fspath(database) if isinstance(database, os.PathLike) else database
    if not isinstance(text, str) or _STORE_MARKER not in text:
        return False
    path = text.split("?", 1)[0]
    return path.replace("\\", "/").endswith("/" + _DATABASE_NAME)


def _stack() -> list[str]:
    frames: list[str] = []
    frame: types.FrameType | None = sys._getframe(2)
    while frame is not None and len(frames) < MAX_FRAMES:
        code = frame.f_code
        if code.co_filename not in _SKIPPED_FILES:
            parts = code.co_filename.replace("\\", "/").split("/")
            frames.append(f"{'/'.join(parts[-3:])}:{frame.f_lineno} {code.co_name}")
        frame = frame.f_back
    return frames


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event != _CONNECT and event != _HANDLE:
        return
    try:
        if event == _CONNECT:
            database = args[0] if args else None
            _pending.record = (
                {
                    "database": str(database),
                    "thread": threading.current_thread().name,
                    "created_at": time.time(),
                    "stack": _stack(),
                }
                if is_generation_database(database)
                else None
            )
            return
        record = getattr(_pending, "record", None)
        _pending.record = None
        key = id(args[0])
        with _lock:
            if record is None:
                _records.pop(key, None)  # 地址被一个无关连接复用
                return
            _records[key] = record
            _records.move_to_end(key)
            while len(_records) > MAX_RECORDS:
                _records.popitem(last=False)
    except Exception:  # noqa: BLE001 - 诊断绝不影响连接的创建  # nosec B110
        pass


def install() -> None:
    """进程内安装一次审计钩子（钩子不可移除，重复调用无副作用）。"""
    global _installed
    with _lock:
        if _installed:
            return
        _installed = True
    sys.addaudithook(_audit)


def _normalized(database: str) -> str:
    path = database
    if path.startswith("file:"):
        path = unquote(path[len("file:") :].split("?", 1)[0])
        if path.startswith("//"):
            path = path[2:]
        if os.name == "nt" and path.startswith("/") and path[2:3] == ":":
            path = path[1:]
    return os.path.normcase(os.path.realpath(path))


def _state(connection: sqlite3.Connection) -> str:
    try:
        connection.total_changes  # noqa: B018 - 已关闭的连接在此抛出
    except sqlite3.ProgrammingError as exc:
        return "closed" if "closed" in str(exc) else "open (other thread)"
    except Exception:  # noqa: BLE001 - 尽力而为
        return "unknown"
    return "open"


def creators(
    database: str | os.PathLike[str] | None,
    *,
    exclude: object | None = None,
) -> list[dict[str, Any]]:
    """仍存活、创建于 ``database`` 上的连接及其创建栈（有界，绝不抛出）。

    已关闭却仍存活的连接也列出：它可能是仍持锁的僵尸连接。
    """
    if database is None:
        return []
    try:
        with _lock:
            if not _records:
                return []
            records = dict(_records)
        target = _normalized(os.fspath(database))
        found: list[dict[str, Any]] = []
        for obj in gc.get_objects():
            if obj is exclude or not isinstance(obj, sqlite3.Connection):
                continue
            record = records.get(id(obj))
            if record is None or _normalized(record["database"]) != target:
                continue
            found.append(
                {
                    "state": _state(obj),
                    "thread": record["thread"],
                    "age_s": round(time.time() - record["created_at"], 3),
                    "stack": record["stack"],
                }
            )
            if len(found) >= MAX_CREATORS:
                break
        return found
    except Exception as exc:  # noqa: BLE001 - 诊断绝不改变封存结果
        return [{"error": f"{type(exc).__name__}: {exc}"[:160]}]
