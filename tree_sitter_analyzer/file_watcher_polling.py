"""监听专用的分段扫描：只发现变化，不签发全范围源码认证。"""

from __future__ import annotations

import hashlib
import os
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from typing import Any

from .constants import EXCLUDE_DIRS
from .languages.lang_extension_map import EXT_TO_LANG
from .source_oracle import SourceOracleError, safe_workspace_path

_POLL_ENTRIES = 2000
_POLL_SECONDS = 1.0
_FILE_BYTES = 64 * 1024 * 1024


def _reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _open_directory(
    root: str, path: str, parent_fd: int | None = None, expected: Any = None
) -> tuple[Any, int | None]:
    """先固定目录再创建枚举器；POSIX 子目录只通过固定的父描述符打开。"""
    if os.name == "nt":
        return _open_windows_directory(root, path), None
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(
        os.path.basename(path) if parent_fd is not None else path,
        flags,
        dir_fd=parent_fd,
    )
    try:
        opened = os.fstat(fd)
        if expected is not None and (opened.st_dev, opened.st_ino, opened.st_mode) != (
            expected.st_dev,
            expected.st_ino,
            expected.st_mode,
        ):
            raise OSError("watcher directory changed before open")
        return os.scandir(fd), fd
    except BaseException:
        os.close(fd)
        raise


def _open_windows_directory(root: str, path: str) -> Any:
    """只在建立搜索句柄时固定祖先，枚举间隔不持有禁止重命名的句柄。"""
    from .index_snapshot_windows import NativeFiles

    api = NativeFiles()
    relative = os.path.relpath(path, root)
    parts = [] if relative == "." else relative.split(os.sep)
    with ExitStack() as owned:
        directory = root
        for part in [None, *parts]:
            if part is not None:
                directory = os.path.join(directory, part)
            handle = api.open(directory, True)
            owned.callback(api.close, handle)
        return os.scandir(path)


def _close_directory(entries: Any, fd: int | None) -> None:
    """无论枚举器关闭是否成功，都释放所属目录描述符。"""
    try:
        entries.close()
    finally:
        if fd is not None:
            os.close(fd)


def _entries(root: str) -> Iterator[tuple[str, str, Any]]:
    """逐项遍历；异常目录单独报告，其他目录继续。"""
    stack: list[tuple[str, Any, int | None]] = []
    try:
        try:
            entries, fd = _open_directory(root, root)
            stack.append((root, entries, fd))
        except (OSError, ValueError):
            yield "blocked", root, None
            return
        while stack:
            directory, entries, parent_fd = stack[-1]
            try:
                entry = next(entries)
            except StopIteration:
                stack.pop()
                _close_directory(entries, parent_fd)
                continue
            except OSError:
                stack.pop()
                _close_directory(entries, parent_fd)
                yield "blocked", directory, None
                continue
            path = os.path.join(directory, entry.name)
            try:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode) and not _reparse(info):
                    if entry.name not in EXCLUDE_DIRS and not entry.name.startswith(
                        "."
                    ):
                        child, child_fd = _open_directory(root, path, parent_fd, info)
                        stack.append((path, child, child_fd))
                    yield "skip", path, None
                elif os.path.splitext(entry.name)[1].lower() in EXT_TO_LANG:
                    yield "file", path, info
                else:
                    yield "skip", path, None
            except (OSError, ValueError):
                yield "blocked", path, None
    finally:
        for _directory, entries, fd in reversed(stack):
            _close_directory(entries, fd)


