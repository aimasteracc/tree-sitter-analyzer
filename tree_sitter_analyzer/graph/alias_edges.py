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
        local_names = _alias_local_names(conn, callee_name)
    except sqlite3.OperationalError:
        return []
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


#: 全部改名导入行 ``(alias_of, local_name)``（星号导入除外），供查询作用域内分桶。
_ALIAS_IMPORTS_ALL_SQL = (
    "SELECT DISTINCT alias_of, local_name FROM ast_imports "
    "WHERE alias_of IS NOT NULL AND alias_of <> local_name AND is_star = 0"
)


def _alias_local_names(conn: sqlite3.Connection, callee_name: str) -> list[str]:
    """把 ``callee_name`` 改名导入的本地名（有序、去重）。

    只做候选收集：是否真的指向 ``callee_name`` 由持久化来源逐行确认——同一本地名
    可以在别的文件绑定别的函数（各语言插件都有 ``_extract_func_standalone``）。

    RFC-0041 跨名批量：``alias_of = ?`` 没有可用索引（按 ``is_star`` 扫描全表，TSA
    自身约 5 ms / 名）。查询作用域内全部改名导入行按 ``alias_of`` 只分桶一次，各名
    字查桶；与逐名查询同一集合（``alias_of = 名 AND local_name <> 名``）。
    """
    from ..query_scope import in_scope

    if not in_scope():
        imports = conn.execute(_ALIAS_IMPORTS_SQL, (callee_name, callee_name))
        return sorted({str(local_name) for _file, local_name in imports})
    return _alias_import_buckets(conn).get(callee_name, [])


def _alias_import_buckets(conn: sqlite3.Connection) -> dict[str, list[str]]:
    from ..query_scope import scoped

    def compute() -> dict[str, list[str]]:
        buckets: dict[str, set[str]] = {}
        for alias_of, local_name in conn.execute(_ALIAS_IMPORTS_ALL_SQL):
            buckets.setdefault(str(alias_of), set()).add(str(local_name))
        return {name: sorted(locals_) for name, locals_ in buckets.items()}

    databases = _database_identity(conn)
    if databases is None:  # in-memory database: no file identity
        return compute()
    return scoped(("alias_import_buckets", databases), compute)


def _database_identity(conn: sqlite3.Connection) -> tuple[Any, ...] | None:
    """连接所附加的库文件（作用域记忆的键）；含内存库时为 None。"""
    databases = tuple(tuple(r) for r in conn.execute("PRAGMA database_list"))
    if any(not db[2] for db in databases):
        return None
    return databases


#: #1764 / #1768：ES 模块里改名的本地名不一定出现在导入行的 ``alias_of`` 上——默认导入
#: （``import makeSig from './jws'``，默认导出是 ``signer``）与再导出链上的改名
#: （``export { signer as sign } from``）。按调用文件的导入绑定连接调用边，以持久化的
#: ``import_alias`` 来源确认。
#:
#: 连接顺序（RFC-0041 跨名批量）：SQLite 的默认计划按 ``kind`` 扫描全部调用边、逐行
#: 测 ``metadata``；``CROSS JOIN`` 改由 ES 导入行驱动、按 ``idx_edges_callee_name``
#: 只读同名的边。哪种更省取决于索引内容——TSA 自身 24.6 万条调用边、40 条 ES 导入：
#: 默认 0.42 s、CROSS 0.01 s；hono 3.9 万条调用边、2,117 条 ES 导入（同名候选 10.9 万）：
#: 默认 0.07 s、CROSS 0.60 s。:func:`_es_join` 按两侧要读的边数选择。两种写法都以
#: ``ORDER BY e.id`` 给出默认计划本来的顺序（按 ``kind`` 索引、行号递增），结果与顺序
#: 都不变。
_ES_FROM = {
    "default": (
        "FROM ast_imports i JOIN edges e "
        "ON e.kind = 'calls' AND e.callee_name = i.local_name "
        "AND e.file_path = i.file_path "
    ),
    "cross": (
        "FROM ast_imports i CROSS JOIN edges e "
        "ON e.callee_name = i.local_name AND e.kind = 'calls' "
        "AND e.file_path = i.file_path "
    ),
}
_ES_WHERE = "WHERE i.language IN ('javascript', 'jsx', 'typescript', 'tsx') "
#: 单个名字（作用域外的逐次路径）。
_ES_ONE_FILTER = "AND i.local_name <> ? AND instr(e.metadata, ?) > 0 ORDER BY e.id"
#: 全部 ES 改名导入调用边（不带名字过滤），在查询作用域内按 ``import_alias.name``
#: 分桶一次；结果只取决于索引内容。
_ES_ALL_FILTER = "AND instr(e.metadata, '\"import_alias\"') > 0 ORDER BY e.id"
#: CROSS 计划要读的同名候选边数（只走 ``idx_edges_callee_name`` 覆盖索引计数）。
_ES_FANOUT_SQL = (
    "SELECT COUNT(*) FROM ast_imports i CROSS JOIN edges e "
    "ON e.callee_name = i.local_name AND e.kind = 'calls' " + _ES_WHERE
)
#: 默认计划要读的边数。
_CALL_EDGES_SQL = "SELECT COUNT(*) FROM edges WHERE kind = 'calls'"


