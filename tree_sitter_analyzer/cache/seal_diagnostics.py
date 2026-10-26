"""封存忙时记录谁还打开着私有版本（#1831）。

#1822 之后封存忙在 CI 上仍偶发（等满 10 s 后 ``SealBusy``），但持有者从未被看到。
这里在第一次忙与期满时收集有界的证据并写入警告日志：

* ``/proc/locks`` 中该文件 inode 上的 POSIX 锁及其进程号——区分本进程与其他进程；
* 本进程指向该文件的描述符数量（``/proc/self/fd``）；
* 本进程中仍打开的 ``sqlite3.Connection`` 数量，以及活动线程名。

证据只用于诊断，任何一步失败都跳过该项，不改变封存结果。
"""

from __future__ import annotations

import gc
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

_MAX_ITEMS = 20


def holder_evidence(database: str | os.PathLike[str] | None) -> dict[str, Any]:
    """返回关于 ``database`` 持有者的有界证据（尽力而为，绝不抛出）。"""
    evidence: dict[str, Any] = {
        "pid": os.getpid(),
        "threads": [thread.name for thread in threading.enumerate()][:_MAX_ITEMS],
        "open_connections": _open_connection_count(),
    }
    if database is None:
        return evidence
    path = Path(database)
    try:
        inode = path.stat().st_ino
    except OSError:
        return evidence
    locks = _posix_locks(inode)
    if locks is not None:
        evidence["posix_locks"] = locks
    descriptors = _own_descriptors(path)
    if descriptors is not None:
        evidence["own_descriptors"] = descriptors
    return evidence


def _open_connection_count() -> int:
    count = 0
    try:
        objects = gc.get_objects()
    except Exception:  # nosec B110 - 诊断尽力而为
        return -1
    for obj in objects:
        if isinstance(obj, sqlite3.Connection):
            try:
                obj.total_changes  # noqa: B018 - 已关闭的连接在此抛出
            except sqlite3.ProgrammingError:
                continue
            except Exception:  # nosec B112 - 其他线程的连接等
                pass
            count += 1
    return count


def _posix_locks(inode: int) -> list[str] | None:
    """``/proc/locks`` 中该 inode 的锁行（仅 Linux）；不可读时为 None。"""
    try:
        lines = Path("/proc/locks").read_text(encoding="ascii").splitlines()
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


def _own_descriptors(path: Path) -> int | None:
    """本进程指向 ``path`` 的描述符数（仅有 ``/proc/self/fd`` 的平台）。"""
    directory = Path("/proc/self/fd")
    try:
        entries = list(directory.iterdir())
        target = os.path.realpath(path)
    except OSError:
        return None
    count = 0
    for entry in entries:
        try:
            if os.path.realpath(os.readlink(entry)) == target:
                count += 1
        except OSError:
            continue
    return count
