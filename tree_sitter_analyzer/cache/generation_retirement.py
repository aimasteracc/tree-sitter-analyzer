"""有界回收未被引用的索引版本（RFC-0032 slice 6，#1554 所有者决定：按数量与年龄）。

在成功发布之后、发布租约之内运行，活动选择器期间不变。永不回收活动或被钉住的版本；
身份校验（32 位十六进制 ID、真实目录而非链接/重解析点、主库为普通文件）不通过的
目录一律跳过。已密封（主库只读）的历史版本最多保留 ``RETAIN_COUNT`` 个且不超过
``RETAIN_AGE_S``，给已解析选择器、尚未建钉的读者留余量；未密封目录是被杀构建者的
孤儿（rfcs/evidence/0032-feasibility E3），无钉即回收。单次受 ``BUDGET_S`` 限制。
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import time
from pathlib import Path

from ..read_only_files import clear_read_only_tree, mark_read_only
from .generation_pins import GENERATION_ID, TOMBSTONE, has_live_pin, pin_directory

logger = logging.getLogger(__name__)

RETAIN_COUNT = 2
RETAIN_AGE_S = 24 * 60 * 60
BUDGET_S = 1.0


def _plain(info: os.stat_result, kind: int) -> bool:
    return stat.S_IFMT(info.st_mode) == kind and not (
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def _verified(directory: Path) -> tuple[bool, float] | None:
    """返回 (已密封, 修改时间)；链接、重解析点和陌生名字都不是版本。"""
    if not GENERATION_ID.fullmatch(directory.name):
        return None
    try:
        info = os.lstat(directory)
    except OSError:
        return None
    if not _plain(info, stat.S_IFDIR):
        return None
    try:
        database = os.lstat(directory / "index.db")
    except FileNotFoundError:
        # 构建者在建目录与建主库之间被杀：未密封孤儿。
        return False, info.st_mtime
    except OSError:
        return None
    if not _plain(database, stat.S_IFREG):
        return None
    return not database.st_mode & stat.S_IWUSR, database.st_mtime


def _remove(storage: Path, directory: Path, sealed: bool) -> bool:
    """墓碑→探测钉→删除；任一步失败都撤回墓碑并保留版本，不留下可写主库。"""
    pins = pin_directory(storage, directory.name)
    pins.mkdir(parents=True, exist_ok=True)
    tombstone = pins / TOMBSTONE
    tombstone.touch(exist_ok=True)
    if has_live_pin(pins):
        tombstone.unlink(missing_ok=True)
        return False
    database = directory / "index.db"
    try:
        clear_read_only_tree(directory)
        database.unlink(missing_ok=True)
    except OSError:
        # Windows 上仍被打开的主库不可删除；恢复只读位后留待下次。
        if sealed and database.exists():
            mark_read_only(database)
        tombstone.unlink(missing_ok=True)
        return False
    shutil.rmtree(directory, ignore_errors=True)
    shutil.rmtree(pins, ignore_errors=True)
    return not directory.exists()


def retire_generations(
    storage: Path, active_id: str, *, now: float | None = None
) -> list[str]:
    """回收活动版本之外不再需要的版本，返回本次实际删除的版本 ID。"""
    started, now = time.monotonic(), time.time() if now is None else now
    try:
        directories = [Path(e.path) for e in os.scandir(storage / "generations")]
    except FileNotFoundError:
        return []
    found = {
        directory: verdict
        for directory in directories
        if directory.name != active_id and (verdict := _verified(directory))
    }
    newest_sealed = sorted(
        (d for d, (sealed, _m) in found.items() if sealed),
        key=lambda d: found[d][1],
        reverse=True,
    )[:RETAIN_COUNT]
    kept = {d for d in newest_sealed if now - found[d][1] <= RETAIN_AGE_S}
    removed = []
    for directory, (sealed, _modified) in found.items():
        if directory in kept or time.monotonic() - started > BUDGET_S:
            continue
        try:
            if _remove(storage, directory, sealed):
                removed.append(directory.name)
        except OSError:
            logger.warning("generation retirement skipped %s", directory, exc_info=True)
    return removed
