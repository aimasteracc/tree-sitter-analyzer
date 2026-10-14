"""跨进程版本钉：读者或构建者持有期间，该版本不得被回收（RFC-0032 slice 6，#1554）。

每个持有者在 ``pins/<版本 ID>/`` 下独占创建一个钉文件并加非阻塞独占锁；进程被杀时
操作系统释放锁，残留钉文件即为过期。回收者先放 ``retiring`` 墓碑再探测钉，持有者
先建钉再查墓碑；顺序相反，故“钉已建立”与“开始回收”至多一方成立。
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
import uuid
from pathlib import Path

if sys.platform == "win32":  # pragma: no cover - Windows 字节区间锁
    import msvcrt
else:  # pragma: no cover - POSIX flock（覆盖率在各自平台统计）
    import fcntl

TOMBSTONE = "retiring"
GENERATION_ID = re.compile(r"[0-9a-f]{32}")


def pin_directory(storage: Path, generation_id: str) -> Path:
    """钉目录只由校验过的版本 ID 构造，拒绝任意路径片段。"""
    if not GENERATION_ID.fullmatch(generation_id):
        raise ValueError("INDEX_GENERATION_ID_INVALID")
    return storage / "pins" / generation_id


def _lock(descriptor: int) -> bool:
    try:
        if sys.platform == "win32":  # pragma: no cover - Windows
            # 锁 EOF 之后的字节：Windows 字节锁会阻断他人读取，空文件内容须仍可读。
            os.lseek(descriptor, 1 << 30, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:  # pragma: no cover - POSIX
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


class GenerationPin:
    """一个持有中的钉；``release`` 幂等，对象被回收时同样释放。"""

    def __init__(self, path: Path, descriptor: int) -> None:
        self.path = path
        self._descriptor: int | None = descriptor

    def release(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            os.close(descriptor)
            # 目录可能已被回收者清理，或探测者暂持句柄；残留文件无锁即过期。
            with contextlib.suppress(OSError):
                self.path.unlink()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.release()


def pin_generation(storage: Path, generation_id: str) -> GenerationPin | None:
    """为版本建立钉；版本已在回收中则返回 ``None``，调用方须重新解析选择器。"""
    directory = pin_directory(storage, generation_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}.pin"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    if not _lock(descriptor):
        os.close(descriptor)
        raise OSError("INDEX_GENERATION_PIN_LOCK_FAILED")
    pin = GenerationPin(path, descriptor)
    if os.path.lexists(directory / TOMBSTONE):
        pin.release()
        return None
    return pin


def pin_database(database: Path) -> GenerationPin | None:
    """钉住 ``<存储>/generations/<ID>/index.db``；其他路径不是托管版本，不建钉。"""
    generation = database.parent
    if database.name == "index.db" and generation.parent.name == "generations":
        if GENERATION_ID.fullmatch(generation.name):
            return pin_generation(generation.parent.parent, generation.name)
    return None


def has_live_pin(directory: Path) -> bool:
    """能加锁即持有者已退出并删除残留；任一加锁失败即活钉；其他 OSError 上抛。"""
    try:
        paths = [Path(e.path) for e in os.scandir(directory) if e.name.endswith(".pin")]
    except FileNotFoundError:
        return False
    for path in paths:
        try:
            descriptor = os.open(path, os.O_RDWR)
        except FileNotFoundError:
            continue
        try:
            if not _lock(descriptor):
                return True
        finally:
            os.close(descriptor)
        path.unlink(missing_ok=True)
    return False
