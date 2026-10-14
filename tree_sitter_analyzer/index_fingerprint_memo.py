"""按数据库字节摘要缓存索引指纹的进程内备忘录（#1561）。

``index_fingerprint`` 对每张查询可见表做全行排序哈希，成本与索引行数成正比：
在本仓库（约 2.4k 文件、48 万行）实测约 18 秒，超过每次快照捕获的期限，
导致中等规模仓库的 symbol/pulse/resolve 每次都返回 ``INDEX_SNAPSHOT_DEADLINE``。

指纹是数据库逻辑内容的纯函数；逻辑内容又由主库与 WAL 的完整字节唯一决定。
因此以「项目根 + 主库/WAL 字节的 SHA-256」为键复用指纹是内容寻址的：
字节不同（包括任何重写、失效标记或增量同步）必然换键并重新计算，
不依赖 mtime、大小或文件 ID 等可伪造或粗粒度的元数据。
备忘录只缓存已成功计算的结果，失败与超时从不入表。
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from collections.abc import Callable

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
    """
    if key is None:
        return compute()
    with _MEMO_LOCK:
        cached = _MEMO.get(key)
        if cached is not None:
            _MEMO.move_to_end(key)
            return cached
    fingerprint = compute()
    with _MEMO_LOCK:
        _MEMO[key] = fingerprint
        _MEMO.move_to_end(key)
        while len(_MEMO) > _MEMO_CAPACITY:
            _MEMO.popitem(last=False)
    return fingerprint


def memoized_projection_exact(
    key: tuple[str, ...] | None, compute: Callable[[], bool]
) -> bool:
    """符号投影精确性同为数据库内容的纯函数，按同一内容键复用判定。

    实测其全表核验在本仓库占每次捕获 3-5 秒；判定失败或超时同样不入表。
    """
    if key is None:
        return compute()
    verdict = memoized_index_fingerprint(
        ("symbol_projection_exact", *key), lambda: "1" if compute() else "0"
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
