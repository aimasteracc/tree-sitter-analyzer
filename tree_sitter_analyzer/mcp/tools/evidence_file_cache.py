"""nav callers 完整性门的进程内文件字节缓存：只按能证明“未变”的元数据复用。

dogfood 第 7 轮：同一 MCP 进程中每次 ``nav callers`` 都重新打开并读取约 1,700 个
同语言源码文件（非调用引用扫描，#1598）以及声明文件（访问器 / 装饰器门），
在 Windows 上占单次调用的大头。这些门不能跳过，但同一字节无需每次从磁盘重读。

复用条件（RFC-0030：绝不以“仅路径”判定为未变）：

* 每次取用都重新 ``os.stat``，缓存键为 ``(size, mtime_ns, ctime_ns, ino, dev)``；
  任一不同即重读。文件消失或不可 stat 返回 ``None``，与 ``open`` 失败相同。
* 读取前后各 stat 一次，二者不同（读取期间被改写）则只返回本次字节、不入缓存。
* “时间戳竞争”（racy-git）：mtime 距读取时刻不足 :data:`RACY_WINDOW_NS` 的文件
  不入缓存——同一时间戳刻度内的第二次写入不会改变元数据，必须每次重读。
* 总字节数有上限（LRU 淘汰），超过单文件上限的文件从不缓存，内存有界。
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict

#: mtime 与读取时刻相差不足此值的文件不缓存（覆盖 FAT 的 2 s 粒度并留余量）。
RACY_WINDOW_NS = 5_000_000_000
#: 缓存总字节上限。
MAX_TOTAL_BYTES = 256 * 1024 * 1024
#: 单文件字节上限；更大的文件每次都直接读取。
MAX_FILE_BYTES = 8 * 1024 * 1024

_Key = tuple[int, int, int, int, int]


def _stat_key(info: os.stat_result) -> _Key:
    return (
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
        int(info.st_ino),
        int(info.st_dev),
    )


class EvidenceFileCache:
    """按 stat 证据复用文件字节的有界 LRU 缓存（线程安全）。"""

    def __init__(
        self,
        *,
        max_total_bytes: int = MAX_TOTAL_BYTES,
        max_file_bytes: int = MAX_FILE_BYTES,
    ) -> None:
        self._max_total = max_total_bytes
        self._max_file = max_file_bytes
        self._entries: OrderedDict[str, tuple[_Key, bytes]] = OrderedDict()
        self._total = 0
        self._lock = threading.Lock()

    @property
    def total_bytes(self) -> int:
        return self._total

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._total = 0

    def read_bytes(self, path: str) -> bytes | None:
        """``path`` 的当前字节；不可 stat 或不可读为 ``None``（不抛异常）。"""
        try:
            before = os.stat(path)
        except OSError:
            return None
        key = _stat_key(before)
        with self._lock:
            cached = self._entries.get(path)
            if cached is not None and cached[0] == key:
                self._entries.move_to_end(path)
                return cached[1]
        try:
            with open(path, "rb") as handle:
                data = handle.read()
            after = os.stat(path)
        except OSError:
            self._forget(path)
            return None
        if _stat_key(after) != key or self._racy(after):
            self._forget(path)
            return data
        self._store(path, key, data)
        return data

    def read_text(self, path: str) -> str | None:
        """与 ``open(path, encoding="utf-8", errors="replace").read()`` 相同的文本。

        文本模式的通用换行：``\\r\\n`` 与单独的 ``\\r`` 都转换为 ``\\n``。
        """
        data = self.read_bytes(path)
        if data is None:
            return None
        text = data.decode("utf-8", "replace")
        if "\r" in text:
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text

    def _racy(self, info: os.stat_result) -> bool:
        return time.time_ns() - int(info.st_mtime_ns) < RACY_WINDOW_NS

    def _forget(self, path: str) -> None:
        with self._lock:
            old = self._entries.pop(path, None)
            if old is not None:
                self._total -= len(old[1])

    def _store(self, path: str, key: _Key, data: bytes) -> None:
        if len(data) > self._max_file:
            self._forget(path)
            return
        with self._lock:
            old = self._entries.pop(path, None)
            if old is not None:
                self._total -= len(old[1])
            self._entries[path] = (key, data)
            self._total += len(data)
            while self._total > self._max_total and self._entries:
                _evicted, (_key, payload) = self._entries.popitem(last=False)
                self._total -= len(payload)


#: 进程级共享实例（nav callers 的各道完整性门共用）。
FILE_CACHE = EvidenceFileCache()
