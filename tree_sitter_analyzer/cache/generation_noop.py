"""无变化的刷新不发布新版本（#1631）。

dogfood round 6（2026-10-16）：``index action=cache mode=index`` 即使 ``indexed=0
removed=0`` 也发布一份完整副本（实测 339 MB/份）。私有副本上运行的真实索引流程
仍是唯一权威：只有它报告零变化、且控制表（认证清单、调用图/解析/构建状态等）
与父版本逐行相同，才放弃发布并保留活动版本。

认证清单中的 ``index_fingerprint`` 覆盖每张查询可见表的每一行；零变化的运行会
重新盖章，因此清单逐行相同即说明查询可见内容与父版本一致，父版本的认证依然
有效。父版本未认证（没有清单）时照常发布，绝不以“未变”跳过一次可能的修复。
有变化的刷新仍经 ``GenerationStore.publish`` 的 CAS 与源码复核发布（RFC-0032）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

#: 跳过发布时返回的稳定原因码。
UNCHANGED_REASON = "INDEX_UNCHANGED"
#: 运行有非稳定失败（读写失败、回填失败等），结果不能替换父版本（#1635）。
NOT_PUBLISHABLE_REASON = "INDEX_NOT_PUBLISHABLE"

#: 与 ``index_snapshot_schema._CONTROL_TABLES`` 相同：不进入 ``index_fingerprint``
#: 的表，必须逐行比较。
_CONTROL_TABLES = (
    "ast_index_snapshot_manifest",
    "ast_cache_metadata",
    "ast_build_state",
    "ast_call_graph_state",
    "ast_resolve_state",
    "sqlite_sequence",
)
_MANIFEST = _CONTROL_TABLES[0]
#: 这些计数非零即表示本次运行写入了内容。
_INDEX_CHANGE_KEYS = ("indexed", "errors", "changed_during_run", "pruned")


def _rows(connection: sqlite3.Connection, table: str) -> list[tuple[Any, ...]] | None:
    """读取一张小控制表的全部行；表不存在返回 ``None``。"""
    present = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if present is None:
        return None
    cursor = connection.execute(f'SELECT * FROM "{table}"')  # nosec B608 - 固定表名
    return sorted((tuple(row) for row in cursor), key=repr)


def _control_state(database: Path) -> dict[str, list[tuple[Any, ...]] | None]:
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        return {table: _rows(connection, table) for table in _CONTROL_TABLES}
    finally:
        connection.close()


def same_certified_content(parent: Path, private: Path) -> bool:
    """父版本已认证，且私有副本的控制表与之逐行相同。读取失败视为有变化。"""
    try:
        before = _control_state(parent)
        after = _control_state(private)
    except sqlite3.Error:
        return False
    return bool(before[_MANIFEST]) and before == after


def index_run_unchanged(result: Any) -> bool:
    """项目索引结果报告零写入：无重新索引、无删除、无错误、无运行中变化。"""
    if not isinstance(result, Mapping) or result.get("backfill_errors"):
        return False
    if any(result.get(key) for key in _INDEX_CHANGE_KEYS):
        return False
    return not result.get("removed_files") and not result.get("activation_flushed")


def unpublished_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """如实报告未发布及原因；活动版本与其认证保持不变。"""
    return {**result, "published": False, "publication_reason": UNCHANGED_REASON}


def not_publishable_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """#1635：运行有非稳定失败，私有副本被放弃；活动版本保持不变。"""
    return {
        **result,
        "published": False,
        "publication_reason": NOT_PUBLISHABLE_REASON,
    }