def _es_join(conn: sqlite3.Connection) -> str:
    """``"cross"``：同名候选边少于全部调用边时由 ES 导入行驱动；否则 ``"default"``。

    两个计数都只读索引（hono 上合计约 8 ms）。选择只影响速度、不影响结果（两种写法
    返回同样的行与顺序），因此在进程内按两张表的最大 rowid（O(1) 读取）记住：认证读
    每次落在不同的快照副本上，按库路径记忆永远不会命中；表被改写时 rowid 随之变化。
    即使不同的库恰好同键，代价也只是一次不够快的连接顺序。
    """
    key = tuple(conn.execute(_JOIN_KEY_SQL).fetchone())
    known = _JOIN_MEMO.get(key)
    if known is not None:
        return known
    fanout = conn.execute(_ES_FANOUT_SQL).fetchone()[0]
    calls = conn.execute(_CALL_EDGES_SQL).fetchone()[0]
    choice = "cross" if int(fanout) < int(calls) else "default"
    if len(_JOIN_MEMO) >= _JOIN_MEMO_MAX:
        _JOIN_MEMO.pop(next(iter(_JOIN_MEMO)))
    _JOIN_MEMO[key] = choice
    return choice


#: ``_es_join`` 的记忆键：两张表的最大 rowid。
_JOIN_KEY_SQL = (
    "SELECT (SELECT COALESCE(MAX(rowid), 0) FROM edges), "
    "(SELECT COALESCE(MAX(rowid), 0) FROM ast_imports)"
)
#: ``_es_join`` 的进程内记忆：记忆键 -> 选择。
_JOIN_MEMO: dict[tuple[Any, ...], str] = {}
_JOIN_MEMO_MAX = 32


def _es_sql(conn: sqlite3.Connection, tail: str) -> str:
    return "SELECT e.* " + _ES_FROM[_es_join(conn)] + _ES_WHERE + tail


def _es_alias_buckets(conn: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    from ..query_scope import scoped

    def compute() -> dict[str, list[sqlite3.Row]]:
        buckets: dict[str, list[sqlite3.Row]] = {}
        for row in conn.execute(_es_sql(conn, _ES_ALL_FILTER)):
            alias = _row_alias(row)
            name = alias.get("name") if alias else None
            if isinstance(name, str):
                buckets.setdefault(name, []).append(row)
        return buckets

    databases = _database_identity(conn)
    if databases is None:  # in-memory database: no file identity
        return compute()
    return scoped(("es_alias_buckets", databases), compute)


def _es_alias_rows(conn: sqlite3.Connection, callee_name: str) -> list[sqlite3.Row]:
    from ..query_scope import in_scope

    try:
        # 作用域内从第一个名字起就分桶（一次连接查询服务查询中的全部名字）。
        if not in_scope():
            return conn.execute(
                _es_sql(conn, _ES_ONE_FILTER),
                (callee_name, f'"name": "{callee_name}"'),
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
