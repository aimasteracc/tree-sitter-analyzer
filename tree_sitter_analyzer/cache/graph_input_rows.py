"""内存调用图输入的原始行与到字典的转换（#1657）。

``CachedCallGraph`` 以构图输入的内容摘要复用已建好的图。命中时只需证明输入未变，
不需要把 18.7 万条边转换成字典、也不需要解析每个文件的 ``symbols_json``：

- 调用边按元组读取（游标 ``row_factory = None``），摘要直接取自这些元组；
  未命中时再用同一批元组转换成与 ``dict(sqlite3.Row)`` 完全相同的字典
  （键为列名、顺序为列序）。实测读取由 1.4–1.8 s 降到 0.8–1.0 s。
- 函数定义按 ``(file_path, symbols_json, language)`` 原始行读取，摘要取自原始文本，
  未命中时才解析。

``ASTCache`` 与认证快照（``CertifiedSnapshotCache``）共用这里的 SQL 与转换，
``get_call_edges`` / ``get_functions`` 的返回值与改动前逐项相同。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, cast

from .helpers import _build_function_entry

#: ``get_call_edges`` 的唯一 SQL（#1559/#1560：带持久化解析列；RFC-0038 / #1618：
#: 注解绑定的边带上 ``metadata.receiver_binding``；#1670：经改名导入解析的边带上
#: 目标的真实名字 ``import_alias_name``）。ASTCache 与认证快照共用。
CALL_EDGE_SQL = (
    "SELECT caller_name, file_path AS caller_file, caller_line, "
    "callee_name, callee_full, callee_line, file_path, language, "
    "callee_resolution, callee_resolved_file, "
    "CASE WHEN callee_resolution = 'annotated_receiver' "
    "THEN json_extract(metadata, '$.receiver_binding') END "
    "AS receiver_binding, "
    "CASE WHEN callee_resolution = 'project' AND instr(metadata, 'import_alias') > 0 "
    "THEN json_extract(metadata, '$.import_alias.name') END "
    "AS import_alias_name "
    "FROM edges WHERE kind = 'calls'"
)
#: ``get_functions`` 读取的原始列。
FUNCTION_ROWS_SQL = "SELECT file_path, symbols_json, language FROM ast_index"
#: 构图使用的符号种类。
_FUNCTION_KINDS = ("function", "method")


@dataclass(frozen=True)
class CallEdgeRows:
    """按读取顺序保存的调用边元组及其列名。"""

    names: tuple[str, ...]
    rows: list[tuple[Any, ...]]

    def to_dicts(self) -> list[dict[str, Any]]:
        """与 ``[dict(row) for row in cursor]``（``sqlite3.Row``）逐项相同。"""
        names = self.names
        return [dict(zip(names, row, strict=True)) for row in self.rows]

    def digest_parts(self) -> tuple[Any, ...]:
        return (self.names, self.rows)


@dataclass(frozen=True)
class FunctionRows:
    """``ast_index`` 的 ``(file_path, symbols_json, language)`` 原始行。"""

    rows: list[tuple[Any, ...]]

    def to_functions(self) -> list[dict[str, Any]]:
        """与 ``get_functions`` 的既有实现逐项相同。"""
        return [
            _build_function_entry(symbol, file_path, language)
            for file_path, symbols_json, language in self.rows
            for symbol in json.loads(symbols_json).get("symbols", [])
            if symbol.get("kind") in _FUNCTION_KINDS
        ]

    def digest_parts(self) -> tuple[Any, ...]:
        return (self.rows,)


def _tuple_cursor(conn: sqlite3.Connection, sql: str) -> sqlite3.Cursor:
    cursor = conn.cursor()
    cursor.row_factory = None
    cursor.execute(sql)
    return cursor


def read_call_edge_rows(conn: sqlite3.Connection) -> CallEdgeRows:
    """读取全部 CALLS 边（元组）；SQL 错误原样抛出，由调用方决定语义。"""
    cursor = _tuple_cursor(conn, CALL_EDGE_SQL)
    names = tuple(str(column[0]) for column in cursor.description)
    return CallEdgeRows(names, cursor.fetchall())


def read_function_rows(conn: sqlite3.Connection) -> FunctionRows:
    """读取全部 ``ast_index`` 的函数定义原始行；SQL 错误原样抛出。"""
    return FunctionRows(_tuple_cursor(conn, FUNCTION_ROWS_SQL).fetchall())


def read_edge_source(cache: Any) -> CallEdgeRows | list[dict[str, Any]]:
    """构图的边输入：优先原始元组；缓存未提供时退回 ``get_call_edges``。"""
    reader = getattr(cache, "get_call_edge_rows", None)
    if callable(reader):
        rows = reader()
        if isinstance(rows, CallEdgeRows):
            return rows
    return cast(list[dict[str, Any]], cache.get_call_edges())


def read_function_source(cache: Any) -> FunctionRows | list[dict[str, Any]]:
    """构图的函数输入：优先未解析的原始行；缓存未提供时退回 ``get_functions``。"""
    reader = getattr(cache, "get_function_rows", None)
    if callable(reader):
        rows = reader()
        if isinstance(rows, FunctionRows):
            return rows
    return cast(list[dict[str, Any]], cache.get_functions())


def source_digest_parts(source: Any) -> tuple[Any, ...]:
    """摘要用的表示；带类型标记，原始行与字典列表永不混同。"""
    if isinstance(source, CallEdgeRows | FunctionRows):
        return (type(source).__name__, *source.digest_parts())
    return ("list", source)


def materialize_edges(source: Any) -> list[dict[str, Any]]:
    return source.to_dicts() if isinstance(source, CallEdgeRows) else list(source)


def materialize_functions(source: Any) -> list[dict[str, Any]]:
    return source.to_functions() if isinstance(source, FunctionRows) else list(source)
