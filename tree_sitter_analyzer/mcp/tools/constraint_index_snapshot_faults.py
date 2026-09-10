"""Filesystem identity and cleanup guards for portable constraint indexes."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    if os.name == "posix":
        return (
            int(info.st_dev),
            int(info.st_ino),
            int(info.st_size),
            int(info.st_mtime_ns),
            int(info.st_ctime_ns),
        )
    # Windows: st_ctime_ns is deliberately excluded — it is the creation
    # time, and the handle/path stat sources disagree on it since CPython
    # 3.12 (the CONCURRENT_WRITER misreport on Windows 3.12/3.13 CI, dogfood
    # round 2026-08-15). st_ino is kept: both sources report the same file
    # ID, so same-size pathname swaps are still detected.
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        0,
    )


def path_identity(path: Path, *, directory: bool) -> tuple[int, int, int, int, int]:
    """Authenticate a non-symlink directory or regular file identity."""
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode):
        raise ValueError("INDEX_PATH_SYMLINK")
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_kind(info.st_mode):
        raise ValueError("INDEX_PATH_UNSAFE")
    return stat_identity(info)


def close_optional_fd(fd: int | None) -> None:
    if fd is not None:
        os.close(fd)
