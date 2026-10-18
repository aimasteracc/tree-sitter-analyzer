"""文件的“元数据变更时间”（ctime 的 POSIX 语义），供按 stat 证据复用的缓存使用。

POSIX 的 ``st_ctime`` 在任何写入或元数据修改时都会前进，且无法由普通调用设回。
Windows 上 Python（至 3.13）通过路径 ``stat``/``lstat`` 返回的 ``st_ctime`` 是
**创建时间**：内容改写后再把 mtime 设回原值（``tar -x``、``cp -p``、``os.utime``），
大小、mtime、ctime 全都不变。实测（#1673，Python 3.13.16）路径 ``stat`` 的 ctime
不变，只有句柄 ``fstat`` 反映改写。

Windows 上因此以仅读属性的句柄（不读内容，不触发按内容的实时扫描）调用
``GetFileInformationByHandleEx(FileBasicInfo)`` 取 NTFS 的 ``ChangeTime``；任何失败
返回 ``None``，调用方必须视为“无法证明未变”而重新读取。
"""

from __future__ import annotations

import os
import sys
from typing import Any

IS_WINDOWS = sys.platform == "win32"

_FILE_READ_ATTRIBUTES = 0x80
_SHARE_ALL = 0x1 | 0x2 | 0x4
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_BASIC_INFO = 0
#: FILETIME 起点 1601-01-01 与 Unix 纪元之差（100 ns 单位）。
_EPOCH_DELTA_100NS = 116444736000000000

_native: Any = None


def _bind() -> Any:  # pragma: no cover - 仅 Windows
    import ctypes
    from ctypes import wintypes

    class FileBasicInfo(ctypes.Structure):
        _fields_ = [
            ("CreationTime", ctypes.c_int64),
            ("LastAccessTime", ctypes.c_int64),
            ("LastWriteTime", ctypes.c_int64),
            ("ChangeTime", ctypes.c_int64),
            ("FileAttributes", wintypes.DWORD),
        ]

    dll = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
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
    dll.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dll.GetFileInformationByHandleEx.restype = wintypes.BOOL
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    return dll, FileBasicInfo, invalid, ctypes


def _windows_change_time_ns(path: str) -> int | None:  # pragma: no cover - Windows
    global _native
    if _native is None:
        _native = _bind()
    dll, info_type, invalid, ctypes = _native
    handle = dll.CreateFileW(
        path,
        _FILE_READ_ATTRIBUTES,
        _SHARE_ALL,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle is None or handle == invalid:
        return None
    try:
        info = info_type()
        if not dll.GetFileInformationByHandleEx(
            handle, _FILE_BASIC_INFO, ctypes.byref(info), ctypes.sizeof(info)
        ):
            return None
        return (int(info.ChangeTime) - _EPOCH_DELTA_100NS) * 100
    finally:
        dll.CloseHandle(handle)


def change_time_ns(path: str, info: os.stat_result) -> int | None:
    """``path`` 的元数据变更时间（纳秒）；无法取得时为 ``None``。

    POSIX 直接使用调用方 ``lstat`` 的 ``st_ctime_ns``；Windows 读取 NTFS
    ``ChangeTime``。
    """
    if not IS_WINDOWS:
        return int(info.st_ctime_ns)
    try:
        return _windows_change_time_ns(path)
    except OSError:
        return None
