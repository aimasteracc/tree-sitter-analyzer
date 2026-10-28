"""RFC-0039：按文件分组的两级 Merkle 认证根（manifest v3）。

``index_fingerprint``（manifest v2）把每张查询可见表的每一行哈希成一个扁平摘要，
一次 1 文件刷新也要重读全部行（本仓库约 51 万行、9–24 s）。这里把同样的行按
``(表, file_path)`` 分组：

* **叶**：一组行按 ``file_path`` 再按每个查询可见列 ``COLLATE BINARY`` 排序，
  用与 ``index_fingerprint`` 相同的 ``_typed`` / ``_frame`` 编码求 SHA-256；
  没有 ``file_path`` 列的表整表为一组；
* **根**：项目根、各表（名字、建表语句、列）与按分组键字节序排列的
  ``(分组键, 叶)`` 依次成帧后求 SHA-256，记为 ``merkle:<hex>``。

FTS5 虚表及其影子表不进入根（RFC-0039 owner decision 2026-10-20）：它们是
``ast_symbol_rows`` 的投影，由已在根内的 ``ast_symbol_projection_state`` 逐文件
``projection_digest`` 与读者的 ``symbol_projection_is_exact`` 核验绑定。

叶存放在控制表 ``ast_certification_leaves``（不进入根，与 ``ast_writer_state`` 同类），
供写者在后续刷新中只重算被改动的组（RFC-0039 step 3–4）。叶只是派生数据：读者
总是独立重算根，从不信任存放的叶。
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

#: manifest 中认证根的前缀；值形如 ``merkle:<64 位十六进制>``。
ROOT_PREFIX = "merkle:"
#: 写入认证根的 manifest 版本（v2 为扁平 ``index_fingerprint``）。
MANIFEST_VERSION = 3
#: 叶的控制表；不进入认证根。
LEAF_TABLE = "ast_certification_leaves"
LEAF_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {LEAF_TABLE} ("
    "tbl TEXT NOT NULL, grp BLOB NOT NULL, leaf BLOB NOT NULL, "
    "PRIMARY KEY (tbl, grp)) WITHOUT ROWID"
)
#: 分组列。
GROUP_COLUMN = "file_path"
#: 整表一组时的分组键。
WHOLE_TABLE_GROUP = b""
_LEAF_DOMAIN = b"tsa-index-leaf-v1\0"
_ROOT_DOMAIN = b"tsa-index-merkle-v1\0"
#: FTS5 影子表后缀（虚表 ``X`` 的 ``X_data`` 等）。
_FTS5_SHADOW_SUFFIXES = ("_data", "_idx", "_docsize", "_config", "_content")
#: Sentinel "no previous group value" (never equal to a SQLite value).
_NO_VALUE = object()
#: ``_frame``'s label header for a row: 4-byte label length, then the label.
_ROW_FRAME = len(b"row").to_bytes(4, "big") + b"row"


@dataclass(frozen=True)
class RootedTable:
    """进入认证根的一张表：名字、建表语句、查询可见列，以及是否按 ``file_path`` 分组。"""

    name: str
    sql: str
    columns: tuple[str, ...]
    grouped: bool


@dataclass
class CertificationTree:
    """各表与其叶（分组键字节 -> 32 字节叶摘要）。"""

    tables: tuple[RootedTable, ...]
    leaves: dict[str, dict[bytes, bytes]] = field(default_factory=dict)


def group_key(value: object) -> bytes:
    """分组键：``file_path`` 值的类型化编码（区分 NULL、整数与文本）。"""
    from .index_snapshot_schema import _typed

    return _typed((value,))


def excluded_tables(conn: sqlite3.Connection) -> set[str]:
    """不进入根的表：控制表、叶表、FTS5 虚表与其影子表。"""
    from .index_snapshot_schema import _CONTROL_TABLES

    excluded = set(_CONTROL_TABLES) | {LEAF_TABLE}
    virtual = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND sql LIKE 'CREATE VIRTUAL TABLE%'"
        )
    ]
    excluded.update(virtual)
    for name in virtual:
        excluded.update(name + suffix for suffix in _FTS5_SHADOW_SUFFIXES)
    return excluded


def rooted_tables(conn: sqlite3.Connection, deadline: float) -> tuple[RootedTable, ...]:
    """按名字排序的根内表清单；与 ``index_fingerprint`` 相同的结构预检与列规则。"""
    from .index_snapshot_schema import (
        _deadline_ordered_rows,
        _preflight_schema_inventory,
        _query_visible_columns,
    )

    _preflight_schema_inventory(conn, deadline)
    excluded = excluded_tables(conn)
    tables = []
    for row in _deadline_ordered_rows(
        conn,
        "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name",
        deadline,
    ):
        name, sql = str(row[0]), str(row[1] or "")
        if name in excluded:
            continue
        columns = _query_visible_columns(conn, name, deadline)
        tables.append(RootedTable(name, sql, columns, GROUP_COLUMN in columns))
    return tuple(tables)


def _ordered_select(table: RootedTable, where: str = "") -> str:
    from .index_snapshot_schema import _quote_identifier

    selected = ", ".join(_quote_identifier(c) for c in table.columns)
    order = [GROUP_COLUMN] if table.grouped else []
    order += [c for c in table.columns if not (table.grouped and c == GROUP_COLUMN)]
    order_by = ", ".join(f"{_quote_identifier(c)} COLLATE BINARY" for c in order)
    return f"SELECT {selected} FROM {_quote_identifier(table.name)}{where} ORDER BY {order_by}"


class _Budget:
    """与 ``index_fingerprint`` 相同的行数与字节预算（跨表累计）。"""

    def __init__(self) -> None:
        self.rows = 0
        self.bytes = 0

    def charge(self, rows: int, size: int) -> None:
        from .index_snapshot_schema import (
            _FINGERPRINT_BYTE_BUDGET,
            _FINGERPRINT_ROW_BUDGET,
        )

        self.rows += rows
        self.bytes += size
        if self.rows > _FINGERPRINT_ROW_BUDGET or self.bytes > _FINGERPRINT_BYTE_BUDGET:
            raise RuntimeError("INDEX_FINGERPRINT_BUDGET")


def _hash_table(
    conn: sqlite3.Connection,
    table: RootedTable,
    deadline: float,
    budget: _Budget,
) -> dict[bytes, bytes]:
    """整表一次有序扫描，返回该表的全部叶。"""
    from .index_snapshot_schema import (
        _check_deadline,
        _deadline_ordered_rows,
        _preflight_table_rows,
        _quote_identifier,
        _typed,
    )

    quoted = tuple(_quote_identifier(c) for c in table.columns)
    rows, size = _preflight_table_rows(conn, table.name, quoted, deadline)
    budget.charge(rows, size)
    index = table.columns.index(GROUP_COLUMN) if table.grouped else -1
    leaves: dict[bytes, bytes] = {}
    current: bytes | None = None
    digest = None
    # Rows arrive ordered by ``file_path``: re-encode the group key only when the
    # value (or its type: 1 and "1" are different groups) changes. Floats are
    # always re-encoded (0.0 == -0.0 but their encodings differ).
    last_value: object = _NO_VALUE
    last_key = WHOLE_TABLE_GROUP
    for row in _deadline_ordered_rows(conn, _ordered_select(table), deadline):
        _check_deadline(deadline)
        if table.grouped:
            value = row[index]
            kind = type(value)
            if kind is float or kind is not type(last_value) or value != last_value:
                last_value, last_key = value, group_key(value)
            key = last_key
        else:
            key = WHOLE_TABLE_GROUP
        if key != current:
            if digest is not None and current is not None:
                leaves[current] = digest.digest()
            current, digest = key, hashlib.sha256(_LEAF_DOMAIN)
        assert digest is not None
        # One update with the bytes ``_frame(digest, b"row", ...)`` would feed.
        encoded = _typed(tuple(row))
        digest.update(_ROW_FRAME + len(encoded).to_bytes(8, "big") + encoded)
    if digest is not None and current is not None:
        leaves[current] = digest.digest()
    return leaves


def full_tree(conn: sqlite3.Connection, *, deadline: float) -> CertificationTree:
    """从数据库内容完整计算认证树（每张根内表一次有序扫描）。"""
    tables = rooted_tables(conn, deadline)
    budget = _Budget()
    tree = CertificationTree(tables)
    for table in tables:
        tree.leaves[table.name] = _hash_table(conn, table, deadline, budget)
    return tree


def fold_root(root: str, tree: CertificationTree, deadline: float) -> str:
    """把各表与叶折叠成 ``merkle:<hex>`` 根。"""
    from .index_snapshot_schema import _check_deadline, _frame, _typed

    digest = hashlib.sha256(_ROOT_DOMAIN)
    _frame(digest, b"root", root.encode("utf-8", "surrogatepass"))
    for table in tree.tables:
        _check_deadline(deadline)
        _frame(digest, b"table", table.name.encode("utf-8", "surrogatepass"))
        _frame(digest, b"schema", table.sql.encode("utf-8", "surrogatepass"))
        _frame(digest, b"columns", _typed(table.columns))
        leaves = tree.leaves.get(table.name, {})
        for key in sorted(leaves):
            _frame(digest, b"group", key)
            _frame(digest, b"leaf", leaves[key])
    return ROOT_PREFIX + digest.hexdigest()


def certification_root(conn: sqlite3.Connection, root: str, *, deadline: float) -> str:
    """数据库内容的完整认证根（读者与校验者使用）。"""
    return fold_root(root, full_tree(conn, deadline=deadline), deadline)


def store_leaves(conn: sqlite3.Connection, tree: CertificationTree) -> None:
    """用 ``tree`` 的叶替换叶表内容（与盖章同一事务）。"""
    conn.execute(LEAF_TABLE_SQL)
    conn.execute(f"DELETE FROM {LEAF_TABLE}")  # nosec B608 — 模块常量
    conn.executemany(
        f"INSERT INTO {LEAF_TABLE} (tbl, grp, leaf) VALUES (?, ?, ?)",  # nosec B608
        _leaf_rows(tree.leaves),
    )


def _leaf_rows(
    leaves: Mapping[str, Mapping[bytes, bytes]],
) -> Iterable[tuple[str, bytes, bytes]]:
    for table in sorted(leaves):
        for key in sorted(leaves[table]):
            yield table, key, leaves[table][key]


__all__ = [
    "GROUP_COLUMN",
    "LEAF_TABLE",
    "MANIFEST_VERSION",
    "ROOT_PREFIX",
    "CertificationTree",
    "RootedTable",
    "certification_root",
    "excluded_tables",
    "fold_root",
    "full_tree",
    "group_key",
    "rooted_tables",
    "store_leaves",
]
