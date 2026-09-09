"""AST 缓存完整重建期间共用的只读状态信号（#578）。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from tree_sitter_analyzer.cache.generation_routing import resolve_index_path


def is_index_rebuilding(project_root: str | None) -> bool:
    """尽力读取重建标记；缺失或读取失败时返回 False，不阻断导航。

    只读打开防止存在检查后文件消失时创建空库；保留两秒锁等待上限。
    """
    if not project_root:
        return False
    db_path = str(resolve_index_path(project_root))
    if not os.path.exists(db_path):
        return False
    try:
        from tree_sitter_analyzer.cache.build_state import build_in_progress

        conn = sqlite3.connect(
            Path(db_path).absolute().as_uri() + "?mode=ro", uri=True, timeout=2
        )
        try:
            return bool(build_in_progress(conn))
        finally:
            conn.close()
    except Exception:
        return False


def rebuild_in_progress_next_step() -> str:
    return (
        "Full rebuild in progress — cached graph rows are transiently empty or "
        "partial. Do NOT start another index; retry this read shortly."
    )
