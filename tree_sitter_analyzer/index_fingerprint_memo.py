"""按数据库字节摘要缓存索引指纹的进程内备忘录（#1561）。

``index_fingerprint`` 对每张查询可见表做全行排序哈希，成本与索引行数成正比：
在本仓库（约 2.4k 文件、48 万行）实测约 18 秒，超过每次快照捕获的期限，
导致中等规模仓库的 symbol/pulse/resolve 每次都返回 ``INDEX_SNAPSHOT_DEADLINE``。

指纹是数据库逻辑内容的纯函数；逻辑内容又由主库与 WAL 的完整字节唯一决定。
因此以「项目根 + 主库/WAL 字节的 SHA-256」为键复用指纹是内容寻址的：
字节不同（包括任何重写、失效标记或增量同步）必然换键并重新计算，
不依赖 mtime、大小或文件 ID 等可伪造或粗粒度的元数据。
备忘录只缓存已成功计算的结果，失败与超时从不入表。

#1700：同一键另有跨进程的落盘层（``index_fingerprint_store``），冷进程取用时按
完整键逐元素复核；键仍由每次捕获现算的字节摘要构成。
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from collections.abc import Callable

from . import index_fingerprint_store

# 快照注册表最多 16 个活跃能力，每个数据库版本占指纹与投影判定两项；
# 每项仅一个短字符串，内存可忽略。
_MEMO_CAPACITY = 32
_MEMO: OrderedDict[tuple[str, ...], str] = OrderedDict()
_MEMO_LOCK = threading.Lock()


def memoized_index_fingerprint(
    key: tuple[str, ...] | None, compute: Callable[[], str]
) -> str:
    """命中则返回同一字节内容的既有指纹，否则计算并按 LRU 有界保存。

    ``key`` 为 None 表示调用方无法给出内容摘要，此时总是重新计算。
    ``key[0]`` 为项目根：#1700 起进程内未命中时先查该项目的落盘记录
    （``index_fingerprint_store``，按完整键逐元素复核），新算出的值也写回。
    """
    if key is None:
        return compute()
    return _memoized(key, compute, key[0])


def _memoized(key: tuple[str, ...], compute: Callable[[], str], root: str) -> str:
    with _MEMO_LOCK:
        cached = _MEMO.get(key)
        if cached is not None:
            _MEMO.move_to_end(key)
            return cached
    stored = index_fingerprint_store.lookup(root, key)
    fingerprint = stored if stored is not None else compute()
    with _MEMO_LOCK:
        _MEMO[key] = fingerprint
        _MEMO.move_to_end(key)
        while len(_MEMO) > _MEMO_CAPACITY:
            _MEMO.popitem(last=False)
    if stored is None:
        index_fingerprint_store.store(root, key, fingerprint)
    return fingerprint


def memo_compute_deadline(
    key: tuple[str, ...] | None, deadline: float, now: float, budget_seconds: float
) -> float:
    """#1634：可入备忘录的计算用整段计算预算，而非单次捕获剩余的期限。

    dogfood 第 6 轮复现：本仓库（2,458 文件）的指纹计算实测 8.2–9.4 秒，与
    10 秒捕获期限只差约 1 秒，负载稍高即在期限处中断。失败从不入表，于是之后
    每次捕获都从头重算、再次超时——``nav callers`` 每次固定付出约 10 秒 CPU，
    永不收敛。有内容键时让计算在 ``budget_seconds`` 内完成并入表：本次捕获仍按
    原期限如实报告超时，下一次即命中备忘录。无内容键时结果不会被复用，延长
    只会拖慢本次调用，因此保持原期限。
    """
    if key is None:
        return deadline
    return max(deadline, now + budget_seconds)


def memoized_projection_exact(
    key: tuple[str, ...] | None, compute: Callable[[], bool]
) -> bool:
    """符号投影精确性同为数据库内容的纯函数，按同一内容键复用判定。

    实测其全表核验在本仓库占每次捕获 3-5 秒；判定失败或超时同样不入表。
    """
    if key is None:
        return compute()
    verdict = _memoized(
        ("symbol_projection_exact", *key),
        lambda: "1" if compute() else "0",
        key[0],
    )
    return verdict == "1"


def pinned_fd_content_key(
    fd: int, size: int, check_deadline: Callable[[], None]
) -> tuple[str, ...]:
    """对已固定的只读主库句柄做完整字节摘要，读多读少均视为并发写入。"""
    digest = hashlib.sha256()
    remaining = size
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        while remaining:
            check_deadline()
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("CONCURRENT_WRITER")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise ValueError("CONCURRENT_WRITER")
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
    return (f"index.db:{digest.hexdigest()}",)


def clear_index_fingerprint_memo() -> None:
    """清空备忘录；供测试隔离与进程内显式失效使用。"""
    with _MEMO_LOCK:
        _MEMO.clear()
