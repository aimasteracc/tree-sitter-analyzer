"""Pinned database capability helpers for authoritative index snapshots."""

from __future__ import annotations

import errno
import hashlib
import os
import sqlite3
import stat
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from typing import Any, BinaryIO

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
_WINDOWS_WAL_SUPPORTED = os.name == "nt"
_WAL_FD_COPY_SUPPORTED = _WINDOWS_WAL_SUPPORTED or (
    os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
)


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
    if not valid_kind:
        os.close(fd)
        raise ValueError("INDEX_PATH_UNSAFE")
    if os.name == "posix" and (opened.st_dev, opened.st_ino) != (
        expected.st_dev,
        expected.st_ino,
    ):
        # Windows (3.12+): os.fstat and os.lstat disagree on st_ino for the
        # same file, so the handle can never match the path expectation.
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
    if os.name == "posix":
        return (path_info.st_dev, path_info.st_ino) == (
            pinned_info.st_dev,
            pinned_info.st_ino,
        )
    # Windows: os.stat(dir_fd=) and os.fstat disagree on st_ino since
    # CPython 3.12 (path side carries the real file ID, handle side does
    # not), and mtime precision is not guaranteed to match either — which
    # made this check always fail and every portable snapshot report
    # CONCURRENT_WRITER on Windows 3.12/3.13 CI. size still detects a
    # replaced database (the failure mode this guard exists for).
    return path_info.st_size == pinned_info.st_size


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


