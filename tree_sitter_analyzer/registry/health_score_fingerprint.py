"""健康评分的源码指纹，隔离平台变更时间与有界内容读取。"""

from __future__ import annotations

import ctypes
import hashlib
import os
import stat
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

_IS_WINDOWS = os.name == "nt"


class _FileBasicInfo(ctypes.Structure):
    """Windows FILE_BASIC_INFO 的四个时间及属性字段。"""

    _fields_ = [
        ("creation", ctypes.c_longlong),
        ("access", ctypes.c_longlong),
        ("write", ctypes.c_longlong),
        ("change", ctypes.c_longlong),
        ("attributes", ctypes.c_uint32),
    ]


@lru_cache(maxsize=1)
def _windows_file_info() -> Any:
    """按需绑定原生句柄查询，非 Windows 不加载动态库。"""
    function = (
        cast(Any, ctypes)
        .WinDLL("kernel32", use_last_error=True)
        .GetFileInformationByHandleEx
    )
    function.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    function.restype = ctypes.c_int
    return function


def _change_time(fd: int, metadata: os.stat_result) -> int:
    """使用变更时间；Windows 的 stat ctime 可能是创建时间。"""
    if not _IS_WINDOWS:
        return metadata.st_ctime_ns
    import msvcrt

    info = _FileBasicInfo()
    if not _windows_file_info()(
        cast(Any, msvcrt).get_osfhandle(fd), 0, ctypes.byref(info), ctypes.sizeof(info)
    ):
        raise OSError("Windows file change time unavailable")
    return int(info.change)


@dataclass(frozen=True)
class _Fingerprint:
    """绑定完整源码内容及读取时的文件元数据。"""

    mtime_ns: int
    size_bytes: int
    content_hash: str
    change_identity: tuple[int, int, int]

    @classmethod
    def from_path(cls, path: str) -> _Fingerprint | None:
        try:
            with os.fdopen(
                os.open(
                    path,
                    os.O_RDONLY
                    | getattr(os, "O_NONBLOCK", 0)
                    | getattr(os, "O_BINARY", 0),
                ),
                "rb",
            ) as stream:
                before = os.fstat(stream.fileno())
                change_before = _change_time(stream.fileno(), before)
                if not stat.S_ISREG(before.st_mode):
                    return None
                content = stream.read(64 * 1024 * 1024 + 1)
                after = os.fstat(stream.fileno())
                change_after = _change_time(stream.fileno(), after)
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if (
                change_before != change_after
                or len(content) > 64 * 1024 * 1024
                or any(
                    getattr(before, field) != getattr(after, field) for field in fields
                )
            ):
                return None
        except OSError:
            return None
        return cls(
            after.st_mtime_ns,
            after.st_size,
            hashlib.sha256(content).hexdigest(),
            (after.st_dev, after.st_ino, change_after),
        )
