"""#1677：把调用继承方法的 ``self.m()`` / ``cls.m()`` 边解析到 MRO 中最近的定义。

Synapse 只在调用方的外围类里找 ``m``；``m`` 只定义在（可能跨文件的）基类上时，
边停在 ``unknown``，``nav callers`` 列不出它。第二遍解析之后，``extends`` 边已经
指向项目里的基类，这里按 ``class_mro.Hierarchy`` 走 MRO：MRO 完全已知时写入
``project`` 与基类方法的符号；MRO 未知（第三方基类）时保持 ``unknown``——读取端
只把同名候选记为可能目标。子类覆写仍由调用图记为可能目标（#1648）。
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from ..class_mro import ClassKey, Hierarchy, load_hierarchy

logger = logging.getLogger(__name__)

#: 仍未解析、接收者是调用方自身实例 / 类的调用边。
_PENDING_SQL = (
    "SELECT id, file_path, caller_name, caller_line, callee_name FROM edges "
    "WHERE kind = 'calls' AND language = 'python' AND callee_resolution = 'unknown' "
    "AND callee_full IN ('self.' || callee_name, 'cls.' || callee_name)"
)
_SYMBOL_SQL = (
    "SELECT id FROM ast_symbol_rows WHERE file_path = ? AND name = ? AND line = ? "
    "AND kind IN ('function', 'method') LIMIT 1"
)
_UPDATE_SQL = (
    "UPDATE edges SET callee_resolution = 'project', callee_resolved_file = ?, "
    "callee_symbol_id = ? WHERE id = ?"
)


def resolve_inherited_self_calls(conn: sqlite3.Connection) -> int:
    """解析能在完全已知的 MRO 中找到最近定义的继承调用；返回更新的边数。"""
    try:
        pending = conn.execute(_PENDING_SQL).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("inherited self-call select failed: %s", exc)
        return 0
    if not pending:
        return 0
    hierarchy = load_hierarchy(conn)
    owners = _method_owners(hierarchy)
    updates: list[tuple[Any, ...]] = []
    for edge_id, file_path, caller_name, caller_line, callee_name in pending:
        owner = owners.get((str(file_path), str(caller_name), int(caller_line or 0)))
        if owner is None:
            continue
        target = _certain_target(conn, hierarchy, owner, str(callee_name))
        if target is not None:
            updates.append((target[0], target[1], edge_id))
    if updates:
        try:
            conn.executemany(_UPDATE_SQL, updates)
        except sqlite3.OperationalError as exc:
            logger.debug("inherited self-call update failed: %s", exc)
            return 0
    return len(updates)


def _method_owners(hierarchy: Hierarchy) -> dict[tuple[str, str, int], ClassKey]:
    """``(文件, 方法名, 定义行)`` -> 外围类。"""
    owners: dict[tuple[str, str, int], ClassKey] = {}
    for klass, methods in hierarchy.methods.items():
        for method, line in methods.items():
            owners[(klass.file, method, line)] = klass
    return owners


def _certain_target(
    conn: sqlite3.Connection, hierarchy: Hierarchy, owner: ClassKey, name: str
) -> tuple[str, int] | None:
    """MRO 完全已知且找到继承定义时返回 ``(定义文件, 符号 id)``。"""
    if name in hierarchy.methods.get(owner, {}):
        return None  # 外围类自己定义了它：由 Synapse 的 self 规则负责。
    found, known = hierarchy.nearest(owner, name)
    if found is None or not known:
        return None
    line = hierarchy.methods[found][name]
    row = conn.execute(_SYMBOL_SQL, (found.file, name, line)).fetchone()
    if row is None:
        return None
    return found.file, int(row[0])


__all__ = ["resolve_inherited_self_calls"]
