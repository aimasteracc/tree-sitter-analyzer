"""Bounded source-scope certification for pathname-only platforms."""

from __future__ import annotations

import fnmatch
import os
import stat
import threading
import time
from pathlib import Path
from typing import Any

from .constants import EXCLUDE_DIRS
from .index_source_scope import SourceScopeDescriptor
from .index_source_snapshot import CurrentSourceSnapshot, inventory_fingerprint
from .index_source_stream import hash_source_at
from .indexing_limits import KNOWLEDGE_INDEX_MAX_FILES
from .languages.lang_extension_map import EXT_TO_LANG

_SOURCE_BYTE_BUDGET = 512 * 1024 * 1024
_SOURCE_ENTRY_BUDGET = 1_000_000
_SOURCE_PATH_BYTE_BUDGET = 128 * 1024 * 1024


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
        int(getattr(info, "st_file_attributes", 0)),
    )


def _marker(info: os.stat_result) -> str:
    return (
        f"{info.st_dev}:{info.st_ino}:{info.st_size}:"
        f"{info.st_mtime_ns}:{info.st_ctime_ns}"
    )


def _is_reparse(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return stat.S_ISLNK(info.st_mode) or bool(reparse and attributes & reparse)


def _same(before: os.stat_result, after: os.stat_result) -> bool:
    return _identity(before) == _identity(after)


def _suffix(name: str) -> str:
    """与 ``PurePath.suffix.lower()`` 相同的扩展名规则（含 ``.bashrc`` 无扩展名）。"""
    dot = name.rfind(".")
    if 0 < dot < len(name) - 1:
        return name[dot:].lower()
    return ""


def _may_be_directory(entry: os.DirEntry[str]) -> bool:
    """目录枚举记下的类型（不跟随链接）可能是目录；读不到类型时按可能处理。

    只用于跳过不支持扩展名的项：它们只有在 ``lstat`` 判为目录时才会被处理，而
    目录（含 junction）在这里总是返回 True，交给 ``lstat`` 判定。
    """
    try:
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return True


def _scope_root(project_root: Path, relative: str) -> Path:
    normalized = relative.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in ("", "."))
    if normalized.startswith("/") or any(part == ".." for part in parts):
        raise OSError("source root escapes project")
    return project_root.joinpath(*parts)


#: #1835：并行处理目录与文件项的线程数。每项的 ``lstat``、元数据变更时间与
#: 内容读取都是释放 GIL 的系统调用；串行时它们占认证捕获的大半（fastapi 约
#: 1.2k 文件、四遍扫描 2–5 s）。实测 4 个线程最快：更多线程只在 GIL 上争用。
_WALK_WORKERS = max(1, min(4, os.cpu_count() or 1))
#: 一个任务处理的目录项数：大目录拆成多块并行，小目录各自成一块。
_WALK_CHUNK = 32

#: 一次任务的结果：(后续任务, 行, (相对路径, 原因) 标记)；字符串为提前终止的原因。
_Task = tuple[Any, ...]
_Outcome = tuple[list[_Task], list[tuple[str, str, str]], list[tuple[str, str]]] | str


