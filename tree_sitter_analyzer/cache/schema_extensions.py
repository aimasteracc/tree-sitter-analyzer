"""已发布 canonical 14/15 与 Pulse 16/LSP 17 的原子扩展迁移。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager

CURRENT_SCHEMA_VERSION = 17
RecordFn = Callable[[sqlite3.Connection, int, str], None]

SCHEMA_V16_COMMENTS = """
CREATE TABLE IF NOT EXISTS ast_symbol_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id INTEGER NOT NULL REFERENCES ast_symbol_rows(id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    text TEXT NOT NULL,
    kind TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_symbol ON ast_symbol_comments(symbol_id);
"""

SCHEMA_V17_LSP_CACHE = """
CREATE TABLE IF NOT EXISTS lsp_resolution_cache (
    symbol_id INTEGER REFERENCES ast_symbol_rows(id),
    edge_id INTEGER REFERENCES edges(id),
    resolved_type TEXT,
    resolved_file TEXT,
    resolved_line INTEGER,
    lsp_server TEXT NOT NULL,
    cached_at INTEGER NOT NULL,
    PRIMARY KEY (edge_id, lsp_server)
);
CREATE INDEX IF NOT EXISTS idx_lsp_edge ON lsp_resolution_cache(edge_id);
CREATE INDEX IF NOT EXISTS idx_lsp_sym ON lsp_resolution_cache(symbol_id);
"""


@contextmanager
def schema_update(conn: sqlite3.Connection) -> Iterator[None]:
    """DDL、数据修复和版本凭证共用保存点；异常及中断均回滚，不提交外层事务。"""
    conn.execute("SAVEPOINT tsa_schema_update")
    try:
        yield
        conn.execute("RELEASE SAVEPOINT tsa_schema_update")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK TO SAVEPOINT tsa_schema_update")
            conn.execute("RELEASE SAVEPOINT tsa_schema_update")
        raise


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, kind: str) -> None:
    """仅接受本模块固定表列名，按物理布局补列，不信任历史版本号。"""
    columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


def _execute_ddl(conn: sqlite3.Connection, ddl: str) -> None:
    """执行本模块不含内嵌分号的固定 DDL，避免 executescript 隐式提交。"""
    for statement in ddl.split(";"):
        if statement.strip():
            conn.execute(statement)


def apply_migration_v14(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """canonical v14：新增可空 certified_at，保留已有认证值。"""
    with schema_update(conn):
        _ensure_column(conn, "ast_index", "certified_at", "INTEGER")
        record_fn(
            conn,
            14,
            "Add certified_at column to ast_index (partial certification model)",
        )


def apply_migration_v15(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """canonical v15：新增可空 activation_state，NULL 保持原先的 pre-lazy 语义。"""
    with schema_update(conn):
        _ensure_column(conn, "ast_symbol_activation", "activation_state", "TEXT")
        record_fn(
            conn,
            15,
            "Add activation_state column to ast_symbol_activation (lazy activation model)",
        )


def apply_migration_v16(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """新增 Pulse 投影并修复旧实验 v15；失效消息交给 lazy activation 重算。"""
    with schema_update(conn):
        apply_migration_v14(conn, record_fn)
        apply_migration_v15(conn, record_fn)
        _ensure_column(conn, "ast_symbol_activation", "last_commit_msg", "TEXT")
        conn.execute(
            "SELECT symbol_id,file_path,last_modified_commit,last_modified_at,"
            "mod_count_30d,mod_count_90d,mod_count_all,computed_at,git_state,"
            "activation_state,last_commit_msg FROM ast_symbol_activation LIMIT 0"
        )
        _execute_ddl(conn, SCHEMA_V16_COMMENTS)
        conn.execute(
            "SELECT id,symbol_id,line,text,kind FROM ast_symbol_comments LIMIT 0"
        )
        conn.execute(
            "UPDATE ast_symbol_activation SET activation_state='pending' "
            "WHERE (last_commit_msg IS NULL OR activation_state IS NULL) "
            "AND activation_state IS NOT 'disabled'"
        )
        # 历史实验版本号发生冲突，规范化凭证描述，但保留原 applied_at。
        conn.execute(
            "UPDATE ast_schema_version SET description=? WHERE version=14",
            ("Add certified_at column to ast_index (partial certification model)",),
        )
        conn.execute(
            "UPDATE ast_schema_version SET description=? WHERE version=15",
            (
                "Add activation_state column to ast_symbol_activation (lazy activation model)",
            ),
        )
        record_fn(
            conn, 16, "Pulse comments and commit messages; canonical layout repair"
        )


def apply_migration_v17(conn: sqlite3.Connection, record_fn: RecordFn) -> None:
    """新增 LSP 缓存；实验版已有的解析行和键保持不变。"""
    with schema_update(conn):
        _execute_ddl(conn, SCHEMA_V17_LSP_CACHE)
        conn.execute(
            "SELECT symbol_id,edge_id,resolved_type,resolved_file,resolved_line,lsp_server,cached_at FROM lsp_resolution_cache LIMIT 0"
        )
        record_fn(conn, 17, "LSP resolution cache")
