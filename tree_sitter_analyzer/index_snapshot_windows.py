"""Windows 快照捕获的只读原生句柄；目录和文件身份不依赖 CRT stat。"""

from __future__ import annotations

import ctypes
import os
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


@contextmanager
def pinned_windows_files(
    project_root: str, check: Callable[[], None]
) -> Iterator[tuple[str, list[tuple[str, int, tuple[Any, ...]]], Callable[[], None]]]:
    """固定主库/WAL 与父目录；只提供 fd 和发布前的身份复核函数。"""
    api = NativeFiles()
    root = os.path.realpath(os.path.abspath(project_root))
    cache = os.path.join(root, ".ast-cache")
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
            pin(cache, True)
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