class _Walk:
    """一遍清单扫描的共享状态：预算计数、支持文件数与待复核的目录（线程安全）。

    #1835：与原串行扫描逐项执行相同的检查、按相同的规则给出相同的行与结论；
    只是不同目录（以及大目录的不同分块）的系统调用并发进行。
    """

    def __init__(self, scope: SourceScopeDescriptor, deadline: float) -> None:
        self.scope = scope
        self.deadline = deadline
        self.limit = min(scope.certification_max_files, KNOWLEDGE_INDEX_MAX_FILES)
        self.counters = {"entries": 0, "path_bytes": 0, "input": 0, "output": 0}
        self.supported = 0
        #: 已扫描的目录与扫描前的身份；整遍结束后逐一复核（不早于原来的复核时刻）。
        self.scanned: list[tuple[str, os.stat_result]] = []
        self._lock = threading.Lock()

    def scan(
        self, directory: str, directory_relative: str, discovered: Any
    ) -> _Outcome:
        """复核排队目录的身份并枚举其项；返回处理各分块的后续任务。"""
        try:
            directory_before = os.lstat(directory)
            if (
                not stat.S_ISDIR(directory_before.st_mode)
                or _is_reparse(directory_before)
                or _identity(directory_before) != _identity(discovered)
            ):
                return "dir_identity_changed"
            with self._lock:
                self.scanned.append((directory, directory_before))
            candidates: list[tuple[str, str, str, str | None]] = []
            with os.scandir(directory) as entries:
                for entry in entries:
                    if time.monotonic() > self.deadline:
                        raise TimeoutError
                    name = entry.name
                    relative = (
                        f"{directory_relative}/{name}" if directory_relative else name
                    )
                    self._count_entry(relative)
                    language = EXT_TO_LANG.get(_suffix(name))
                    if language is None and not _may_be_directory(entry):
                        # #1778：不支持的非目录项无论 lstat 结果如何都跳过，不为它
                        # 付一次打开文件的 lstat（Windows 上每次约 0.1–0.2 ms，
                        # fastapi 一遍扫描约 2 千次）。扫描期间换成目录的项会改变
                        # 所在目录的身份，由整遍结束后的目录身份复核标为不安全。
                        continue
                    candidates.append((entry.path, name, relative, language))
        except OSError:
            return "walk_oserror"
        tasks: list[_Task] = [
            (self.entries, candidates[start : start + _WALK_CHUNK])
            for start in range(0, len(candidates), _WALK_CHUNK)
        ]
        return tasks, [], []

    def _count_entry(self, relative: str) -> None:
        size = len(relative.encode("utf-8", "surrogatepass"))
        with self._lock:
            self.counters["entries"] += 1
            self.counters["path_bytes"] += size
            if (
                self.counters["entries"] > _SOURCE_ENTRY_BUDGET
                or self.counters["path_bytes"] > _SOURCE_PATH_BYTE_BUDGET
            ):
                raise OverflowError

    def entries(self, chunk: list[tuple[str, str, str, str | None]]) -> _Outcome:
        """逐项 ``lstat`` 分类：子目录排队，支持的普通文件按句柄读取摘要。"""
        tasks: list[_Task] = []
        rows: list[tuple[str, str, str]] = []
        flags: list[tuple[str, str]] = []
        try:
            for path, name, relative, language in chunk:
                if time.monotonic() > self.deadline:
                    raise TimeoutError
                before = os.lstat(path)
                if stat.S_ISDIR(before.st_mode):
                    if name in EXCLUDE_DIRS or name.startswith("."):
                        continue
                    if _is_reparse(before):
                        continue
                    tasks.append((self.scan, path, relative, before))
                    continue
                if _is_reparse(before):
                    if language is not None:
                        flags.append((relative, "reparse_supported_file"))
                    continue
                if language is None or any(
                    fnmatch.fnmatch(relative, pattern)
                    for pattern in self.scope.effective_excludes
                ):
                    continue
                if not stat.S_ISREG(before.st_mode):
                    flags.append((relative, "supported_not_regular"))
                    continue
                self._count_supported()
                digest, clean = self._hash(path, before)
                if not clean:
                    flags.append((relative, "hash_unclean"))
                rows.append((relative, digest, language))
        except OSError:
            return "walk_oserror"
        return tasks, rows, flags

    def _count_supported(self) -> None:
        with self._lock:
            self.supported += 1
            if self.supported > self.limit:
                raise OverflowError

    def _hash(self, path: str, before: os.stat_result) -> tuple[str, bool]:
        """一个文件的摘要；字节预算与原串行扫描相同，按全部文件累计。"""
        with self._lock:
            local = {
                "input": self.counters["input"],
                "output": self.counters["output"],
            }
        start = dict(local)
        _marker_value, digest, clean = hash_source_at(
            None,
            path,
            before,
            self.deadline,
            local,
            _SOURCE_BYTE_BUDGET,
            _marker,
            _same,
        )
        with self._lock:
            for key in ("input", "output"):
                self.counters[key] += local[key] - start[key]
                if self.counters[key] > _SOURCE_BYTE_BUDGET:
                    raise OverflowError
        return digest, clean


