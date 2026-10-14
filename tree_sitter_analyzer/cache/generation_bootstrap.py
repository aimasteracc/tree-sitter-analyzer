"""默认定位符首次发布前的读写边界：读取不建库，首次写入采纳旧库。

RFC-0032 slice 1（#1554，rfcs/evidence/0032-feasibility E1，2026-10-13）：
首次发布前的默认写入口不能再原地写旧 ``.ast-cache/index.db``。写入一律先
在版本存储中引导私有版本，再经选择器 CAS 发布；只读调用既不引导版本，也不
迁移或创建旧库。
"""

from __future__ import annotations

import os
import sqlite3
import stat
import uuid
from pathlib import Path


def unindexed_database_uri() -> str:
    """尚无任何索引时，读者使用进程内共享的空库，不在项目内落盘。"""
    return f"file:tsa-unindexed-{uuid.uuid4().hex}?mode=memory&cache=shared"


def open_unindexed_anchor(uri: str) -> sqlite3.Connection:
    """内存共享库在最后一个连接关闭时消失，缓存生命周期内须持有锚连接。"""
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


def adopt_legacy_database(logical: Path, destination: Path) -> bool:
    """把首次发布前遗留的旧库整库复制进新版本；旧文件本身只读打开、保持不变。

    采纳而非重建：单文件写入、失效等局部操作若从空库开始，发布后读者会丢失
    旧库中的其余文件。复制用 SQLite 在线备份取得一致快照；旧库只可能被旧版本
    进程原地写入，混合版本并发写不在 RFC-0032 范围内，发布 CAS 仍是唯一围栏。
    """
    try:
        info = os.lstat(logical)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("INDEX_GENERATION_PATH_UNSAFE")
    source = sqlite3.connect(logical.as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return True
