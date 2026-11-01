"""封存期满仍忙时，指出本进程中哪个 SQLite 对象、被谁引用着私有版本（#1848）。

#1831 的证据（``seal_diagnostics.holder_evidence``）在 CI 上两次说明了持有者在
本进程、只有主线程、该文件上多一个描述符，却说不出它是哪个对象。这里在期满时
（不占用忙等待期限）遍历本进程的对象：

* ``open_connection``：仍打开、主库正是该文件的 ``sqlite3.Connection``；
* ``other_thread_connection``：其他线程创建、本线程无法查询库文件的打开连接；
* ``cursor_on_closed_connection``：连接已关闭、游标仍存活——未完成的语句让关闭
  的连接成为僵尸并继续持锁（#1832 / #1833 的模式）。``sqlite3`` 不暴露已关闭
  连接的库文件，所以这类候选可能属于其他库。

每个候选附一条有界的引用链（帧的函数与行号、生成器、异常、持有它的实例类型、
模块全局），足以在下一次偶发时直接指出泄漏的代码位置。证据只用于诊断：任何
一步失败都跳过该项，绝不抛出，也不改变封存结果。
"""

from __future__ import annotations

import gc
import os
import sqlite3
import sys
import time
import types
from typing import Any

MAX_HOLDERS = 5
MAX_CHAIN = 8
#: 构建全部引用链的总时间上限（秒）；只在封存已失败之后花费。
CHAIN_BUDGET_S = 3.0
CHAIN_TRUNCATED = "... (diagnostic time budget exhausted)"
_MAX_TEXT = 160
#: 引用链在这些对象处结束：再往上只是定义它们的模块与类型系统。
_CHAIN_ENDS = (types.ModuleType, types.FunctionType, type)
_HOLDER_KINDS = (
    "open_connection",
    "other_thread_connection",
    "cursor_on_closed_connection",
)


def holder_objects(
    database: str | os.PathLike[str] | None,
    *,
    exclude: object | None = None,
) -> list[dict[str, Any]]:
    """本进程中可能持有 ``database`` 的 SQLite 对象及其引用链（有界，绝不抛出）。

    ``exclude`` 是调用方自己的连接（封存连接本身也打开着该文件）。
    """
    try:
        return _holder_objects(database, exclude)
    except Exception as exc:  # 诊断绝不改变封存结果
        return [{"error": f"{type(exc).__name__}: {exc}"[:_MAX_TEXT]}]


def _holder_objects(
    database: str | os.PathLike[str] | None, exclude: object | None
) -> list[dict[str, Any]]:
    target = os.path.realpath(database) if database is not None else None
    found: dict[str, list[Any]] = {kind: [] for kind in _HOLDER_KINDS}
    for obj in gc.get_objects():
        if obj is exclude:
            continue
        kind = _classify(obj, target)
        if kind is not None and len(found[kind]) < MAX_HOLDERS:
            found[kind].append(obj)
    ordered = [(kind, obj) for kind in _HOLDER_KINDS for obj in found[kind]]
    del found
    ordered = ordered[:MAX_HOLDERS]
    ignored = {id(ordered), *(id(pair) for pair in ordered)}
    # 每一步引用链都扫描整个堆；大进程里总耗时以此为界，超出后只报告种类。
    deadline = time.monotonic() + CHAIN_BUDGET_S
    holders = []
    for kind, obj in ordered:
        holders.append(
            {
                "kind": kind,
                "object": _describe(obj),
                "held_by": _chain(obj, ignored, deadline),
            }
        )
    return holders


def _classify(obj: object, target: str | None) -> str | None:
    if isinstance(obj, sqlite3.Connection):
        return _connection_kind(obj, target)
    if isinstance(obj, sqlite3.Cursor):
        try:
            connection = obj.connection
        except Exception:  # noqa: BLE001 - 尽力而为
            return None
        if _is_closed(connection):
            return "cursor_on_closed_connection"
    return None


def _is_closed(connection: sqlite3.Connection) -> bool:
    try:
        connection.total_changes  # noqa: B018 - 已关闭的连接在此抛出
    except sqlite3.ProgrammingError as exc:
        return "closed" in str(exc)
    except Exception:  # noqa: BLE001 - 尽力而为
        return False
    return False


