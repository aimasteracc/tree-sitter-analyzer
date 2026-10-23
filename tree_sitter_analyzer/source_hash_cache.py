"""按 stat 证据复用源码内容摘要的进程内缓存（#1673）。

Windows 上每次刷新都要按路径为全部源码计算内容摘要：捕获候选一次、发布前复核
一次、认证盖戳的双遍扫描再两次。打开并读取文件受 I/O 与实时扫描支配（#1562 实测
约 17 ms/文件，本机负载高时 35–170 ms），2.5k 文件的仓库仅摘要就要数十秒。

摘要仍是全部新鲜度判定的依据（RFC-0030）；本缓存只避免为**同一份字节**重复读取。
复用规则与 #1651 的 ``EvidenceFileCache`` 相同，绝不只按路径：

* 键为 ``(st_dev, st_ino, st_mode, st_size, st_mtime_ns, 变更时间,
  st_file_attributes)``；任一不同即重新读取。调用方每次都重新 ``lstat``。
  “变更时间”取元数据变更时间（``file_change_time``）：POSIX 为 ``st_ctime``；
  Windows 路径 ``stat`` 的 ``st_ctime`` 是创建时间，改为读取 NTFS ``ChangeTime``，
  否则“改写内容再把 mtime 设回”（大小相同）的文件会被误判为未变。取不到时
  不复用。
* 只缓存“干净”的读取：句柄读取前后的元数据与枚举时一致、摘要不是不安全标记。
  变更时间在读取**之前**取得，读取期间的改写只会让后续查找不匹配。
* 时间戳竞争（racy-git）：mtime 或变更时间距当前不足 :data:`RACY_WINDOW_NS` 的
  文件不入缓存——同一时间戳刻度内的第二次写入不会改变元数据，必须每次重读。
* 条目数有上限（LRU 淘汰）；缓存只存摘要字符串，不存源码字节。

只用于按路径读取的路径平台扫描（``directory_fd is None``）；POSIX 描述符绑定的
扫描不经此缓存。
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict

from .file_change_time import change_time_ns

#: mtime/变更时间与当前相差不足此值的文件不缓存（覆盖 FAT 的 2 s 粒度并留余量）。
RACY_WINDOW_NS = 5_000_000_000
#: 条目上限：每条约 200 字节，20 万条约 40 MB。
MAX_ENTRIES = 200_000

_Key = tuple[int, int, int, int, int, int, int]


def _now_ns() -> int:
    """竞争窗口判定使用的墙钟（测试可替换）。"""
    return time.time_ns()


def stat_key(info: os.stat_result, change_ns: int) -> _Key:
    """复用所需的完整 stat 证据；``change_ns`` 为元数据变更时间。"""
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(change_ns),
        int(getattr(info, "st_file_attributes", 0)),
    )


def evidence(path: str, info: os.stat_result) -> _Key | None:
    """``path`` 当前的复用证据；取不到变更时间时为 ``None``（不得复用）。"""
    change = change_time_ns(path, info)
    return None if change is None else stat_key(info, change)


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


class SourceHashCache:
    """路径 -> (stat 证据, 摘要) 的有界 LRU（线程安全）。"""

    def __init__(self, *, max_entries: int = MAX_ENTRIES) -> None:
        self._max = max_entries
        self._entries: OrderedDict[str, tuple[_Key, str]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self.hits = self.misses = 0

    def lookup(self, path: str, key: _Key | None) -> str | None:
        """``key`` 与上次干净读取时的证据完全相同才返回摘要。"""
        name = _path_key(path)
        with self._lock:
            cached = self._entries.get(name)
            if key is not None and cached is not None and cached[0] == key:
                self._entries.move_to_end(name)
                self.hits += 1
                return cached[1]
            self.misses += 1
            return None

    def store(self, path: str, key: _Key | None, digest: str) -> None:
        """记录一次干净读取（``key`` 在读取前取得）；竞争窗口内只忘记、不缓存。"""
        if key is None:
            self.forget(path)
            return
        now = _now_ns()
        mtime_ns, change_ns = key[4], key[5]
        if now - mtime_ns < RACY_WINDOW_NS or now - change_ns < RACY_WINDOW_NS:
            self.forget(path)
            return
        name = _path_key(path)
        with self._lock:
            self._entries.pop(name, None)
            self._entries[name] = (key, digest)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def forget(self, path: str) -> None:
        with self._lock:
            self._entries.pop(_path_key(path), None)


#: 进程级共享实例（候选捕获、发布复核与认证盖戳共用）。
SOURCE_HASHES = SourceHashCache()
