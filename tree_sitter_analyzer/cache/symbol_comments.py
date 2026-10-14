"""符号注释的清除与孤儿清扫（#1602）。

注释只通过 ``symbol_id`` 与 ``ast_symbol_rows`` 连接读取，且两张表的 ID 均为
``AUTOINCREMENT``，孤儿注释不会被重新挂到新符号上。此前每次逐文件写入都附带
``OR NOT EXISTS`` 孤儿清扫，规划器因此对整张注释表做全表扫描：#1602 剖析中
2,433 个文件累计 4,851 次、51 s（单次 36 ms，仅按文件删除为 0.5 ms）。

写入路径总是先删除本文件符号的注释、再删除符号行，本身不产生孤儿；唯一会产生
孤儿的是投影修复删除“未入索引”的符号行，因此清扫只在那里执行一次。
"""

from __future__ import annotations

import sqlite3


def _has_comments_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' "
        "AND name = 'ast_symbol_comments'"
    ).fetchone()
    return row is not None


def delete_file_symbol_comments(conn: sqlite3.Connection, rel_path: str) -> None:
    """显式清除该文件旧定义的注释；不能依赖所有 SQLite 调用方都启用外键级联。"""
    if _has_comments_table(conn):
        conn.execute(
            "DELETE FROM ast_symbol_comments WHERE symbol_id IN "
            "(SELECT id FROM ast_symbol_rows WHERE file_path=?)",
            (rel_path,),
        )


def prune_unindexed_symbol_rows(conn: sqlite3.Connection) -> None:
    """删除不属于任何已索引文件的符号行，并一次性清扫由此产生的孤儿注释。"""
    conn.execute(
        "DELETE FROM ast_symbol_rows WHERE file_path NOT IN "
        "(SELECT file_path FROM ast_index)"
    )
    if _has_comments_table(conn):
        conn.execute(
            "DELETE FROM ast_symbol_comments WHERE NOT EXISTS "
            "(SELECT 1 FROM ast_symbol_rows s WHERE s.id=ast_symbol_comments.symbol_id)"
        )
