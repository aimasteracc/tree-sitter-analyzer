"""#1746：按本轮结束时的文件集合解析 JS/TS ``imports`` 边的相对说明符。

写入一个文件的边时（``write_graph_edges_for_file``），相对说明符只能对照"已经索引的
文件"解析，结果取决于索引顺序：全新重建里导入方若排在目标之前，边写成 ``""``；
增量刷新时目标早已在索引里，写成目标文件。目标文件后来加入或删除时，未改动的导入方
的边也不会更新。这一步在两条路线的回填开始前运行，对全部这类边重新解析，使结果
只取决于最终的文件集合——刷新与全新重建写出相同的边。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from .write import _RELATIVE_SPECIFIER_LANGUAGES

logger = logging.getLogger(__name__)

_FILE_PREFIX = "file:"
_MODULE_PREFIX = "module:"
#: ``language`` 列取自同一份元数据：只读 JS/TS 的导入边，其他语言不解析 JSON。
_SELECT_SQL = (
    "SELECT id, source_node_id, target_node_id, metadata, callee_resolved_file "
    "FROM edges WHERE kind = 'imports' AND language IN ("  # nosec B608 — 常量语言列表
    + ", ".join(f"'{language}'" for language in _RELATIVE_SPECIFIER_LANGUAGES)
    + ")"
)
_UPDATE_SQL = "UPDATE edges SET callee_resolved_file = ?, metadata = ? WHERE id = ?"


def resolve_import_specifier_edges(conn: sqlite3.Connection) -> dict[str, int]:
    """重新解析全部 JS/TS ``imports`` 边；返回与其他回填阶段相同形状的统计。"""
    from ..synapse_resolver._typescript_imports import resolve_typescript_specifier

    stats = {"total": 0, "resolved": 0, "unchanged": 0, "errors": 0}
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name IN ('edges', 'ast_index')"
        )
    }
    if tables != {"edges", "ast_index"}:
        return stats  # 没有边表或索引表：没有可解析的导入边
    indexed = {str(row[0]) for row in conn.execute("SELECT file_path FROM ast_index")}
    updates: list[tuple[str, str, int]] = []
    for edge_id, source, target, metadata_text, current in conn.execute(_SELECT_SQL):
        metadata = _metadata(metadata_text)
        if (
            metadata is None
            or metadata.get("language") not in _RELATIVE_SPECIFIER_LANGUAGES
        ):
            continue
        if not str(source).startswith(_FILE_PREFIX) or not str(target).startswith(
            _MODULE_PREFIX
        ):
            continue
        stats["total"] += 1
        resolved = resolve_typescript_specifier(
            str(target)[len(_MODULE_PREFIX) :],
            str(source)[len(_FILE_PREFIX) :],
            indexed,
        )
        if (
            resolved == str(current or "")
            and metadata.get("callee_resolved_file") == resolved
        ):
            stats["unchanged"] += 1
            continue
        # 与 ``EdgeStore.upsert_edges`` 相同的序列化，转储与全新写入逐字相同。
        metadata["callee_resolved_file"] = resolved
        updates.append(
            (
                resolved,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                int(edge_id),
            )
        )
    if updates:
        conn.executemany(_UPDATE_SQL, updates)
        stats["resolved"] = len(updates)
    return stats


def _metadata(text: Any) -> dict[str, Any] | None:
    try:
        value = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return None
    return value if isinstance(value, dict) else None
