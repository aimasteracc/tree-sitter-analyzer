#!/usr/bin/env python3
"""Non-mutating filesystem snapshots for the RFC-0022 Linux authority."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, cast

from rfc0022_strace_model import AuthorityError

_READ_SIZE = 1024 * 1024
_STAT_FIELDS = (
    "st_mode",
    "st_uid",
    "st_gid",
    "st_dev",
    "st_ino",
    "st_size",
    "st_nlink",
    "st_atime_ns",
    "st_mtime_ns",
    "st_ctime_ns",
)


def _metadata(details: os.stat_result) -> tuple[int, ...]:
    return tuple(int(getattr(details, field)) for field in _STAT_FIELDS)


def _record(relative: str, details: os.stat_result, kind: str) -> dict[str, Any]:
    return {
        "path": relative,
        "mode": details.st_mode,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "device": details.st_dev,
        "inode": details.st_ino,
        "size": details.st_size,
        "nlink": details.st_nlink,
        "atime_ns": details.st_atime_ns,
        "mtime_ns": details.st_mtime_ns,
        "ctime_ns": details.st_ctime_ns,
        "kind": kind,
    }


def _hash_fd(descriptor: int, expected_size: int) -> str:
    digest = hashlib.sha256()
    remaining = expected_size
    while remaining:
        chunk = os.read(descriptor, min(_READ_SIZE, remaining))
        if not chunk:
            raise AuthorityError("snapshot file ended before its recorded size")
        digest.update(chunk)
        remaining -= len(chunk)
    if os.read(descriptor, 1):
        raise AuthorityError("snapshot file grew beyond its recorded size")
    return digest.hexdigest()


def _linux_platform() -> bool:
    return sys.platform == "linux"


def _noatime_flags(*, directory: bool = False) -> int:
    names = ("O_CLOEXEC", "O_NOATIME", "O_NOFOLLOW", "O_NONBLOCK")
    values = [getattr(os, name, None) for name in names]
    if not _linux_platform() or not all(isinstance(value, int) for value in values):
        raise AuthorityError("Linux O_NOATIME snapshot support is unavailable")
    flags = os.O_RDONLY
    for value in values:
        flags |= cast(int, value)
    if directory:
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if not isinstance(directory_flag, int):
            raise AuthorityError("Linux O_DIRECTORY snapshot support is unavailable")
        flags |= directory_flag
    return flags


def _open_checked(
    path: str | Path,
    expected: os.stat_result,
    *,
    directory: bool,
    dir_fd: int | None = None,
) -> int:
    try:
        descriptor = os.open(path, _noatime_flags(directory=directory), dir_fd=dir_fd)
    except OSError as exc:
        raise AuthorityError(f"unable to open snapshot inode: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise AuthorityError(f"unable to stat opened snapshot inode: {exc}") from exc
    if _metadata(opened) != _metadata(expected):
        os.close(descriptor)
        raise AuthorityError("snapshot entry changed while it was opened")
    return descriptor


def _linux_file_record(
    directory_fd: int | None,
    name: str | Path,
    relative: str,
    expected: os.stat_result,
) -> dict[str, Any]:
    descriptor = _open_checked(name, expected, directory=False, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        digest = _hash_fd(descriptor, before.st_size)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _metadata(before) != _metadata(after):
        raise AuthorityError("snapshot file metadata changed while hashing")
    record = _record(relative, before, "file")
    record["sha256"] = digest
    return record


def _linux_directory_records(
    descriptor: int, relative: PurePosixPath
) -> list[dict[str, Any]]:
    before = os.fstat(descriptor)
    display = "." if relative == PurePosixPath(".") else relative.as_posix()
    records = [_record(display, before, "directory")]
    with os.scandir(descriptor) as iterator:
        names = sorted(entry.name for entry in iterator)
    for name in names:
        child_relative = PurePosixPath(name) if display == "." else relative / name
        child_display = child_relative.as_posix()
        details = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISLNK(details.st_mode):
            records.append(_record(child_display, details, "symlink"))
        elif stat.S_ISREG(details.st_mode):
            records.append(_linux_file_record(descriptor, name, child_display, details))
        elif stat.S_ISDIR(details.st_mode):
            child_fd = _open_checked(name, details, directory=True, dir_fd=descriptor)
            try:
                records.extend(_linux_directory_records(child_fd, child_relative))
            finally:
                os.close(child_fd)
        else:
            records.append(_record(child_display, details, "other"))
    after = os.fstat(descriptor)
    if _metadata(before) != _metadata(after):
        raise AuthorityError("snapshot directory metadata changed while traversing")
    return records


def _linux_snapshot(root: Path) -> list[dict[str, Any]]:
    details = root.lstat()
    if stat.S_ISREG(details.st_mode):
        records = [_linux_file_record(None, root, ".", details)]
    elif not stat.S_ISDIR(details.st_mode):
        kind = "symlink" if stat.S_ISLNK(details.st_mode) else "other"
        records = [_record(".", details, kind)]
    else:
        descriptor = _open_checked(root, details, directory=True)
        try:
            records = _linux_directory_records(descriptor, PurePosixPath("."))
        finally:
            os.close(descriptor)
    if _metadata(details) != _metadata(root.lstat()):
        raise AuthorityError("snapshot root pathname changed during traversal")
    return records


def _portable_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_READ_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_snapshot(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    paths = sorted([root, *root.rglob("*")], key=lambda item: os.fspath(item))
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode):
            record = _record(relative, details, "symlink")
        elif stat.S_ISREG(details.st_mode):
            digest = _portable_hash(path)
            details = path.lstat()
            record = _record(relative, details, "file")
            record["sha256"] = digest
        elif stat.S_ISDIR(details.st_mode):
            record = _record(relative, details, "directory")
        else:
            record = _record(relative, details, "other")
        records.append(record)
    return records


def snapshot_root(root: Path, *, require_noatime: bool = False) -> dict[str, Any]:
    if sys.platform == "linux" and hasattr(os, "O_NOATIME"):
        records = _linux_snapshot(root)
    elif require_noatime:
        raise AuthorityError("Linux O_NOATIME snapshot support is unavailable")
    else:
        records = _portable_snapshot(root)
    return {"root": os.fspath(root), "records": records}
