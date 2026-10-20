"""RFC-0039 slice 2：只重算被改动的组的增量认证根。

一次刷新在写者连接上“武装”：

* 武装时本连接尚未写入任何行（``total_changes == 0``），即数据库仍是父版本已认证
  的内容；记录 ``PRAGMA data_version`` 与根内表清单，并在每张根内表上安装
  TEMP 触发器，把被写入的 ``(表, file_path)`` 记入 TEMP 表（值不变的 UPDATE 不记）；
* 盖章时（同一连接、同一未提交状态）若下列条件全部成立，就从父版本存放的叶
  出发只重算脏组，折叠出新根：
  - 武装有效；``data_version`` 未变（没有别的连接或进程提交过）；
  - 根内表清单与建表语句未变；
  - 父 manifest 为 v3、规范根相同，且存放的叶折叠后正好等于父根。

否则完整重算，并记下原因（``certification: {mode, reason}``）。

校验者：``TSA_CERTIFICATION_VERIFY=full``（测试套件默认开启）时每次盖章都另做
一次完整重算；生产中每 :data:`VERIFY_EVERY` 次增量盖章或叶超过
:data:`VERIFY_MAX_AGE_SECONDS` 也完整重算。不一致时**失败闭合**：抛出
``CERTIFICATION_TREE_MISMATCH``，manifest 不写入，并记入 :func:`mismatches`
供测试套件断言。读者从不信任存放的叶，总是独立重算根。

TEMP 对象只存在于该连接，不进入索引文件。
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
import zlib
from dataclasses import dataclass
from typing import Any

from ..index_certification_tree import (
    GROUP_COLUMN,
    LEAF_TABLE,
    MANIFEST_VERSION,
    CertificationTree,
    RootedTable,
    fold_root,
    full_tree,
    group_key,
    rooted_tables,
)

logger = logging.getLogger(__name__)

#: 每次盖章都另做完整重算并比较（测试套件开启）。
VERIFY_ENV = "TSA_CERTIFICATION_VERIFY"
#: 连续增量盖章达到这个次数后，下一次完整重算。
VERIFY_EVERY = 20
#: 上次完整重算超过这个时长后，下一次完整重算。
VERIFY_MAX_AGE_SECONDS = 24 * 3600
#: 一张表的脏组超过这个比例时，整表单次有序扫描比逐组查询便宜。
DENSE_FRACTION = 0.25
STATE_TABLE = "ast_certification_state"
STATE_TABLE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {STATE_TABLE} ("
    "id INTEGER PRIMARY KEY CHECK (id = 1), "
    "incremental_since_full INTEGER NOT NULL, full_at INTEGER NOT NULL)"
)
_STATE_COLUMNS = ("id", "incremental_since_full", "full_at")
#: “上次盖章后有写入”标记：放在每个索引都有的控制表 ``ast_cache_metadata`` 里，
#: 持久触发器体只引用这张表（它从不被删除，触发器因而不会让写入失败）。
STALE_KEY = "certification_stale"
_METADATA = "ast_cache_metadata"
_DIRTY = "tsa_cert_dirty"
_EVENTS = ("INSERT", "UPDATE", "DELETE")
_WHOLE = "*"
_ARM_DEADLINE_SECONDS = 30.0
MISMATCH = "CERTIFICATION_TREE_MISMATCH"


@dataclass
class _Arm:
    token: str
    data_version: int | None
    tables: tuple[RootedTable, ...]
    reason: str | None


@dataclass(frozen=True)
class CertificationDecision:
    """本次盖章用了增量还是完整重算，以及原因（写入刷新结果，供审计）。"""

    mode: str
    reason: str
    dirty_groups: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "dirty_groups": self.dirty_groups,
        }


#: 连接 -> 状态。``sqlite3.Connection`` 不支持弱引用，``id`` 可能在连接关闭后被
#: 复用，因此每项都带一个随机令牌，同一令牌也写在该连接的 TEMP 表里；新连接
#: 没有这张表，旧状态永远不会被误用。
_INIT: dict[int, tuple[str, int, bool]] = {}
_ARMED: dict[int, _Arm] = {}
_LAST: dict[int, CertificationDecision] = {}
_MISMATCHES: list[str] = []
_TOKENS = "tsa_cert_tokens"


def _set_token(conn: sqlite3.Connection, kind: str) -> str:
    """令牌编码在 TEMP 表名里：只用 DDL，不开启隐式事务、不计入 ``total_changes``。"""
    _drop_token(conn, kind)
    token = uuid.uuid4().hex
    conn.execute(f"CREATE TEMP TABLE {_TOKENS}_{kind}_{token} (x INTEGER)")  # nosec B608
    return token


def _token_tables(conn: sqlite3.Connection, kind: str) -> list[str]:
    prefix = f"{_TOKENS}_{kind}_"
    return [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_temp_master WHERE type = 'table' AND name LIKE ?",
            (prefix + "%",),
        )
    ]


def _token(conn: sqlite3.Connection, kind: str) -> str | None:
    try:
        names = _token_tables(conn, kind)
    except sqlite3.Error:
        return None
    if len(names) != 1:
        return None
    return names[0][len(f"{_TOKENS}_{kind}_") :]


def _drop_token(conn: sqlite3.Connection, kind: str) -> None:
    for name in _token_tables(conn, kind):
        conn.execute(f"DROP TABLE IF EXISTS temp.{name}")  # nosec B608


def note_initialized(conn: sqlite3.Connection, migrated: bool) -> None:
    """缓存的 schema 初始化完成时调用：记下此刻的写入计数，以及是否执行过迁移。

    初始化本身会写入与认证内容无关的行（FTS5 能力探测表随建随删）；之后到
    武装之间若再有任何行写入，武装时计数不符，退回完整重算。
    """
    try:
        token = _set_token(conn, "init")
        _INIT[id(conn)] = (token, conn.total_changes, migrated)
    except sqlite3.Error:
        logger.debug("certification baseline could not be recorded", exc_info=True)
        _INIT.pop(id(conn), None)


def arm(conn: sqlite3.Connection) -> None:
    """刷新开始、本连接在初始化之后写入任何行之前调用。"""
    # 先判断，再撤销旧武装。
    try:
        tables = rooted_tables(conn, time.monotonic() + _ARM_DEADLINE_SECONDS)
    except Exception:  # nosec B110 — 读不到表清单：不武装，完整重算。
        logger.debug("certification tracking could not list tables", exc_info=True)
        tables = ()
    reason = _arming_blocker(conn, tables)
    disarm(conn)
    try:
        token = _set_token(conn, "arm")
        if reason is not None:
            _ARMED[id(conn)] = _Arm(token, None, (), reason)
            return
        # 只用 DDL：重建（而非清空）脏组表，不开启隐式事务。
        conn.execute(f"DROP TABLE IF EXISTS temp.{_DIRTY}")  # nosec B608 — 模块常量
        conn.execute(
            f"CREATE TEMP TABLE {_DIRTY} "  # nosec B608 — 模块常量
            # 不设唯一约束：触发器体内的 OR IGNORE 会被外层语句的冲突策略覆盖，
            # 重复的组在读取时去重。
            "(tbl TEXT NOT NULL, grp TEXT NOT NULL)"
        )
        for index, table in enumerate(tables):
            _install_triggers(conn, table, index)
        _ARMED[id(conn)] = _Arm(token, _data_version(conn), tables, None)
    except sqlite3.Error:
        logger.debug("certification tracking could not be armed", exc_info=True)
        disarm(conn)


def _arming_blocker(
    conn: sqlite3.Connection, tables: tuple[RootedTable, ...]
) -> str | None:
    """武装前的写入证明：库内容仍是上次盖章时的内容。

    * 本连接：初始化基线存在、未迁移，且此后没有写入任何行；
    * 任何连接、任何代码路径、任何版本：上次盖章后，根内表都带着持久触发器，
      第一次写入就把 ``stale`` 置 1（盖章失败的运行、单文件写入、旧版本写入
      都会留下这个标记）；标记仍为 0 才说明父版本的叶描述的就是现在的行。
    """
    baseline = _INIT.get(id(conn))
    if baseline is None or _token(conn, "init") != baseline[0]:
        return "NOT_INITIALIZED"
    if baseline[2]:
        return "MIGRATED"
    if conn.total_changes != baseline[1]:
        return "WRITES_BEFORE_ARMING"
    return _stale_blocker(conn, tables)


def _stale_trigger_name(table: str, event: str) -> str:
    return f"tsa_cert_stale_{zlib.crc32(table.encode('utf-8')):08x}_{event.lower()}"


def _stale_blocker(
    conn: sqlite3.Connection, tables: tuple[RootedTable, ...]
) -> str | None:
    try:
        row = conn.execute(
            f"SELECT value FROM {_METADATA} WHERE key = ?",  # nosec B608 — 模块常量
            (STALE_KEY,),
        ).fetchone()
        triggers = {
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND name LIKE 'tsa_cert_stale_%'"
            )
        }
    except sqlite3.Error:
        return "NO_STALE_TRACKING"
    expected = {
        _stale_trigger_name(table.name, event) for table in tables for event in _EVENTS
    }
    if row is None or not tables or not expected <= triggers:
        return "NO_STALE_TRACKING"
    return None if row[0] == "0" else "WRITTEN_SINCE_STAMP"


def _ensure_stale_triggers(
    conn: sqlite3.Connection, tables: tuple[RootedTable, ...]
) -> None:
    """盖章时为每张根内表装上持久触发器，并把标记归零：此后第一次写入把它置 1。"""
    flag = f"(SELECT value FROM {_METADATA} WHERE key = '{STALE_KEY}')"
    for table in tables:
        for event in _EVENTS:
            conn.execute(
                f"CREATE TRIGGER IF NOT EXISTS {_stale_trigger_name(table.name, event)} "
                f"AFTER {event} ON {_quote(table.name)} "
                f"WHEN {flag} = '0' "
                f"BEGIN UPDATE {_METADATA} SET value = '1' WHERE key = '{STALE_KEY}'; END"
            )
    conn.execute(
        f"INSERT OR REPLACE INTO {_METADATA} (key, value) VALUES (?, '0')",  # nosec B608
        (STALE_KEY,),
    )


def disarm(conn: sqlite3.Connection) -> None:
    """撤销武装：删除本连接的全部增量认证 TEMP 触发器与脏组表。"""
    _ARMED.pop(id(conn), None)
    try:
        names = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_temp_master "
                "WHERE type = 'trigger' AND name LIKE 'tsa_cert_%'"
            )
        ]
        for name in names:
            conn.execute(f"DROP TRIGGER IF EXISTS temp.{name}")  # nosec B608
        conn.execute(f"DROP TABLE IF EXISTS temp.{_DIRTY}")  # nosec B608
        _drop_token(conn, "arm")
    except Exception:  # nosec B110 — 撤销失败只让下一次盖章完整重算。
        logger.debug("certification tracking could not be disarmed", exc_info=True)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _install_triggers(
    conn: sqlite3.Connection, table: RootedTable, index: int
) -> list[str]:
    literal = "'" + table.name.replace("'", "''") + "'"
    names = []
    same = " AND ".join(f"OLD.{_quote(c)} IS NEW.{_quote(c)}" for c in table.columns)
    for event, refs in (
        ("INSERT", ("NEW",)),
        ("UPDATE", ("OLD", "NEW")),
        ("DELETE", ("OLD",)),
    ):
        name = f"tsa_cert_{index}_{event.lower()}"
        body = " ".join(
            f"INSERT INTO {_DIRTY} (tbl, grp) "
            f"VALUES ({literal}, {_group_expression(table, ref)});"
            for ref in refs
        )
        when = f"WHEN NOT ({same}) " if event == "UPDATE" else ""
        conn.execute(
            f"CREATE TEMP TRIGGER {name} AFTER {event} ON main.{_quote(table.name)} "
            f"{when}BEGIN {body} END"
        )
        names.append(name)
    return names


def _group_expression(table: RootedTable, ref: str) -> str:
    """触发器里记录分组的 SQL 表达式：``quote(file_path)``，整表一组时为常量。"""
    if table.grouped:
        return f"quote({ref}.{_quote(GROUP_COLUMN)})"
    return f"'{_WHOLE}'"


def _data_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA data_version").fetchone()[0])


def _unquote(literal: str) -> object:
    """``quote()`` 结果还原为值（NULL、文本、整数、浮点、BLOB）。"""
    if literal == "NULL":
        return None
    if literal.startswith("'"):
        return literal[1:-1].replace("''", "'")
    if literal[:2] in ("X'", "x'"):
        return bytes.fromhex(literal[2:-1])
    try:
        return int(literal)
    except ValueError:
        return float(literal)


def commitment(
    conn: sqlite3.Connection, root: str, *, deadline: float
) -> tuple[str, CertificationTree]:
    """盖章用的认证根与认证树：能证明增量有效时只重算脏组，否则完整重算。"""
    try:
        decision, tree = _incremental(conn, root, deadline)
        index = fold_root(root, tree, deadline) if tree is not None else None
        if index is None or tree is None:
            tree = full_tree(conn, deadline=deadline)
            index = fold_root(root, tree, deadline)
            _ensure_stale_triggers(conn, tree.tables)
            _record_full(conn)
        elif _verify_due(conn):
            full = full_tree(conn, deadline=deadline)
            full_index = fold_root(root, full, deadline)
            if full_index != index:
                _MISMATCHES.append(f"{root}: {decision.reason}")
                logger.error(
                    "incremental certification root differs from a full recompute"
                )
                raise sqlite3.OperationalError(MISMATCH)
            _ensure_stale_triggers(conn, tree.tables)
            _record_full(conn)
        else:
            _ensure_stale_triggers(conn, tree.tables)
            _record_incremental(conn)
        _LAST[id(conn)] = decision
        return index, tree
    finally:
        disarm(conn)


def _incremental(
    conn: sqlite3.Connection, root: str, deadline: float
) -> tuple[CertificationDecision, CertificationTree | None]:
    state = _ARMED.get(id(conn))
    if state is None or _token(conn, "arm") != state.token:
        return CertificationDecision("full", "NOT_ARMED"), None
    if state.reason is not None:
        return CertificationDecision("full", state.reason), None
    if _data_version(conn) != state.data_version:
        return CertificationDecision("full", "OTHER_CONNECTION_COMMITTED"), None
    tables = rooted_tables(conn, deadline)
    if tables != state.tables:
        return CertificationDecision("full", "TABLES_CHANGED"), None
    parent = _parent_root(conn, root)
    if parent is None:
        return CertificationDecision("full", "PARENT_NOT_V3"), None
    leaves = _stored_leaves(conn, tables)
    if (
        leaves is None
        or fold_root(root, CertificationTree(tables, leaves), deadline) != parent
    ):
        return CertificationDecision("full", "LEAVES_DO_NOT_FOLD"), None
    dirty = _dirty_groups(conn)
    count = sum(len(groups) for groups in dirty.values())
    tree = CertificationTree(tables, leaves)
    from ..index_certification_tree import _Budget, _hash_table

    for table in tables:
        groups = dirty.get(table.name)
        if not groups:
            continue
        if not table.grouped or len(groups) > DENSE_FRACTION * max(
            1, len(leaves[table.name])
        ):
            tree.leaves[table.name] = _hash_table(conn, table, deadline, _Budget())
            continue
        for value in groups:
            _rehash_group(conn, table, value, tree, deadline)
    return CertificationDecision("incremental", "DEPENDENCIES_TRACKED", count), tree


def _parent_root(conn: sqlite3.Connection, root: str) -> str | None:
    try:
        row = conn.execute(
            "SELECT canonical_root, index_fingerprint, manifest_version "
            "FROM ast_index_snapshot_manifest"
        ).fetchall()
    except sqlite3.Error:
        return None
    if len(row) != 1 or row[0][0] != root or row[0][2] != MANIFEST_VERSION:
        return None
    return str(row[0][1])


def _stored_leaves(
    conn: sqlite3.Connection, tables: tuple[RootedTable, ...]
) -> dict[str, dict[bytes, bytes]] | None:
    try:
        rows = conn.execute(f"SELECT tbl, grp, leaf FROM {LEAF_TABLE}").fetchall()  # nosec B608
    except sqlite3.Error:
        return None
    leaves: dict[str, dict[bytes, bytes]] = {table.name: {} for table in tables}
    for table, key, leaf in rows:
        if table not in leaves:
            return None
        leaves[table][bytes(key)] = bytes(leaf)
    return leaves


def _dirty_groups(conn: sqlite3.Connection) -> dict[str, set[object]]:
    dirty: dict[str, set[object]] = {}
    for table, literal in conn.execute(f"SELECT DISTINCT tbl, grp FROM temp.{_DIRTY}"):  # nosec B608
        value: object = _WHOLE if literal == _WHOLE else _unquote(str(literal))
        dirty.setdefault(str(table), set()).add(value)
    return dirty


def _rehash_group(
    conn: sqlite3.Connection,
    table: RootedTable,
    value: object,
    tree: CertificationTree,
    deadline: float,
) -> None:
    import hashlib

    from ..index_certification_tree import _LEAF_DOMAIN, _ordered_select
    from ..index_snapshot_schema import _check_deadline, _frame, _typed

    digest = hashlib.sha256(_LEAF_DOMAIN)
    rows = 0
    for row in conn.execute(
        _ordered_select(table, f" WHERE {_quote(GROUP_COLUMN)} IS ?"), (value,)
    ):
        _check_deadline(deadline)
        _frame(digest, b"row", _typed(tuple(row)))
        rows += 1
    key = group_key(value)
    if rows:
        tree.leaves[table.name][key] = digest.digest()
    else:
        tree.leaves[table.name].pop(key, None)


def _verify_due(conn: sqlite3.Connection) -> bool:
    if os.environ.get(VERIFY_ENV, "").strip().lower() == "full":
        return True
    state = _read_state(conn)
    if state is None:
        return True
    since_full, full_at = state
    return (
        since_full + 1 >= VERIFY_EVERY or time.time() - full_at > VERIFY_MAX_AGE_SECONDS
    )


def _read_state(conn: sqlite3.Connection) -> tuple[int, int] | None:
    try:
        row = conn.execute(
            f"SELECT incremental_since_full, full_at FROM {STATE_TABLE} WHERE id = 1"  # nosec B608
        ).fetchone()
    except sqlite3.Error:
        return None
    return (int(row[0]), int(row[1])) if row is not None else None


def _ensure_state_table(conn: sqlite3.Connection) -> None:
    """校验计划表：列不符（旧格式）就重建——没有触发器引用它，重建是安全的。"""
    columns = tuple(
        str(row[1]) for row in conn.execute(f"PRAGMA table_info({STATE_TABLE})")
    )
    if columns and columns != _STATE_COLUMNS:
        conn.execute(f"DROP TABLE {STATE_TABLE}")  # nosec B608 — 模块常量
    conn.execute(STATE_TABLE_SQL)


def _write_state(conn: sqlite3.Connection, since_full: int, full_at: int) -> None:
    _ensure_state_table(conn)
    conn.execute(
        f"INSERT OR REPLACE INTO {STATE_TABLE} "  # nosec B608
        "(id, incremental_since_full, full_at) VALUES (1, ?, ?)",
        (since_full, full_at),
    )


def _record_full(conn: sqlite3.Connection) -> None:
    _write_state(conn, 0, int(time.time()))


def _record_incremental(conn: sqlite3.Connection) -> None:
    state = _read_state(conn)
    since_full, full_at = state if state is not None else (0, int(time.time()))
    _write_state(conn, since_full + 1, full_at)


def last_decision(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """本连接最近一次盖章的认证决定（取出即清除）。"""
    decision = _LAST.pop(id(conn), None)
    return decision.to_dict() if decision is not None else None


def mismatches() -> list[str]:
    """本进程中增量根与完整重算不一致的记录（测试套件断言其为空）。"""
    return list(_MISMATCHES)


def clear_mismatches() -> None:
    _MISMATCHES.clear()


__all__ = [
    "MISMATCH",
    "STATE_TABLE",
    "VERIFY_ENV",
    "CertificationDecision",
    "arm",
    "clear_mismatches",
    "commitment",
    "disarm",
    "last_decision",
    "mismatches",
]
