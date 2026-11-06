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

from .seal_diagnostics import sqlite_objects

MAX_HOLDERS = 5
MAX_CHAIN = 8
#: 构建全部引用链的总时间上限（秒）；只在封存已失败之后花费。每一步只做一次全堆
#: 遍历（实例 ``__dict__`` 的所有者只为选中的那个引用者再找一次），一百五十万对象
#: 的堆上约 0.03 s 一步，这个上限足够走完几条完整的链。
CHAIN_BUDGET_S = 1.0
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
    objects: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """本进程中可能持有 ``database`` 的 SQLite 对象及其引用链（有界，绝不抛出）。

    ``exclude`` 是调用方自己的连接（封存连接本身也打开着该文件）。``objects`` 是
    调用方已取得的 ``sqlite_objects()``；它引用每个候选，不算作持有者。
    """
    try:
        return _holder_objects(database, exclude, objects)
    except Exception as exc:  # 诊断绝不改变封存结果
        return [{"error": f"{type(exc).__name__}: {exc}"[:_MAX_TEXT]}]


def _holder_objects(
    database: str | os.PathLike[str] | None,
    exclude: object | None,
    objects: list[Any] | None,
) -> list[dict[str, Any]]:
    target = os.path.realpath(database) if database is not None else None
    found: dict[str, list[Any]] = {kind: [] for kind in _HOLDER_KINDS}
    candidates = sqlite_objects() if objects is None else objects
    for obj in candidates:
        if obj is exclude:
            continue
        kind = _classify(obj, target)
        if kind is not None and len(found[kind]) < MAX_HOLDERS:
            found[kind].append(obj)
    del candidates
    ordered = [(kind, obj) for kind in _HOLDER_KINDS for obj in found[kind]]
    del found
    ordered = ordered[:MAX_HOLDERS]
    ignored = {id(ordered), *(id(pair) for pair in ordered)}
    if objects is not None:
        ignored.add(id(objects))
    # 每一步引用链都扫描整个堆；大进程里总耗时以此为界，超出后只报告种类。
    deadline = time.monotonic() + CHAIN_BUDGET_S
    chains = _chains([obj for _kind, obj in ordered], ignored, deadline)
    return [
        {"kind": kind, "object": _describe(obj), "held_by": chain}
        for (kind, obj), chain in zip(ordered, chains, strict=True)
    ]


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


def _chains(objs: list[object], ignored: set[int], deadline: float) -> list[list[str]]:
    """每个候选沿第一个外部引用者向上，直到模块、函数、正在运行的帧、长度或时间上限。

    所有候选一起走：每一步一次全堆遍历（另加至多一次找 ``__dict__`` 的所有者），
    与候选数无关（原先每个候选每一步各遍历一次，每个 dict 引用者再各遍历一次）。
    """
    running = _running_frames()
    chains: list[list[str]] = [[] for _ in objs]
    seen = [set(ignored) for _ in objs]
    current = list(objs)
    # 本函数自己引用候选的容器不是持有者。
    own = {id(objs), id(current)}
    active = list(range(len(objs)))
    for _ in range(MAX_CHAIN):
        if not active:
            break
        if time.monotonic() > deadline:
            for index in active:
                chains[index].append(CHAIN_TRUNCATED)
            break
        for index in active:
            seen[index].add(id(current[index]))
        chosen = _first_referrers(
            tuple(current[index] for index in active),
            [seen[index] for index in active],
            running,
            own,
        )
        still: list[int] = []
        for index, referrer in zip(active, chosen, strict=True):
            if referrer is None:
                continue
            chains[index].append(_describe(referrer))
            if not isinstance(referrer, _CHAIN_ENDS) and id(referrer) not in running:
                current[index] = referrer
                still.append(index)
        # 上一步的引用者就是下一步的目标：不能让这个列表出现在下一步的引用者中。
        del chosen
        active = still
    return chains


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


def _first_referrers(
    targets: tuple[object, ...],
    seen: list[set[int]],
    running: set[int],
    own: set[int],
) -> list[object | None]:
    """一次全堆遍历，为每个目标选出它的第一个外部引用者（没有则为 None）。

    ``targets`` 自身与 ``own`` 中调用方的容器都引用目标，不算作引用者。
    """
    slots: dict[int, list[int]] = {}
    for slot, target in enumerate(targets):
        slots.setdefault(id(target), []).append(slot)
    candidates: list[list[object]] = [[] for _ in targets]
    referrer: object
    for referrer in gc.get_referrers(*targets):
        if referrer is targets or id(referrer) in own or _own_frame(referrer):
            continue
        hit: set[int] = set()
        for child in gc.get_referents(referrer):
            for slot in slots.get(id(child), ()):
                if slot not in hit and id(referrer) not in seen[slot]:
                    hit.add(slot)
                    candidates[slot].append(referrer)
    chosen: list[object | None] = [None] * len(targets)
    # 正在运行的帧把对象当局部变量引用时最直接；否则取第一个外部引用者。
    for slot, found in enumerate(candidates):
        chosen[slot] = next((r for r in found if id(r) in running), None)
    pending = [slot for slot in range(len(targets)) if chosen[slot] is None]
    owners = _dict_owners(
        [r for slot in pending for r in candidates[slot] if isinstance(r, dict)]
    )
    for slot in pending:
        for referrer in candidates[slot]:
            owner = owners.get(id(referrer))
            if owner is not None and id(owner) not in seen[slot]:
                seen[slot].add(id(referrer))
                referrer = owner
            # 连接自己的语句缓存（``functools.lru_cache`` 包装连接本身）不是持有者。
            if getattr(referrer, "__wrapped__", None) is targets[slot]:
                continue
            chosen[slot] = referrer
            break
    return chosen


def _dict_owners(mappings: list[dict[Any, Any]]) -> dict[int, object]:
    """实例或模块的 ``__dict__`` 换成其所有者，便于读出“哪个类型的属性”。

    一次全堆遍历找出全部所有者；按 ``id(mapping)`` 返回。
    """
    if not mappings:
        return {}
    wanted = {id(mapping) for mapping in mappings}
    owners: dict[int, object] = {}
    referrer: object
    for referrer in gc.get_referrers(*mappings):
        # 帧、列表与调用方的容器没有 ``__dict__``，在此跳过。
        try:
            mapping = referrer.__dict__
        except Exception:  # noqa: BLE001 - 尽力而为（无 ``__dict__`` 或访问出错）
            continue
        if id(mapping) in wanted and id(mapping) not in owners:
            owners[id(mapping)] = referrer
    return owners