@contextmanager
def private_wal_database(
    project_root: str,
    *,
    deadline: float,
    byte_limit: int,
    check_deadline: Callable[[float], None],
) -> Iterator[tuple[str, int | None]]:
    """只用只读 fd 捕获稳定的主库与 WAL；SQLite 只能打开返回的私有路径。

    不复制 SHM，不获取源 SQLite 连接。两平台均要求句柄身份绑定、完整字节
    复核和前后身份一致；缺少能力时拒绝，不能退化成路径猜测。
    """
    if os.name == "nt" and _WINDOWS_WAL_SUPPORTED and _WAL_FD_COPY_SUPPORTED:
        from .index_snapshot_windows import pinned_windows_files

        with pinned_windows_files(project_root, lambda: check_deadline(deadline)) as (
            root,
            files,
            verify_paths,
        ):
            with _copy_pinned_wal_files(
                root,
                files,
                verify_paths,
                deadline=deadline,
                byte_limit=byte_limit,
                check_deadline=check_deadline,
            ) as copied:
                yield copied
        return

    if (
        os.name != "posix"
        or not hasattr(os, "O_NOFOLLOW")
        or not _WAL_FD_COPY_SUPPORTED
    ):
        raise ValueError("WAL_PRIVATE_SNAPSHOT_UNSUPPORTED")

    def identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    with ExitStack() as owned:
        root, root_fd, cache_fd, db_fd = open_bound_database(project_root)
        for fd in (root_fd, cache_fd, db_fd):
            owned.callback(os.close, fd)
        files = [("index.db", db_fd, identity(os.fstat(db_fd)))]
        try:
            wal_stat = os.stat("index.db-wal", dir_fd=cache_fd, follow_symlinks=False)
        except FileNotFoundError:
            wal_stat = None
        if wal_stat is not None:
            try:
                fd = _open_pinned_path(
                    "index.db-wal",
                    os.O_RDONLY | os.O_NONBLOCK,
                    dir_fd=cache_fd,
                    directory=False,
                )
            except FileNotFoundError as exc:
                raise ValueError("CONCURRENT_WRITER") from exc
            owned.callback(os.close, fd)
            expected = identity(wal_stat)
            if identity(os.fstat(fd)) != expected:
                raise ValueError("CONCURRENT_WRITER")
            files.append(("index.db-wal", fd, expected))

        def verify_paths() -> None:
            check_deadline(deadline)
            try:
                for name, fd, expected in files:
                    current = os.stat(name, dir_fd=cache_fd, follow_symlinks=False)
                    if (
                        identity(current) != expected
                        or identity(os.fstat(fd)) != expected
                    ):
                        raise ValueError("CONCURRENT_WRITER")
                if wal_stat is None:
                    try:
                        os.stat("index.db-wal", dir_fd=cache_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        raise ValueError("CONCURRENT_WRITER")
                try:
                    os.stat("index.db-journal", dir_fd=cache_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("CONCURRENT_WRITER")
                if not hierarchy_matches_pinned_database(
                    root, root_fd, cache_fd, db_fd
                ):
                    raise ValueError("CONCURRENT_WRITER")
            except OSError as exc:
                raise ValueError("CONCURRENT_WRITER") from exc

        with _copy_pinned_wal_files(
            root,
            files,
            verify_paths,
            deadline=deadline,
            byte_limit=byte_limit,
            check_deadline=check_deadline,
        ) as copied:
            yield copied


@contextmanager
def _copy_pinned_wal_files(
    root: str,
    files: list[tuple[str, int, tuple[Any, ...]]],
    verify_paths: Callable[[], None],
    *,
    deadline: float,
    byte_limit: int,
    check_deadline: Callable[[float], None],
) -> Iterator[tuple[str, int | None]]:
    """两平台共享完整字节复制、WAL 验证、预算和发布后复核。"""
    from .frozen_git_index import safe_external_temp_parent
    from .source_oracle import SourceOracleError

    if sum(expected[2] for _, _, expected in files) > byte_limit:
        raise RuntimeError("INDEX_BACKUP_BUDGET")
    wal_size = next(
        (expected[2] for name, _, expected in files if name == "index.db-wal"), None
    )

    def stream_file(fd: int, size: int, destination: BinaryIO | None = None) -> bytes:
        os.lseek(fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        remaining = size
        while remaining:
            check_deadline(deadline)
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                raise ValueError("CONCURRENT_WRITER")
            digest.update(chunk)
            if destination is not None:
                view = memoryview(chunk)
                while view:
                    check_deadline(deadline)
                    written = destination.write(view)
                    if not isinstance(written, int) or not 0 < written <= len(view):
                        raise OSError("INDEX_STAGE_WRITE_FAILED")
                    view = view[written:]
            remaining -= len(chunk)
        check_deadline(deadline)
        if os.read(fd, 1):
            raise ValueError("CONCURRENT_WRITER")
        return digest.digest()

    verify_paths()
    try:
        temp_parent = safe_external_temp_parent(root)
    except SourceOracleError as exc:
        raise ValueError("INDEX_TEMP_OUTSIDE_PROJECT_REQUIRED") from exc
    with tempfile.TemporaryDirectory(
        prefix="tsa-wal-index-", dir=temp_parent
    ) as private:
        private = os.path.realpath(private)
        try:
            inside_project = os.path.commonpath((root, private)) == root
        except ValueError:
            # 两个路径均已绝对化；Windows 不同盘符的临时目录必在项目外。
            inside_project = False
        if inside_project:
            raise ValueError("INDEX_TEMP_OUTSIDE_PROJECT_REQUIRED")
        hashes = []
        for name, fd, expected in files:
            with open(os.path.join(private, name), "xb", buffering=0) as stream:
                hashes.append(stream_file(fd, expected[2], stream))
        verify_paths()
        wal_frames = None
        if wal_size is not None:
            wal_frames = 0
            if wal_size:
                with open(os.path.join(private, "index.db-wal"), "rb") as wal:
                    header = wal.read(32)
                page_size = int.from_bytes(header[8:12], "big")
                if (
                    len(header) != 32
                    or int.from_bytes(header[:4], "big") not in (0x377F0682, 0x377F0683)
                    or int.from_bytes(header[4:8], "big") != 3007000
                    or not 512 <= page_size <= 65536
                    or page_size & (page_size - 1)
                    or (wal_size - 32) % (24 + page_size)
                ):
                    raise ValueError("CONCURRENT_WRITER")
                wal_frames = (wal_size - 32) // (24 + page_size)
        yield os.path.join(private, "index.db"), wal_frames
        # 跨主库/WAL 的完整复核发生在私有 SQLite 读取之后、发布能力之前。
        for (_, fd, expected), captured in zip(files, hashes, strict=True):
            if stream_file(fd, expected[2]) != captured:
                raise ValueError("CONCURRENT_WRITER")
        verify_paths()


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
