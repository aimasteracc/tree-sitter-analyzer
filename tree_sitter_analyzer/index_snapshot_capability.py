"""Pinned database capability helpers for authoritative index snapshots."""

from __future__ import annotations

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
    return [(int(row[0]), int(row[1])) for row in rows] == [(1, 1)]


def open_bound_database(project_root: str) -> tuple[str, int, int, int]:
    logical = os.path.abspath(project_root)
    if not os.path.isdir(logical):
        raise FileNotFoundError("MISSING_PROJECT_ROOT")
    root = os.path.realpath(logical)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    root_fd = os.open(root, flags)
    try:
        cache_fd = os.open(".ast-cache", flags | os.O_NOFOLLOW, dir_fd=root_fd)
    except FileNotFoundError:
        os.close(root_fd)
        raise FileNotFoundError("MISSING_INDEX") from None
    except Exception:
        os.close(root_fd)
        raise
    try:
        db_fd = os.open(
            "index.db",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=cache_fd,
        )
        if not stat.S_ISREG(os.fstat(db_fd).st_mode):
            os.close(db_fd)
            raise ValueError("INDEX_PATH_UNSAFE")
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
