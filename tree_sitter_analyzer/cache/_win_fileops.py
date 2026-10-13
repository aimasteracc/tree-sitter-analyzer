"""Windows 活动选择器的原生替换与读取：POSIX 语义改名 + 允许删除共享的读者。

背景 (rfcs/evidence/0032-feasibility E4, 2026-10-13)：``os.replace`` 在任一读者持有
``active.json`` 时报 ``PermissionError [WinError 5]``，读者打开也会失败。只有发布者使用
``FileRenameInfoEx`` (REPLACE_IF_EXISTS | POSIX_SEMANTICS) 且读者以 ``FILE_SHARE_DELETE``
打开时，才能做到零发布失败、零读取失败、零撕裂读取。两侧必须同时修改。

本模块只保证原子可见性（读者要么见旧字节、要么见新字节），不宣称 Windows 掉电持久性。
POSIX 不调用本模块：``rename(2)`` 在读者持有旧 inode 时本身即原子替换。
"""

from __future__ import annotations

import ctypes
import functools
import os
from pathlib import Path
from typing import Any, cast

WRITER_BUSY = "INDEX_WRITER_BUSY"

_FILE_RENAME_INFO_EX = 22
_RENAME_FLAGS = 0x1 | 0x2  # REPLACE_IF_EXISTS | POSIX_SEMANTICS
_DELETE = 0x00010000
_SYNCHRONIZE = 0x00100000
_GENERIC_READ = 0x80000000
_SHARE_ALL = 0x1 | 0x2 | 0x4  # READ | WRITE | DELETE
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x80
_INVALID_HANDLE = ctypes.c_void_p(-1).value
# 不支持 FileRenameInfoEx（旧系统 / 非 NTFS）或仍被不共享删除的读者占用时的错误码：
# INVALID_FUNCTION / ACCESS_DENIED / SHARING_VIOLATION / LOCK_VIOLATION /
# NOT_SUPPORTED / INVALID_PARAMETER。
_BUSY_ERRORS = frozenset({1, 5, 32, 33, 50, 87})


class IndexWriterBusy(RuntimeError):
    """无法以 POSIX 语义原子替换选择器；失败关闭，活动选择器保持不变，可稍后重试。"""

    retryable = True

    def __init__(self, winerror: int) -> None:
        super().__init__(WRITER_BUSY)
        self.winerror = winerror


def native_failure(code: int, path: Path) -> Exception:
    """把原生错误码映射为异常：忙/不支持归入类型化忙错误，其余保留 OSError 语义。"""
    if code in _BUSY_ERRORS:
        return IndexWriterBusy(code)
    return OSError(None, f"WinError {code}", str(path), code)


@functools.lru_cache(maxsize=1)
def _kernel32() -> Any:  # pragma: no cover - 仅 Windows 加载 Kernel32
    from ctypes import wintypes

    dll = cast(Any, ctypes).WinDLL("kernel32", use_last_error=True)
    dll.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    dll.CreateFileW.restype = wintypes.HANDLE
    dll.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dll.SetFileInformationByHandle.restype = wintypes.BOOL
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    return dll


def _last_error() -> int:  # pragma: no cover - 仅 Windows 读取原生错误码
    return int(cast(Any, ctypes).get_last_error())


def _create(path: Path, access: int) -> int:  # pragma: no cover - 仅 Windows
    handle = _kernel32().CreateFileW(
        str(path),
        access,
        _SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle is None or handle == _INVALID_HANDLE:
        code = _last_error()
        raise OSError(None, cast(Any, ctypes).FormatError(code), str(path), code)
    return int(handle)


def _set_file_information(
    handle: int, info_class: int, buffer: Any, size: int
) -> bool:  # pragma: no cover - 原生调用 seam，测试以此注入不支持错误
    return bool(
        _kernel32().SetFileInformationByHandle(handle, info_class, buffer, size)
    )


def open_shared_reader(path: Path) -> int:  # pragma: no cover - 仅 Windows 读者
    """以读/写/删除共享只读打开，返回 CRT 描述符；读者不再阻塞发布者替换名称。"""
    import msvcrt

    handle = _create(path, _GENERIC_READ)
    try:
        # 所有权交给 CRT；此后仅由 os.close 关闭原生句柄。
        return int(
            cast(Any, msvcrt).open_osfhandle(
                handle, os.O_RDONLY | getattr(os, "O_BINARY", 0)
            )
        )
    except BaseException:
        _kernel32().CloseHandle(handle)
        raise


def replace_file(source: Path, target: Path) -> None:  # pragma: no cover - 仅 Windows
    """以 POSIX 语义把已关闭的临时文件改名覆盖目标；不支持时失败关闭，不退回 os.replace。"""
    encoded = os.path.abspath(target).encode("utf-16-le")

    class _RenameInfo(ctypes.Structure):
        _fields_ = [
            ("flags", ctypes.c_uint32),
            ("root", ctypes.c_void_p),
            ("length", ctypes.c_uint32),
            ("name", ctypes.c_ubyte * (len(encoded) + 2)),
        ]

    info = _RenameInfo()
    info.flags = _RENAME_FLAGS
    info.length = len(encoded)
    ctypes.memmove(
        ctypes.addressof(info) + _RenameInfo.name.offset, encoded, len(encoded)
    )
    handle = _create(source, _DELETE | _SYNCHRONIZE)
    try:
        if not _set_file_information(
            handle, _FILE_RENAME_INFO_EX, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise native_failure(_last_error(), target)
    finally:
        _kernel32().CloseHandle(handle)
