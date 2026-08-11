"""Pinned database capability helpers for authoritative index snapshots."""

from __future__ import annotations

import errno
import os
import sqlite3
import stat


def exact_call_graph_marker(conn: sqlite3.Connection) -> bool:
    """Require id=1/built=1 and absence of the incomplete sentinel."""
    try:
        rows = conn.execute(
            "SELECT id, built FROM ast_call_graph_state WHERE id IN (1, 2) ORDER BY id"
        ).fetchall()
    except sqlite3.OperationalError:
        return False
    return bool(
        len(rows) == 1
        and type(rows[0][0]) is int
        and type(rows[0][1]) is int
        and rows[0][0] == 1
        and rows[0][1] == 1
    )


def _open_pinned_path(
    path: str,
    flags: int,
    *,
    dir_fd: int | None = None,
    directory: bool,
) -> int:
    """Open one no-follow path component and bind it to its lstat identity."""
    expected = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
    if stat.S_ISLNK(expected.st_mode):
        raise ValueError("INDEX_PATH_SYMLINK")
    if not (
        stat.S_ISDIR(expected.st_mode) if directory else stat.S_ISREG(expected.st_mode)
    ):
        raise ValueError("INDEX_PATH_UNSAFE")
    try:
        fd = os.open(
            path,
            flags | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=dir_fd,
        )
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ValueError("INDEX_PATH_SYMLINK") from exc
        raise
    try:
        opened = os.fstat(fd)
    except BaseException:
        os.close(fd)
        raise
    valid_kind = (
        stat.S_ISDIR(opened.st_mode) if directory else stat.S_ISREG(opened.st_mode)
    )
    if not valid_kind or (opened.st_dev, opened.st_ino) != (
        expected.st_dev,
        expected.st_ino,
    ):
        os.close(fd)
        raise ValueError("INDEX_PATH_UNSAFE")
    return fd


def open_bound_database(project_root: str) -> tuple[str, int, int, int]:
    logical = os.path.abspath(project_root)
    if not os.path.isdir(logical):
        raise FileNotFoundError("MISSING_PROJECT_ROOT")
    root = os.path.realpath(logical)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        root_fd = _open_pinned_path(root, directory_flags, directory=True)
    except FileNotFoundError:
        raise FileNotFoundError("MISSING_PROJECT_ROOT") from None
    try:
        cache_fd = _open_pinned_path(
            ".ast-cache", directory_flags, dir_fd=root_fd, directory=True
        )
    except FileNotFoundError:
        os.close(root_fd)
        raise FileNotFoundError("MISSING_INDEX") from None
    except Exception:
        os.close(root_fd)
        raise
    try:
        db_fd = _open_pinned_path(
            "index.db",
            os.O_RDONLY | os.O_NONBLOCK,
            dir_fd=cache_fd,
            directory=False,
        )
    except FileNotFoundError:
        os.close(cache_fd)
        os.close(root_fd)
        raise FileNotFoundError("MISSING_INDEX") from None
    except Exception:
        os.close(cache_fd)
        os.close(root_fd)
        raise
    return root, root_fd, cache_fd, db_fd


def path_matches_pinned_database(cache_fd: int, db_fd: int) -> bool:
    """Return whether the cache path still names the securely pinned inode."""
    try:
        path_info = os.stat("index.db", dir_fd=cache_fd, follow_symlinks=False)
        pinned_info = os.fstat(db_fd)
    except OSError:
        return False
    return (path_info.st_dev, path_info.st_ino) == (
        pinned_info.st_dev,
        pinned_info.st_ino,
    )


def reject_sidecars(cache_fd: int) -> None:
    # A quiescent WAL database commonly retains a non-empty shared-memory
    # index. Only durable write payloads (WAL/journal) prove it is not safe to
    # open the pinned main database immutably.
    for name in ("index.db-wal", "index.db-journal"):
        try:
            info = os.stat(name, dir_fd=cache_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size:
            raise ValueError("CONCURRENT_WRITER")
    try:
        shm = os.stat("index.db-shm", dir_fd=cache_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(shm.st_mode):
        raise ValueError("CONCURRENT_WRITER")
