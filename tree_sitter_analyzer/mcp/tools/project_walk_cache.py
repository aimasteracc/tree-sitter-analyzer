"""#1607 / #1624 目录遍历的进程内记忆：只在目录列表证据未变时复用。

dogfood 第 7 轮：``nav callers`` 的“未入索引的新文件”门每次都完整遍历项目树
并对每一项做 ``.gitignore`` 匹配，在约 2,900 个文件的仓库上占单次调用约 1 s。
遍历结果只取决于：

* 每个被列出的目录的条目（名字与类型）；
* 这些目录及其祖先目录中的忽略规则文件（``.gitignore`` / ``.ignore`` /
  ``.rgignore``）的内容；
* 调用参数（排除目录名、条目 / 路径字节预算）。

增删改名任何条目都会更新所在目录的 mtime（NTFS 与 POSIX 皆然），因此记忆绑定
每个被列出目录的 ``lstat`` 身份与每个已存在规则文件的 ``lstat`` 身份；取用时
全部重新 ``lstat``，任一不同即重新遍历。规则文件的新建 / 删除同样改变目录 mtime。

时间戳竞争（racy-git）：遍历期间或之前 :data:`RACY_WINDOW_NS` 内修改过的目录 /
规则文件，其 mtime 无法区分“遍历前”与“遍历后”的写入，这样的结果不入记忆。
遍历失败（预算超限、列表错误）从不入记忆，异常原样抛出。

#1691：``persist=True`` 时同一份条目还写入 ``walk_evidence_store``；进程内未命中
时先读落盘条目，并以与进程内相同的 ``_still_valid`` 全部重新 lstat 复核。
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable

from ...ignore_rules import IGNORE_RULE_FILES
from . import walk_evidence_store

#: 与 ``evidence_file_cache`` 相同的竞争窗口（覆盖 FAT 2 s 粒度并留余量）。
RACY_WINDOW_NS = 5_000_000_000
#: 记忆条目上限（每个 项目根 × 起点 × 参数 一条）。
MAX_ENTRIES = 8

_StatKey = tuple[int, int, int, int, int, int]
_Evidence = tuple[tuple[str, _StatKey], ...]


def _lstat_key(path: str) -> _StatKey | None:
    try:
        info = os.lstat(path)
    except OSError:
        return None
    return (
        int(info.st_mode),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
        int(info.st_ino),
        int(info.st_dev),
    )


def _ancestors(start_relative: str) -> list[str]:
    """``start_relative`` 之上的目录（含项目根 ``""``），不含其自身。"""
    normalized = os.path.normpath(start_relative) if start_relative else ""
    if normalized in ("", "."):
        return []
    parts = normalized.split(os.sep)
    return [""] + [os.path.join(*parts[:index]) for index in range(1, len(parts))]


class ProjectWalkCache:
    """以目录 / 规则文件 ``lstat`` 证据为键的遍历结果记忆（线程安全、有界）。"""

    def __init__(self, max_entries: int = MAX_ENTRIES, *, persist: bool = False) -> None:
        self._max_entries = max_entries
        # #1691：为真时同一份条目也落盘（``walk_evidence_store``），冷进程复核后复用。
        self._persist = persist
        self._entries: OrderedDict[
            tuple[object, ...], tuple[_Evidence, tuple[str, ...]]
        ] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def walk(
        self,
        project_root: str,
        key: tuple[object, ...],
        start_relative: str,
        walker: Callable[[list[str]], Iterable[str]],
    ) -> tuple[str, ...]:
        """返回 ``walker`` 的结果；证据未变时复用上次结果。

        ``walker(visited_dirs)`` 必须把它列出的每个目录（相对路径）追加到
        ``visited_dirs`` 并返回全部产出路径；它抛出的异常原样传播。
        """
        full_key = (os.path.abspath(project_root), start_relative, *key)
        with self._lock:
            cached = self._entries.get(full_key)
        if cached is not None and self._still_valid(cached[0]):
            with self._lock:
                if full_key in self._entries:
                    self._entries.move_to_end(full_key)
            return cached[1]
        stored_key = self._stored_key(full_key)
        stored = self._load_stored(project_root, stored_key)
        if stored is not None:
            self._remember(full_key, stored)
            return stored[1]
        started_ns = time.time_ns()
        visited: list[str] = []
        paths = tuple(walker(visited))
        evidence = self._collect(project_root, start_relative, visited, started_ns)
        if evidence is None:
            with self._lock:
                self._entries.pop(full_key, None)
            return paths
        self._remember(full_key, (evidence, paths))
        if stored_key is not None:
            walk_evidence_store.save(project_root, stored_key, evidence, paths)
        return paths

    def _remember(
        self, full_key: tuple[object, ...], entry: tuple[_Evidence, tuple[str, ...]]
    ) -> None:
        with self._lock:
            self._entries[full_key] = entry
            self._entries.move_to_end(full_key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def _stored_key(self, full_key: tuple[object, ...]) -> str | None:
        if not (self._persist and walk_evidence_store.enabled()):
            return None
        return walk_evidence_store.key_text(full_key)

    def _load_stored(
        self, project_root: str, stored_key: str | None
    ) -> tuple[_Evidence, tuple[str, ...]] | None:
        """落盘条目，且其每条证据重新 lstat 后仍相同；否则 None。"""
        if stored_key is None:
            return None
        stored = walk_evidence_store.load(project_root, stored_key)
        if stored is None or not self._still_valid(stored[0]):
            return None
        return stored

    @staticmethod
    def _still_valid(evidence: _Evidence) -> bool:
        return all(_lstat_key(path) == expected for path, expected in evidence)

    @staticmethod
    def _collect(
        project_root: str,
        start_relative: str,
        visited: list[str],
        started_ns: int,
    ) -> _Evidence | None:
        """遍历后的证据；任一证据不可读或处于竞争窗口内则为 None（不记忆）。"""
        racy_after = started_ns - RACY_WINDOW_NS
        evidence: list[tuple[str, _StatKey]] = []
        for relative in [*_ancestors(start_relative), *visited]:
            directory = (
                os.path.join(project_root, relative) if relative else project_root
            )
            key = _lstat_key(directory)
            if key is None or key[2] >= racy_after:
                return None
            evidence.append((directory, key))
            for name in IGNORE_RULE_FILES:
                rule_path = os.path.join(directory, name)
                rule_key = _lstat_key(rule_path)
                if rule_key is None:
                    # 不存在：其新建会改变所在目录的 mtime，由目录证据覆盖。
                    continue
                if rule_key[2] >= racy_after:
                    return None
                evidence.append((rule_path, rule_key))
        return tuple(evidence)


#: 进程级共享实例；条目同时落盘，供新进程复核后复用（#1691）。
WALK_CACHE = ProjectWalkCache(persist=True)
