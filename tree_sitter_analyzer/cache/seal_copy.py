"""封存时私有库仍被另一句柄打开：改为封存一份字节副本（#1902）。

``PRAGMA journal_mode=DELETE`` 需要主库排他锁，而 SQLite 在进程内按 inode 计数
SHARED 锁：同一文件上只要还有任何句柄（WAL 模式下空闲也持有 SHARED），切换就以
``database is locked`` 失败，无论等多久。CI 上（#1821、#1831、#1848、#1902）这样的
句柄在本进程、只有主线程，而 Python 层看不到对应的 ``sqlite3.Connection`` 或游标
（``holders []``）；等满 10 s 后 ``SealBusy``，刷新不发布，监视器与测试都超时。

私有构建库只属于本次构建：没有任何读者或写者应当打开它。``wal_checkpoint(TRUNCATE)``
成功即说明 WAL 已全部并入主库、没有读者持有 WAL 快照，此时主库的字节就是完整一致的
数据库。这里把这些字节复制到同目录的新文件，只在新文件上（唯一的句柄）切回回滚日志，
再原子替换私有库路径。残留句柄继续指向已被替换的旧 inode，不再影响发布的文件。

复制前后源文件的身份（inode、大小、修改时间）必须一致，否则视为仍有写入，抛出
:class:`SealBusy`，私有版本照常回收。Windows 不能替换或删除仍被打开的文件，也没有
这种按 inode 共享的锁计数，因此只在 POSIX 上使用。
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path

from .generation_seal import SealBusy

_CHUNK = 8 * 1024 * 1024
_SIDECARS = ("-wal", "-shm", "-journal")
SEALING_SUFFIX = ".sealing"


def reseal_supported() -> bool:
    """只有 POSIX 能原子替换仍被其他句柄打开的文件。"""
    return os.name == "posix"


def _identity(path: Path) -> tuple[int, int, int, int]:
    info = os.lstat(path)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _wal_size(database: Path) -> int:
    try:
        return os.lstat(f"{database}-wal").st_size
    except FileNotFoundError:
        return 0


def _copy_bytes(source: Path, destination: Path) -> None:
    with open(source, "rb") as reader, open(destination, "xb") as writer:
        while chunk := reader.read(_CHUNK):
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())


def _leave_wal_alone(database: Path) -> None:
    """新文件只有这一个句柄：切回回滚日志不会遇到其他持有者。"""
    connection = sqlite3.connect(database)
    try:
        journal = str(connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0])
    finally:
        connection.close()
    if journal != "delete" or any(
        os.path.lexists(f"{database}{suffix}") for suffix in _SIDECARS
    ):
        raise RuntimeError("INDEX_GENERATION_SIDECAR_PRESENT")


def reseal_by_copy(database: Path, cause: BaseException | None = None) -> None:
    """以字节副本替换 ``database``；副本已是回滚日志模式，不带任何旁路文件。

    ``cause`` 是让调用方走到这里的 :class:`SealBusy`，失败时接在新异常上。
    """
    before = _identity(database)
    if _wal_size(database):
        # 检查点之后 WAL 又有了帧：仍有写入者，不能以主库字节代表整个库。
        raise SealBusy() from cause
    sealing = database.with_name(database.name + SEALING_SUFFIX)
    try:
        _copy_bytes(database, sealing)
        if _identity(database) != before or _wal_size(database):
            raise SealBusy() from cause
        _leave_wal_alone(sealing)
        # 旧 inode 的 WAL（检查点后为空）与 SHM 仍属于残留句柄；新文件不能继承它们，
        # 否则读者会按旁路文件把回滚日志库当作 WAL 库打开。
        for suffix in ("-wal", "-shm"):
            with contextlib.suppress(FileNotFoundError):
                os.unlink(f"{database}{suffix}")
        os.replace(sealing, database)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(sealing)
        raise
