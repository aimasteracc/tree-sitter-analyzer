"""#1670：经改名导入调用的边（``from m import f as g; g()``）按目标的真实名字查找。

这类 CALLS 边的 ``callee_name`` 是本地名 ``g``，按 ``callee_name = 'f'`` 的索引
查询看不到它们。Synapse 解析时把来源写入 ``metadata.import_alias``
（``local`` / ``name`` / ``line``）；这里经 ``ast_imports`` 找出把 ``f`` 改名导入的
本地名，再按 ``callee_name`` 走索引读取边，只保留来源确认指向 ``f`` 的行——没有
持久化来源的行（旧索引、未解析）不被当作 ``f`` 的调用。

#1705：别的文件经模块属性调用这个本地名（``import pkg.hub as owner;
owner._f()``）时，调用文件既不改名导入也不原样导入 ``_f``，因此按本地名读取
全部文件中的边，而不只是导入了它的文件。
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
#: 以本地名为被调方的 CALLS 边（走 ``idx_edges_callee_name``）。
_ALIAS_EDGES_SQL = (
    "SELECT * FROM edges WHERE kind = 'calls' AND callee_name = ? "
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
    # 只做候选收集：是否真的指向 `callee_name` 由持久化来源逐行确认——同一本地名
    # 可以在别的文件绑定别的函数（各语言插件都有 `_extract_func_standalone`）。
    local_names = sorted({str(local_name) for _file, local_name in imports})
    rows: list[sqlite3.Row] = []
    for local_name in local_names:
        for row in conn.execute(_ALIAS_EDGES_SQL, (local_name,)):
            alias = _row_alias(row)
            if alias is not None and alias.get("name") == callee_name:
                rows.append(row)
    seen = {row["id"] for row in rows}
    for row in _es_alias_rows(conn, callee_name):
        alias = _row_alias(row)
        if (
            row["id"] not in seen
            and alias is not None
            and alias.get("name") == callee_name
        ):
            seen.add(row["id"])
            rows.append(row)
    return rows


#: #1764 / #1768：ES 模块里改名的本地名不一定出现在导入行的 ``alias_of`` 上——默认导入
#: （``import makeSig from './jws'``，默认导出是 ``signer``）与再导出链上的改名
#: （``export { signer as sign } from``）。按调用文件的导入绑定连接调用边，以持久化的
#: ``import_alias`` 来源确认。
_ES_ALIAS_EDGES_SQL = (
    "SELECT e.* FROM ast_imports i JOIN edges e "
    "ON e.kind = 'calls' AND e.callee_name = i.local_name AND e.file_path = i.file_path "
    "WHERE i.language IN ('javascript', 'jsx', 'typescript', 'tsx') "
    "AND i.local_name <> ? AND instr(e.metadata, ?) > 0"
)


#: 全部 ES 改名导入调用边（不带名字过滤），按 ``import_alias.name`` 分桶。
#: RFC-0041：一次统一查询里 callers 会对许多名字各问一次；逐名的 ``instr`` 连接
#: 扫描在 TSA 自身索引上每次约 0.3 s，而它只取决于索引内容。在查询作用域
#: （``query_scope``）内按库文件只分桶一次；作用域外逐次实时计算，行为不变。
_ES_ALIAS_ALL_SQL = (
    "SELECT e.* FROM ast_imports i JOIN edges e "
    "ON e.kind = 'calls' AND e.callee_name = i.local_name AND e.file_path = i.file_path "
    "WHERE i.language IN ('javascript', 'jsx', 'typescript', 'tsx') "
    "AND instr(e.metadata, '\"import_alias\"') > 0"
)


def _es_alias_buckets(conn: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    from ..query_scope import scoped

    def compute() -> dict[str, list[sqlite3.Row]]:
        buckets: dict[str, list[sqlite3.Row]] = {}
        for row in conn.execute(_ES_ALIAS_ALL_SQL):
            alias = _row_alias(row)
            name = alias.get("name") if alias else None
            if isinstance(name, str):
                buckets.setdefault(name, []).append(row)
        return buckets

    databases = tuple(tuple(r) for r in conn.execute("PRAGMA database_list"))
    if any(not db[2] for db in databases):  # in-memory database: no file identity
        return compute()
    return scoped(("es_alias_buckets", databases), compute)


#: 单个名字的同一查询（作用域外的原路径）。
_ES_ALIAS_EDGES_SQL = (
    "SELECT e.* FROM ast_imports i JOIN edges e "
    "ON e.kind = 'calls' AND e.callee_name = i.local_name AND e.file_path = i.file_path "
    "WHERE i.language IN ('javascript', 'jsx', 'typescript', 'tsx') "
    "AND i.local_name <> ? AND instr(e.metadata, ?) > 0"
)


def _es_alias_rows(conn: sqlite3.Connection, callee_name: str) -> list[sqlite3.Row]:
    from ..query_scope import in_scope

    try:
        if not in_scope():
            return conn.execute(
                _ES_ALIAS_EDGES_SQL, (callee_name, f'"name": "{callee_name}"')
            ).fetchall()
        rows = _es_alias_buckets(conn).get(callee_name, [])
    except sqlite3.OperationalError:
        return []
    # 与逐名查询的 ``i.local_name <> ?`` 条件一致：原样导入的同名不算改名。
    return [row for row in rows if row["callee_name"] != callee_name]


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