def _connection_kind(connection: sqlite3.Connection, target: str | None) -> str | None:
    try:
        cursor = sqlite3.Connection.execute(connection, "PRAGMA database_list")
        try:
            rows = cursor.fetchall()
        finally:
            cursor.close()
    except sqlite3.ProgrammingError as exc:
        # 已关闭的连接不持有文件；其他线程创建的连接本线程不能查询，但它仍打开。
        return None if "closed" in str(exc) else "other_thread_connection"
    except Exception:  # noqa: BLE001 - 尽力而为
        return None
    for row in rows:
        try:
            filename = row[2]
        except Exception:  # noqa: BLE001 - 尽力而为
            continue
        if filename and target is not None and os.path.realpath(filename) == target:
            return "open_connection"
    return None


def _describe(obj: object) -> str:
    """一个引用者的简短描述：帧与生成器给出函数和位置，其余给出类型。"""
    if isinstance(obj, types.FrameType):
        code = obj.f_code
        name = getattr(code, "co_qualname", code.co_name)
        return f"frame {name} ({_short(code.co_filename)}:{obj.f_lineno})"
    if isinstance(obj, (types.GeneratorType, types.CoroutineType)):
        frame = getattr(obj, "gi_frame", None) or getattr(obj, "cr_frame", None)
        where = (
            f" ({_short(frame.f_code.co_filename)}:{frame.f_lineno})" if frame else ""
        )
        return f"{type(obj).__name__} {obj.__qualname__}{where}"
    if isinstance(obj, types.ModuleType):
        return f"module {obj.__name__}"
    if isinstance(obj, types.FunctionType):
        code = obj.__code__
        return (
            f"function {obj.__qualname__} "
            f"({_short(code.co_filename)}:{code.co_firstlineno})"
        )
    if isinstance(obj, type):
        return f"class {obj.__module__}.{obj.__qualname__}"[:_MAX_TEXT]
    if isinstance(obj, BaseException):
        return f"exception {type(obj).__qualname__}: {obj}"[:_MAX_TEXT]
    kind = type(obj)
    return f"{kind.__module__}.{kind.__qualname__}"[:_MAX_TEXT]


def _short(filename: str) -> str:
    parts = filename.replace("\\", "/").split("/")
    return "/".join(parts[-3:])


def _chain(obj: object, ignored: set[int], deadline: float) -> list[str]:
    """沿第一个外部引用者向上，直到模块、函数、正在运行的帧、长度或时间上限。"""
    running = _running_frames()
    chain: list[str] = []
    seen = set(ignored)
    current = obj
    for _ in range(MAX_CHAIN):
        if time.monotonic() > deadline:
            chain.append(CHAIN_TRUNCATED)
            break
        seen.add(id(current))
        referrer = _first_referrer(current, seen, running)
        if referrer is None:
            break
        chain.append(_describe(referrer))
        if isinstance(referrer, _CHAIN_ENDS) or id(referrer) in running:
            break
        current = referrer
    return chain


def _running_frames() -> set[int]:
    frames: set[int] = set()
    frame: types.FrameType | None = sys._getframe(1)
    while frame is not None:
        frames.add(id(frame))
        frame = frame.f_back
    return frames


def _own_frame(referrer: object) -> bool:
    return (
        isinstance(referrer, types.FrameType)
        and referrer.f_code.co_filename == __file__
    )


def _first_referrer(obj: object, seen: set[int], running: set[int]) -> object | None:
    candidates: list[object] = []
    referrer: object
    for referrer in gc.get_referrers(obj):
        if id(referrer) in seen or _own_frame(referrer):
            continue
        if isinstance(referrer, dict):
            owner = _dict_owner(referrer, seen)
            if owner is not None:
                seen.add(id(referrer))
                referrer = owner
        # 连接自己的语句缓存（``functools.lru_cache`` 包装连接本身）不是持有者。
        if getattr(referrer, "__wrapped__", None) is obj:
            continue
        candidates.append(referrer)
    # 正在运行的帧把对象当局部变量引用时最直接；否则取第一个外部引用者。
    for referrer in candidates:
        if id(referrer) in running:
            return referrer
    return candidates[0] if candidates else None


def _dict_owner(mapping: dict[Any, Any], seen: set[int]) -> object | None:
    """实例或模块的 ``__dict__`` 换成其所有者，便于读出“哪个类型的属性”。"""
    referrer: object
    for referrer in gc.get_referrers(mapping):
        if id(referrer) in seen or _own_frame(referrer):
            continue
        try:
            if referrer.__dict__ is mapping:
                return referrer
        except Exception:  # noqa: BLE001 - 尽力而为（无 ``__dict__`` 或访问出错）
            continue
    return None