class PollingScanner:
    """每轮工作有界，游标跨轮保留；只有遍历完成后才确认删除。"""

    def __init__(self, root: str, on_error: Callable[[], None]) -> None:
        self.root = root
        self.on_error = on_error
        self.snapshot: dict[str, tuple[Any, ...]] = {}
        self._cursor: Iterator[tuple[str, str, Any]] | None = None
        self._retry_entry: tuple[str, str, Any] | None = None
        self._seen: set[str] = set()
        self._blocked: set[str] = set()
        self._warming = False
        self._native: Any = None

    @property
    def in_progress(self) -> bool:
        return self._cursor is not None

    def close(self) -> None:
        self._retry_entry = None
        if self._cursor is not None:
            self._cursor.close()  # type: ignore[attr-defined]
            self._cursor = None

    def scan(self, *, baseline: bool = False) -> list[str]:
        if self._cursor is None:
            self._warming = baseline
            self._cursor = _entries(self.root)
            self._seen.clear()
            self._blocked.clear()
        changed: list[str] = []
        deadline = time.monotonic() + _POLL_SECONDS
        for _ in range(_POLL_ENTRIES):
            if time.monotonic() >= deadline:
                break
            retrying = self._retry_entry is not None
            try:
                if self._retry_entry is not None:
                    kind, path, info = self._retry_entry
                    self._retry_entry = None
                else:
                    kind, path, info = next(self._cursor)
            except StopIteration:
                deleted = [
                    path
                    for path in self.snapshot
                    if path not in self._seen and not self._protected(path)
                ]
                for path in deleted:
                    del self.snapshot[path]
                if not (self._warming or baseline):
                    changed.extend(deleted)
                self._warming = False
                self._cursor = None
                break
            path = os.path.normpath(path)
            if kind == "skip":
                continue
            if kind == "blocked":
                self._blocked.add(path)
                self.on_error()
                continue
            if (
                not stat.S_ISREG(info.st_mode)
                or _reparse(info)
                or info.st_size > _FILE_BYTES
            ):
                # #1405：永久不可读取的替换不算存活，遍历完成后按删除通知失效。
                self.on_error()
                continue
            self._seen.add(path)
            try:
                fingerprint = self._fingerprint(path, deadline)
            except (OSError, SourceOracleError, ValueError):
                self.on_error()
                if not retrying and time.monotonic() >= deadline:
                    # 片尾失败只补一次完整预算；持续失败必须让后续文件继续前进。
                    self._retry_entry = (kind, path, info)
                    break
                continue
            if (
                not (baseline or self._warming)
                and self.snapshot.get(path) != fingerprint
            ):
                changed.append(path)
            self.snapshot[path] = fingerprint
        return sorted(changed)

    def _protected(self, path: str) -> bool:
        while True:
            if path in self._blocked:
                return True
            parent = os.path.dirname(path)
            if parent == path:
                return False
            path = parent

    def _fingerprint(self, path: str, deadline: float) -> tuple[Any, ...]:
        if os.name == "nt":
            return self._windows_fingerprint(path, deadline)
        captured = safe_workspace_path(
            self.root,
            os.path.relpath(path, self.root),
            deadline=deadline,
            limit=_FILE_BYTES,
        )
        if captured.kind != "file" or captured.data is None:
            raise OSError("watcher source changed during capture")
        return hashlib.sha256(captured.data).hexdigest(), captured.metadata[-1]

    def _windows_fingerprint(self, path: str, deadline: float) -> tuple[Any, ...]:
        """短期固定目录和文件句柄；不在两次轮询之间持有禁止重命名的句柄。"""
        from .index_snapshot_windows import NativeFiles

        if self._native is None:
            self._native = NativeFiles()
        api = self._native
        parts = os.path.relpath(path, self.root).split(os.sep)
        with ExitStack() as owned:
            directory = self.root
            for part in [None, *parts[:-1]]:
                if time.monotonic() >= deadline:
                    raise OSError("watcher read deadline exceeded")
                if part is not None:
                    directory = os.path.join(directory, part)
                handle = api.open(directory, True)
                owned.callback(api.close, handle)
            handle = api.open(path, False)
            try:
                identity = api.identity(handle)
                fd = api.reader_fd(handle)
            except BaseException:
                api.close(handle)
                raise
            owned.callback(os.close, fd)
            digest = hashlib.sha256()
            size = 0
            while True:
                if time.monotonic() >= deadline:
                    raise OSError("watcher read deadline exceeded")
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > _FILE_BYTES:
                    raise OSError("watcher source exceeds byte limit")
                digest.update(chunk)
            if api.identity(handle) != identity:
                raise OSError("watcher source changed during capture")
            if time.monotonic() >= deadline:
                raise OSError("watcher read deadline exceeded")
            return digest.hexdigest(), identity
