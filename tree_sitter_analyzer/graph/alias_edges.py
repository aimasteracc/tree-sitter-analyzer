"""#1670：经改名导入调用的边（``from m import f as g; g()``）按目标的真实名字查找。

这类 CALLS 边的 ``callee_name`` 是本地名 ``g``，按 ``callee_name = 'f'`` 的索引
查询看不到它们。Synapse 解析时把来源写入 ``metadata.import_alias``
（``local`` / ``name`` / ``line``）；这里经 ``ast_imports`` 找出把 ``f`` 改名导入的
文件与本地名，再按 ``(callee_name, file_path)`` 走索引读取边，只保留来源确认
指向 ``f`` 的行——没有持久化来源的行（旧索引、未解析）不被当作 ``f`` 的调用。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

#: ``ast_imports`` 中把 ``name`` 改名导入的行（星号导入与模块别名除外）。
_ALIAS_IMPORTS_SQL = (
    "SELECT DISTINCT file_path, local_name FROM ast_imports "
    "WHERE alias_of = ? AND local_name <> ? AND is_star = 0"
)
#: 原样导入本地名 ``local`` 的文件（改名后的再导出被别的模块再次导入，一跳）。
_PLAIN_REIMPORTS_SQL = (
    "SELECT DISTINCT file_path FROM ast_imports "
    "WHERE local_name = ? AND (alias_of = '' OR alias_of IS NULL) AND is_star = 0"
)
#: 某文件中以本地名为被调方的 CALLS 边（走 ``idx_edges_callee_name``）。
_ALIAS_EDGES_SQL = (
    "SELECT * FROM edges WHERE kind = 'calls' AND callee_name = ? AND file_path = ? "
    "ORDER BY source_node_id, target_node_id, line"
)


def alias_call_rows(conn: sqlite3.Connection, callee_name: str) -> list[sqlite3.Row]:
    """调用 ``callee_name`` 时用的是改名导入的本地名、且已解析到它的 CALLS 边。"""
    if not callee_name or "." in callee_name:
        return []
    try:
        imports = conn.execute(
            _ALIAS_IMPORTS_SQL, (callee_name, callee_name)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    pairs = {(str(file_path), str(local_name)) for file_path, local_name in imports}
    for local_name in {local for _file, local in pairs}:
        # 只做候选收集：是否真的指向 `callee_name` 由持久化来源逐行确认。
        pairs.update(
            (str(row[0]), local_name)
            for row in conn.execute(_PLAIN_REIMPORTS_SQL, (local_name,))
        )
    rows: list[sqlite3.Row] = []
    for file_path, local_name in sorted(pairs):
        for row in conn.execute(_ALIAS_EDGES_SQL, (local_name, file_path)):
            alias = _row_alias(row)
            if alias is not None and alias.get("name") == callee_name:
                rows.append(row)
    return rows


def import_alias_of(edge: Any) -> str | None:
    """边经改名导入解析时返回调用点使用的本地名，否则 None。"""
    alias = getattr(edge, "metadata", {}).get("import_alias")
    if isinstance(alias, dict) and alias.get("local"):
        return str(alias["local"])
    return None


def _row_alias(row: sqlite3.Row) -> dict[str, Any] | None:
    try:
        raw = row["metadata"]
    except (IndexError, KeyError):
        return None
    if not raw or "import_alias" not in raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    alias = parsed.get("import_alias") if isinstance(parsed, dict) else None
    return alias if isinstance(alias, dict) else None


__all__ = ["alias_call_rows", "import_alias_of"]
