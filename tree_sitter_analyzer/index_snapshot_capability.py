"""Pinned database capability helpers for authoritative index snapshots."""

from __future__ import annotations

import errno
import os
import sqlite3
import stat
import time

from .cache.callgraph_state import exact_call_graph_marker as _exact_marker


def require_memory_temp_store(conn: sqlite3.Connection) -> None:
    """Keep read-existing sorters in memory and verify SQLite accepted it."""
    try:
        conn.execute("PRAGMA temp_store=MEMORY")
        row = conn.execute("PRAGMA temp_store").fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError("INDEX_TEMP_STORE_MEMORY_REQUIRED") from exc
    if row is None or int(row[0]) != 2:
        raise ValueError("INDEX_TEMP_STORE_MEMORY_REQUIRED")


_CALL_GRAPH_MARKER_DEADLINE_SECONDS = 5.0


def physical_storage_identity(
    conn: sqlite3.Connection,
) -> tuple[int, int, int, int, int, int]:
    """Return every physical storage field published by snapshot status."""
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    auto_vacuum = int(conn.execute("PRAGMA auto_vacuum").fetchone()[0])
    return (
        page_size * page_count,
        page_count,
        page_size,
        free_pages,
        free_pages * page_size,
        auto_vacuum,
    )


def strict_call_graph_marker(
    conn: sqlite3.Connection, *, deadline: float | None = None
) -> bool:
    """Check the shared exact marker predicate."""
    if deadline is None:
        deadline = time.monotonic() + _CALL_GRAPH_MARKER_DEADLINE_SECONDS
    return _exact_marker(conn, deadline=deadline)


def exact_call_graph_marker(
    conn: sqlite3.Connection, *, deadline: float | None = None
) -> bool:
    """Require id=1/built=1 and absence of duplicate/sentinel rows."""
    return strict_call_graph_marker(conn, deadline=deadline)


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


def hierarchy_matches_pinned_database(
    canonical_root: str, root_fd: int, cache_fd: int, db_fd: int
) -> bool:
    """Reopen the published pathname and compare every pinned hierarchy inode."""
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    current_root: int | None = None
    current_cache: int | None = None
    try:
        current_root = os.open(canonical_root, directory_flags)
        if _fd_identity(current_root) != _fd_identity(root_fd):
            return False
        current_cache = os.open(".ast-cache", directory_flags, dir_fd=current_root)
        if _fd_identity(current_cache) != _fd_identity(cache_fd):
            return False
        return path_matches_pinned_database(current_cache, db_fd)
    except OSError:
        return False
    finally:
        if current_cache is not None:
            os.close(current_cache)
        if current_root is not None:
            os.close(current_root)


def _fd_identity(fd: int) -> tuple[int, int]:
    info = os.fstat(fd)
    return int(info.st_dev), int(info.st_ino)


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
