"""Windows 快照捕获的只读原生句柄；目录和文件身份不依赖 CRT stat。"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from typing import Any, cast


class _FileInfo(ctypes.Structure):
    _fields_ = [
        ("attributes", ctypes.c_uint32),
        ("created", ctypes.c_uint32 * 2),
        ("accessed", ctypes.c_uint32 * 2),
        ("written", ctypes.c_uint32 * 2),
        ("volume", ctypes.c_uint32),
        ("size_high", ctypes.c_uint32),
        ("size_low", ctypes.c_uint32),
        ("links", ctypes.c_uint32),
        ("index_high", ctypes.c_uint32),
        ("index_low", ctypes.c_uint32),
    ]


class _FileId(ctypes.Structure):
    _fields_ = [("volume", ctypes.c_uint64), ("identifier", ctypes.c_ubyte * 16)]


class NativeFiles:
    """只加载 Kernel32 的读取接口，使用完整文件 ID，拒绝重解析点。"""

    def __init__(self) -> None:
        from ctypes import wintypes

        native = cast(Any, ctypes)
        self.dll = native.WinDLL("kernel32", use_last_error=True)
        self.error = native.WinError
        self.last_error = native.get_last_error
        specifications = {
            "CreateFileW": (
                [
                    wintypes.LPCWSTR,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.c_void_p,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.HANDLE,
                ],
                wintypes.HANDLE,
            ),
            "GetFileInformationByHandle": (
                [wintypes.HANDLE, ctypes.POINTER(_FileInfo)],
                wintypes.BOOL,
            ),
            "GetFileInformationByHandleEx": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                wintypes.BOOL,
            ),
            "GetFileType": ([wintypes.HANDLE], wintypes.DWORD),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (arguments, result) in specifications.items():
            function = getattr(self.dll, name)
            function.argtypes = arguments
            function.restype = result

    def open(self, path: str, directory: bool) -> int:
        # 不共享 DELETE：捕获期间固定目录层级，防止绝对路径经过被替换的父目录。
        handle = self.dll.CreateFileW(
            path,
            0x80 if directory else 0x80000000,
            3,
            None,
            3,
            0x00200000 | 0x02000000,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            raise self.error(self.last_error())
        try:
            info = self._info(handle)
            if info.attributes & 0x400:
                raise ValueError("INDEX_PATH_SYMLINK")
            if (
                bool(info.attributes & 0x10) != directory
                or self.dll.GetFileType(handle) != 1
            ):
                raise ValueError("INDEX_PATH_UNSAFE")
        except BaseException:
            self.close(handle)
            raise
        return int(handle)

    def _info(self, handle: int) -> _FileInfo:
        info = _FileInfo()
        if not self.dll.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise self.error(self.last_error())
        return info

    def identity(self, handle: int) -> tuple[Any, ...]:
        info = self._info(handle)
        identifier = _FileId()
        if not self.dll.GetFileInformationByHandleEx(
            handle, 18, ctypes.byref(identifier), ctypes.sizeof(identifier)
        ):
            raise self.error(self.last_error())
        return (
            int(identifier.volume),
            bytes(identifier.identifier),
            (int(info.size_high) << 32) | int(info.size_low),
            tuple(info.written),
            tuple(info.created),
            int(info.attributes),
        )

    def close(self, handle: int) -> None:
        if not self.dll.CloseHandle(handle):
            raise self.error(self.last_error())

    def reader_fd(self, handle: int) -> int:
        import msvcrt

        # 所有权交给 CRT；此后仅由 os.close 关闭原生句柄。
        return int(
            cast(Any, msvcrt).open_osfhandle(
                handle, os.O_RDONLY | getattr(os, "O_BINARY", 0)
            )
        )


def _read_descriptor(fd: int, size: int) -> bytes:
    """模块级读取 seam，便于故障注入而不修改进程级 ``os``。"""
    return os.read(fd, size)


def _workspace_parts(relative_path: str, limit: int) -> tuple[str, ...]:
    """在打开任何句柄前拒绝绝对、越界、驱动器或空组件路径。"""
    normalized = relative_path.replace("\\", "/")
    parts = tuple(normalized.split("/"))
    if (
        limit < 0
        or not parts
        or normalized.startswith("/")
        or any(part in {"", ".", ".."} or ":" in part for part in parts)
    ):
        raise ValueError("INDEX_PATH_UNSAFE")
    return parts


def _read_bounded(fd: int, limit: int, check: Callable[[], None]) -> bytes:
    data = bytearray()
    while True:
        check()
        chunk = _read_descriptor(fd, min(64 * 1024, limit - len(data) + 1))
        if not chunk:
            return bytes(data)
        data.extend(chunk)
        if len(data) > limit:
            raise OverflowError("INDEX_SOURCE_CAPACITY")


class PinnedWorkspaceReader:
    """一次扫描内共享目录句柄的批量读取器（#1783）。

    ``read_pinned_workspace_file`` 每读一个文件都要重新打开并复核根到父目录的整条
    链：深度为 d 的文件需要 2·(d+2) 次 ``CreateFileW``。批量扫描时同一目录被反复
    打开数百次，在开启实时防护的 Windows 上把 500 个文件的扫描拖到数秒以上。

    这里每个目录只固定一次，句柄在整个扫描期间持有且不共享 DELETE，因此目录不能被
    重命名或删除，路径到目录的绑定在扫描期间保持不变；``verify`` 在扫描结束时再按
    路径重开全部目录并比较卷与 File ID。文件仍逐个在固定句柄上读取，并在读取后
    重开路径、复核完整身份（大小、时间、属性）。调用方必须在 ``verify`` 成功后才
    发布结果；任一失败都使整次扫描失败关闭。``read`` 可被多个线程并发调用。
    """

    def __init__(self, project_root: str, *, deadline: float) -> None:
        self._api = NativeFiles()
        self._root = os.path.realpath(os.path.abspath(project_root))
        self._deadline = deadline
        self._lock = threading.Lock()
        self._directories: dict[tuple[str, ...], tuple[str, int, tuple[Any, ...]]] = {}
        self._closed = False
        self._pin_directory(())

    def _check(self) -> None:
        if time.monotonic() >= self._deadline:
            raise TimeoutError("INDEX_SNAPSHOT_DEADLINE")

    def _pin_directory(self, key: tuple[str, ...]) -> tuple[Any, ...]:
        pinned = self._directories.get(key)
        if pinned is not None:
            return pinned[2]
        self._check()
        path = os.path.join(self._root, *key) if key else self._root
        handle = self._api.open(path, True)
        try:
            identity = self._api.identity(handle)
        except BaseException:
            self._api.close(handle)
            raise
        self._directories[key] = (path, handle, identity)
        return identity

    def _pin_chain(self, directories: tuple[str, ...]) -> list[tuple[Any, ...]]:
        with self._lock:
            if self._closed:
                raise ValueError("INDEX_SOURCE_CHANGED")
            return [
                self._pin_directory(directories[:depth])
                for depth in range(len(directories) + 1)
            ]

    def read(
        self, relative_path: str, *, limit: int
    ) -> tuple[bytes, tuple[bytes, ...]]:
        """读取一个普通文件；缺失时抛出 ``FileNotFoundError``。"""
        parts = _workspace_parts(relative_path, limit)
        self._check()
        chain = self._pin_chain(parts[:-1])
        path = os.path.join(self._root, *parts)
        handle = self._api.open(path, False)
        try:
            fd = self._api.reader_fd(handle)
        except BaseException:
            self._api.close(handle)
            raise
        try:
            expected = self._api.identity(handle)
            data = _read_bounded(fd, limit, self._check)
            self._check()
            try:
                reopened = self._api.open(path, False)
                try:
                    if (
                        self._api.identity(reopened) != expected
                        or self._api.identity(handle) != expected
                    ):
                        raise ValueError("INDEX_SOURCE_CHANGED")
                finally:
                    self._api.close(reopened)
            except OSError as exc:
                raise ValueError("INDEX_SOURCE_CHANGED") from exc
        finally:
            os.close(fd)
        metadata = tuple(repr(item).encode("ascii") for item in [*chain, expected])
        return data, metadata

    def verify(self) -> None:
        """按路径重开每个固定目录；卷或 File ID 漂移即拒绝整次扫描。"""
        with self._lock:
            try:
                for path, handle, expected in self._directories.values():
                    reopened = self._api.open(path, True)
                    try:
                        if (
                            self._api.identity(reopened)[:2] != expected[:2]
                            or self._api.identity(handle)[:2] != expected[:2]
                        ):
                            raise ValueError("INDEX_SOURCE_CHANGED")
                    finally:
                        self._api.close(reopened)
            except OSError as exc:
                raise ValueError("INDEX_SOURCE_CHANGED") from exc

    def close(self) -> None:
        """释放全部目录句柄；即使某个关闭失败也继续释放其余句柄。"""
        with self._lock:
            self._closed = True
            directories = list(self._directories.values())
            self._directories.clear()
        failure: OSError | None = None
        for _path, handle, _expected in directories:
            try:
                self._api.close(handle)
            except OSError as exc:
                failure = failure or exc
        if failure is not None:
            raise failure

    def __enter__(self) -> PinnedWorkspaceReader:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def read_pinned_workspace_file(
    project_root: str,
    relative_path: str,
    *,
    deadline: float,
    limit: int,
) -> tuple[bytes, tuple[bytes, ...]]:
    """用原生句柄固定工作区层级，并在同一 deadline 内读取普通文件。"""
    parts = _workspace_parts(relative_path, limit)

    def check() -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError("INDEX_SNAPSHOT_DEADLINE")

    api = NativeFiles()
    root = os.path.realpath(os.path.abspath(project_root))
    with ExitStack() as owned:
        pinned: list[tuple[str, int, tuple[Any, ...], bool]] = []

        def pin(path: str, directory: bool) -> int | None:
            check()
            handle = api.open(path, directory)
            fd = None
            if directory:
                owned.callback(api.close, handle)
            else:
                try:
                    fd = api.reader_fd(handle)
                except BaseException:
                    api.close(handle)
                    raise
                owned.callback(os.close, fd)
            expected = api.identity(handle)
            pinned.append((path, handle, expected, directory))
            return fd

        pin(root, True)
        current = root
        for component in parts[:-1]:
            current = os.path.join(current, component)
            pin(current, True)
        source_path = os.path.join(current, parts[-1])
        source_fd = pin(source_path, False)
        assert source_fd is not None

        def verify() -> None:
            check()
            try:
                for path, handle, expected, directory in pinned:
                    reopened = api.open(path, directory)
                    try:
                        # 目录只比较卷与 File ID；文件还比较大小、时间与属性。
                        width = 2 if directory else len(expected)
                        if (
                            api.identity(reopened)[:width] != expected[:width]
                            or api.identity(handle)[:width] != expected[:width]
                        ):
                            raise ValueError("INDEX_SOURCE_CHANGED")
                    finally:
                        api.close(reopened)
            except OSError as exc:
                raise ValueError("INDEX_SOURCE_CHANGED") from exc

        data = _read_bounded(source_fd, limit, check)
        verify()
        metadata = tuple(repr(expected).encode("ascii") for _, _, expected, _ in pinned)
        return data, metadata


@contextmanager
def pinned_windows_files(
    project_root: str, check: Callable[[], None]
) -> Iterator[tuple[str, list[tuple[str, int, tuple[Any, ...]]], Callable[[], None]]]:
    """固定主库/WAL 与父目录；只提供 fd 和发布前的身份复核函数。"""
    api = NativeFiles()
    root = os.path.realpath(os.path.abspath(project_root))
    from .cache.generation_routing import resolve_index_path

    database = resolve_index_path(root)
    cache = str(database.parent)
    with ExitStack() as owned:
        pinned: list[tuple[str, int, tuple[Any, ...], bool]] = []

        def pin(path: str, directory: bool) -> tuple[int | None, tuple[Any, ...]]:
            check()
            handle = api.open(path, directory)
            fd = None
            if directory:
                owned.callback(api.close, handle)
            else:
                try:
                    fd = api.reader_fd(handle)
                except BaseException:
                    api.close(handle)
                    raise
                owned.callback(os.close, fd)
            expected = api.identity(handle)
            pinned.append((path, handle, expected, directory))
            return fd, expected

        try:
            pin(root, True)
        except FileNotFoundError:
            raise FileNotFoundError("MISSING_PROJECT_ROOT") from None
        try:
            current_directory = root
            for part in database.parent.relative_to(root).parts:
                current_directory = os.path.join(current_directory, part)
                pin(current_directory, True)
            db_fd, expected = pin(os.path.join(cache, "index.db"), False)
        except FileNotFoundError:
            raise FileNotFoundError("MISSING_INDEX") from None
        assert db_fd is not None
        files = [("index.db", db_fd, expected)]
        try:
            wal_fd, wal_expected = pin(os.path.join(cache, "index.db-wal"), False)
        except FileNotFoundError:
            wal_fd = None
        if wal_fd is not None:
            files.append(("index.db-wal", wal_fd, wal_expected))

        def verify() -> None:
            check()
            try:
                if resolve_index_path(root) != database:
                    raise ValueError("CONCURRENT_WRITER")
                for path, handle, expected, directory in pinned:
                    current = api.open(path, directory)
                    try:
                        # 目录身份不包括 mtime；SQLite 可合法创建 SHM 等非持久数据。
                        width = 2 if directory else len(expected)
                        if (
                            api.identity(current)[:width] != expected[:width]
                            or api.identity(handle)[:width] != expected[:width]
                        ):
                            raise ValueError("CONCURRENT_WRITER")
                    finally:
                        api.close(current)
                absent = ["index.db-journal"]
                if wal_fd is None:
                    absent.append("index.db-wal")
                for name in absent:
                    try:
                        unexpected = api.open(os.path.join(cache, name), False)
                    except FileNotFoundError:
                        continue
                    api.close(unexpected)
                    raise ValueError("CONCURRENT_WRITER")
            except OSError as exc:
                raise ValueError("CONCURRENT_WRITER") from exc

        verify()
        yield root, files, verify