def _run_walk(
    walk: _Walk, first: _Task
) -> tuple[set[tuple[str, str, str]], list[tuple[str, str]], str | None]:
    """并发执行一个范围根下的全部任务；返回 (行, 标记, 提前终止的原因)。

    任一任务抛出的预算异常原样传播（与串行扫描相同）；提前终止或异常时不再开始
    新任务，并等正在运行的任务结束后才返回。
    """
    run = _WalkRun(first)
    if _WALK_WORKERS <= 1:
        run.work()
    else:
        workers = [
            threading.Thread(
                target=run.work, name=f"tsa-source-walk-{index}", daemon=True
            )
            for index in range(_WALK_WORKERS)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
    if run.error is not None:
        raise run.error
    return run.rows, run.flags, run.stopped


class _WalkRun:
    """一个范围根的任务队列：工作线程取任务、并入结果、把后续任务放回队列。

    首个提前终止原因或异常结束整遍扫描：之后不再取新任务，正在运行的任务完成后
    其结果被丢弃。队列按后进先出取用（与原串行扫描的栈相同的深度优先倾向）。
    """

    def __init__(self, first: _Task) -> None:
        self.rows: set[tuple[str, str, str]] = set()
        self.flags: list[tuple[str, str]] = []
        self.stopped: str | None = None
        self.error: BaseException | None = None
        self._queue: list[_Task] = [first]
        #: 已排队与正在运行的任务数；归零即整遍完成。
        self._outstanding = 1
        self._done = False
        self._condition = threading.Condition()

    def work(self) -> None:
        while True:
            with self._condition:
                while not self._queue and self._outstanding and not self._done:
                    self._condition.wait()
                if self._done or not self._outstanding:
                    return
                task = self._queue.pop()
            try:
                outcome: Any = task[0](*task[1:])
            except BaseException as exc:  # noqa: BLE001 — 交给调用线程原样抛出
                outcome = exc
            self._finish(outcome)

    def _finish(self, outcome: Any) -> None:
        with self._condition:
            self._outstanding -= 1
            if self._done:
                pass
            elif isinstance(outcome, BaseException):
                self.error = outcome
                self._done = True
            elif isinstance(outcome, str):
                self.stopped = outcome
                self._done = True
            else:
                tasks, found, flagged = outcome
                self.rows.update(found)
                self.flags.extend(flagged)
                self._queue.extend(tasks)
                self._outstanding += len(tasks)
            self._condition.notify_all()


def _portable_inventory(
    project_root: str,
    scope: SourceScopeDescriptor,
    deadline: float,
) -> tuple[frozenset[tuple[str, str, str]], str | None]:
    """Hash one bounded pathname inventory without following directory links.

    返回 (rows, unsafe_reason);unsafe_reason 为 None 表示安全,否则给出
    具体触发的安全检查名(#1364/#1373 诊断:满载 CI 上的 unsafe 需要
    区分是目录身份漂移、双走不一致还是哈希不洁)。
    """
    project = Path(project_root)
    root_before = os.lstat(project)
    if not stat.S_ISDIR(root_before.st_mode) or _is_reparse(root_before):
        return frozenset(), "root_reparse_or_not_dir"
    rows: set[tuple[str, str, str]] = set()
    walk = _Walk(scope, deadline)
    # #1364/#1373 诊断:记录首个触发的安全检查名,None=安全
    unsafe_reason: str | None = None

    def _flag(reason: str) -> None:
        nonlocal unsafe_reason
        if unsafe_reason is None:
            unsafe_reason = reason

    for relative_root in scope.roots:
        base = _scope_root(project, relative_root)
        try:
            base_before = os.lstat(base)
        except OSError:
            return frozenset(), "scope_root_stat_failed"
        if not stat.S_ISDIR(base_before.st_mode) or _is_reparse(base_before):
            return frozenset(), "scope_root_reparse_or_not_dir"
        # #1561：相对路径随任务以字符串前缀传递；逐项 Path.relative_to 曾占单遍
        # 扫描约 18% 的耗时（2,401 文件实测 0.85/4.74 秒），结果逐字节相同。
        base_relative = base.relative_to(project).as_posix()
        first = (
            walk.scan,
            str(base),
            "" if base_relative == "." else base_relative,
            base_before,
        )
        found, flags, stopped = _run_walk(walk, first)
        if stopped is not None:
            return frozenset(), stopped
        rows.update(found)
        # 标记按相对路径排序后取首个：并发完成顺序不影响诊断原因。
        for _relative, reason in sorted(flags):
            _flag(reason)
        # 已扫描目录的身份在整遍结束后复核：复核窗口覆盖原先“扫完该目录即复核”的
        # 窗口，目录项在扫描期间的增删改名同样被标为不安全。
        scanned, walk.scanned = walk.scanned, []
        for directory, directory_before in scanned:
            if _identity(os.lstat(directory)) != _identity(directory_before):
                _flag("dir_identity_changed")
        if _identity(os.lstat(base)) != _identity(base_before):
            _flag("scope_root_identity_changed")
    if _identity(os.lstat(project)) != _identity(root_before):
        _flag("project_root_identity_changed")
    return frozenset(rows), unsafe_reason


def capture_portable_source_snapshot(
    project_root: str,
    source_scope: SourceScopeDescriptor,
    *,
    deadline: float,
) -> CurrentSourceSnapshot:
    """在调用者给定的总期限内双次扫描；不一致与超时均拒绝认证。"""
    root = os.path.abspath(project_root)
    try:
        first, unsafe_first = _portable_inventory(root, source_scope, deadline)
        second, unsafe_second = _portable_inventory(root, source_scope, deadline)
        fingerprint = inventory_fingerprint(first, deadline=deadline)
    except TimeoutError:
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unknown", "SOURCE_SCAN_DEADLINE"
        )
    except OverflowError:
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unknown", "SOURCE_SCOPE_UNBOUNDED"
        )
    except OSError:
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unknown", "SOURCE_SCOPE_UNREADABLE"
        )
    generation = "idxsrc-v3:" + fingerprint.removeprefix("sha256:")
    if unsafe_first or unsafe_second or first != second:
        detail = unsafe_first or unsafe_second or "walk_mismatch"
        return CurrentSourceSnapshot(
            first, fingerprint, generation, "unsafe", f"SOURCE_SCOPE_UNSAFE:{detail}"
        )
    return CurrentSourceSnapshot(first, fingerprint, generation, "exact", None)
