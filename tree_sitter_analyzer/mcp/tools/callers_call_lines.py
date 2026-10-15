"""#1622：非调用引用扫描只能跳过“已有调用边”的 ``name(`` 调用位置。

#1598 的扫描把处于调用位置的 ``name(`` 视为已被调用边覆盖而跳过。但调用边若
没有被计为调用方（#1622 之前的模块作用域调用点就是如此），这个假设会让真实
调用点从两边同时漏掉，答案变成假“不存在”。因此只有当同一文件同一行确有以该
名字为被调方的 CALLS 边时才跳过；否则该位置计为可能的引用。
"""

from __future__ import annotations

import sqlite3
from typing import Any


def call_edge_lines(cache: Any, bare: str) -> dict[str, frozenset[int]] | None:
    """以 ``bare`` 为被调方的 CALLS 边所在行，按文件分组；读取失败为 None。"""
    try:
        rows = cache.get_conn().execute(
            "SELECT file_path, line FROM edges WHERE kind = 'calls' AND callee_name = ?",
            (bare,),
        )
        grouped: dict[str, set[int]] = {}
        for file_path, line in rows:
            grouped.setdefault(str(file_path), set()).add(int(line or 0))
    except (sqlite3.Error, AttributeError, TypeError, ValueError):
        return None
    return {path: frozenset(lines) for path, lines in grouped.items()}
