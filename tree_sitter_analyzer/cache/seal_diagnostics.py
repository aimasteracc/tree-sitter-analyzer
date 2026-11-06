"""封存忙时记录谁还打开着私有版本（#1831）。

#1822 之后封存忙在 CI 上仍偶发（等满 10 s 后 ``SealBusy``），但持有者从未被看到。
这里在第一次忙与期满时收集有界的证据并写入警告日志：

* ``/proc/locks`` 中该文件 inode 上的 POSIX 锁及其进程号——区分本进程与其他进程；
* 本进程指向该文件的描述符数量（``/proc/self/fd``）；
* 本进程中仍打开的 ``sqlite3.Connection`` 数量，以及活动线程名。

证据只用于诊断，任何一步失败都跳过该项，不改变封存结果。

各项证据要找的都是本进程中的 SQLite 连接与游标，由 :func:`sqlite_objects` 统一
查找。逐个遍历 ``gc.get_objects()`` 在大进程里每次要数百毫秒（一百五十万对象约
0.3 s，CI 上整个忙路径因此超过 8 s CPU）；这里改为问回收器"谁引用了这些类型"：
堆类型的实例在遍历时访问自己的类型，一次 C 层遍历即可找出全部实例，约为逐个
遍历的十分之一。首次使用时用探针连接确认这一点成立，否则退回逐个遍历。
"""

from __future__ import annotations

import gc
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

_MAX_ITEMS = 20
#: Linux 的锁表与本进程描述符目录；其他平台不存在，对应证据省略。
PROC_LOCKS = Path("/proc/locks")
PROC_FDS = Path("/proc/self/fd")
_SQLITE_TYPES = (sqlite3.Connection, sqlite3.Cursor)
#: 实例能否经由其类型的引用者找到；``None`` 表示尚未探测。
_type_referrers_work: bool | None = None


def _sqlite_types() -> tuple[type, ...]:
    """连接、游标两种类型及其全部子类（子类实例访问的是子类本身）。"""
    found: list[type] = list(_SQLITE_TYPES)
    index = 0
    while index < len(found):
        found.extend(found[index].__subclasses__())
        index += 1
    return tuple(found)


def _probe_type_referrers() -> bool:
    probe = sqlite3.connect(":memory:")
    try:
        cursor = probe.cursor()
        found = {id(obj) for obj in gc.get_referrers(*_SQLITE_TYPES)}
        cursor.close()
        return id(probe) in found and id(cursor) in found
    finally:
        probe.close()


def sqlite_objects() -> list[Any]:
    """本进程中存活的 ``sqlite3`` 连接与游标（含子类实例与已关闭的连接）。

    失败时抛出；调用方各自把失败记入证据。返回的列表本身也引用这些对象，
    构建引用链的调用方须忽略它。
    """
    global _type_referrers_work
    if _type_referrers_work is None:
        _type_referrers_work = _probe_type_referrers()
    candidates = (
        gc.get_referrers(*_sqlite_types()) if _type_referrers_work else gc.get_objects()
    )
    return [obj for obj in candidates if isinstance(obj, _SQLITE_TYPES)]


def holder_evidence(
    database: str | os.PathLike[str] | None,
    *,
    objects: list[Any] | None = None,
) -> dict[str, Any]:
    """返回关于 ``database`` 持有者的有界证据（尽力而为，绝不抛出）。

    ``objects`` 是调用方已取得的 :func:`sqlite_objects`，用于多项证据共用一次查找。
    """
    try:
        connections: int | str = open_connection_count(objects)
    except Exception as exc:  # noqa: BLE001 - 诊断绝不改变封存结果
        connections = f"{type(exc).__name__}: {exc}"[:160]
    evidence: dict[str, Any] = {
        "pid": os.getpid(),
        "threads": [thread.name for thread in threading.enumerate()][:_MAX_ITEMS],
        "open_connections": connections,
    }
    try:
        inode = Path(database).stat().st_ino if database is not None else None
    except OSError:
        inode = None
    if inode is None:
        return evidence
    locks = posix_locks(inode)
    if locks is not None:
        evidence["posix_locks"] = locks
    descriptors = own_descriptors(Path(str(database)))
    if descriptors is not None:
        evidence["own_descriptors"] = descriptors
    return evidence


def open_connection_count(objects: list[Any] | None = None) -> int:
    """本进程中尚未关闭的 ``sqlite3.Connection`` 数（含其他线程创建的）。"""
    count = 0
    for obj in sqlite_objects() if objects is None else objects:
        if isinstance(obj, sqlite3.Connection):
            try:
                obj.total_changes  # noqa: B018 - 已关闭的连接在此抛出
            except sqlite3.ProgrammingError as exc:
                # 其他线程创建的连接同样抛出 ProgrammingError，但它仍打开。
                if "closed" in str(exc):
                    continue
            count += 1
    return count


def posix_locks(inode: int) -> list[str] | None:
    """锁表中该 inode 的锁（``类型 读写 进程号 起 止``）；锁表不可读时为 None。"""
    try:
        lines = PROC_LOCKS.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    # 行格式：``1: POSIX ADVISORY READ <pid> <maj>:<min>:<inode> <start> <end>``；
    # 等待中的锁行在序号后多一个 ``->``。
    suffix = f":{inode}"
    found: list[str] = []
    for line in lines:
        fields = [field for field in line.split() if field != "->"]
        if len(fields) >= 8 and fields[5].endswith(suffix):
            found.append(" ".join((fields[1], fields[3], fields[4], *fields[6:8])))
    return found[:_MAX_ITEMS]


def own_descriptors(path: Path) -> int | None:
    """本进程指向 ``path`` 的描述符数；没有描述符目录时为 None。"""
    try:
        entries = list(PROC_FDS.iterdir())
    except OSError:
        return None
    target = os.path.realpath(path)
    count = 0
    for entry in entries:
        try:
            count += os.path.realpath(os.readlink(entry)) == target
        except OSError:
            continue
    return count
