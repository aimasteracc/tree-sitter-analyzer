"""已收敛刷新的记录：零变化判定的内容证据（#1671）。

缺少可选语法等稳定失败（``failure_kind: stable``）不写索引行，清单因而不认证，
调用图标记也保持撤销。#1631 的零变化判定只认可已认证的父版本，于是含此类文件
的项目每次刷新都重新回填并发布一份完整副本。

本记录说明一个版本“是一次完整项目刷新运行的直接结果：除下列稳定失败（可以为空）
外与源码一致，调用图流水线已在这些内容上收敛”。只有满足以下全部条件的索引运行
才写入它：

* 候选完整（无发现错误、无截断、计数对账），运行中无文件变化、无回填错误；
* 每个错误都是带文件与内容摘要的稳定失败，索引行恰好等于“选中文件减失败文件”；
* 本次运行完整执行了调用图流水线（回填零错误）；没有失败时，本次运行还必须
  成功盖了清单（认证为 complete）。

记录逐项绑定 ``(文件, 内容摘要, 失败原因)``，并绑定项目根、源码范围描述、提取器
版本与调用图流水线版本。任何写入私有副本的操作开始前都会清除继承自父版本的
记录（``GenerationStore.begin``，运行自身开始时亦然），只有满足上述条件的运行在
结束时重新签发。单文件写入、失效、仅解析、派生数据持久化等操作产生的版本因此
不带记录：其后的刷新照常运行（并重新盖清单），不会把未经回填或已过期的认证
当作零变化保留下来。

它是 ``ast_cache_metadata`` 中的一个控制键，不进入 ``index_fingerprint``；不改变
完整性语义：带稳定失败的版本仍是 partial，读者照旧拒绝把它认证为 complete。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: ``ast_cache_metadata`` 中的键。
RECORD_KEY = "tsa.converged_refresh"
RECORD_VERSION = 1
#: 记录的字节上限；超过即不签发（失败文件过多时退回真实运行）。
_RECORD_BYTE_LIMIT = 1024 * 1024
_SHA256_HEX = frozenset("0123456789abcdef")


@dataclass(frozen=True, slots=True)
class StableFailure:
    """一个稳定失败：文件、解析器拒绝的那份字节的摘要、失败原因。"""

    file: str
    content_hash: str
    reason: str


@dataclass(frozen=True, slots=True)
class StableFailureRecord:
    """一个已收敛版本的稳定失败集合及其绑定的环境。"""

    root: str
    scope: str
    extractor_version: int
    pipeline_version: int
    failures: tuple[StableFailure, ...]

    def by_file(self) -> dict[str, StableFailure]:
        return {failure.file: failure for failure in self.failures}


def current_extractor_version() -> int:
    """项目索引与单文件入口各有一份提取器版本常量；取二者较大者（运行时读取）。"""
    from .. import ast_cache
    from . import indexer

    return max(
        int(indexer._AST_CACHE_EXTRACTOR_VERSION),
        int(ast_cache.ASTCache._extractor_version),
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and _SHA256_HEX.issuperset(value)


def failures_from_details(
    details: Iterable[Any], errors: int
) -> tuple[StableFailure, ...] | None:
    """全部错误都是带文件与完整摘要的稳定失败时返回它们（无错误为空元组），否则 ``None``。"""
    from .publication_policy import FAILURE_KIND, STABLE

    found: dict[str, StableFailure] = {}
    count = 0
    for detail in details:
        if not isinstance(detail, Mapping) or detail.get("status") != "error":
            continue
        count += 1
        file = detail.get("file")
        reason = detail.get("reason")
        content_hash = detail.get("content_hash")
        if (
            detail.get(FAILURE_KIND) != STABLE
            or not isinstance(file, str)
            or not file
            or not isinstance(reason, str)
            or not _is_sha256(content_hash)
            or file in found
        ):
            return None
        found[file] = StableFailure(file, str(content_hash), reason)
    if count != errors:
        return None
    return tuple(sorted(found.values(), key=lambda failure: failure.file))


def _encode(record: StableFailureRecord) -> str:
    return json.dumps(
        {
            "version": RECORD_VERSION,
            "root": record.root,
            "scope": record.scope,
            "extractor_version": record.extractor_version,
            "pipeline_version": record.pipeline_version,
            "failures": [
                [failure.file, failure.content_hash, failure.reason]
                for failure in record.failures
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _decode(value: object) -> StableFailureRecord | None:
    if not isinstance(value, str) or len(value) > _RECORD_BYTE_LIMIT:
        return None
    try:
        data = json.loads(value)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("version") != RECORD_VERSION:
        return None
    root, scope = data.get("root"), data.get("scope")
    extractor, pipeline = data.get("extractor_version"), data.get("pipeline_version")
    raw = data.get("failures")
    if (
        not isinstance(root, str)
        or not isinstance(scope, str)
        or type(extractor) is not int
        or type(pipeline) is not int
        or not isinstance(raw, list)
    ):
        return None
    failures: list[StableFailure] = []
    for item in raw:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or not all(isinstance(part, str) for part in item)
            or not item[0]
            or not _is_sha256(item[1])
        ):
            return None
        failures.append(StableFailure(item[0], item[1], item[2]))
    if len({failure.file for failure in failures}) != len(failures):
        return None
    return StableFailureRecord(root, scope, extractor, pipeline, tuple(failures))


def _has_metadata_table(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='ast_cache_metadata' LIMIT 1"
        ).fetchone()
        is not None
    )


def read_record(conn: sqlite3.Connection) -> StableFailureRecord | None:
    """读取并严格校验记录；缺失、畸形或表不存在均为 ``None``。"""
    try:
        if not _has_metadata_table(conn):
            return None
        row = conn.execute(
            "SELECT value FROM ast_cache_metadata WHERE key = ?", (RECORD_KEY,)
        ).fetchone()
    except sqlite3.Error:
        return None
    return None if row is None else _decode(row[0])


def clear_record(conn: sqlite3.Connection) -> None:
    """删除记录（在调用方的事务内；由调用方提交）。"""
    if _has_metadata_table(conn):
        conn.execute("DELETE FROM ast_cache_metadata WHERE key = ?", (RECORD_KEY,))


def clear_record_at(database: Path) -> None:
    """私有副本建立后立即清除继承的记录：其后的写入尚未证明收敛。"""
    connection = sqlite3.connect(database)
    try:
        clear_record(connection)
        connection.commit()
    finally:
        connection.close()


def issue_record(
    conn: sqlite3.Connection,
    *,
    project_root: str,
    scope: str,
    extractor_version: int,
    failures: tuple[StableFailure, ...],
) -> bool:
    """签发记录并提交；表缺失或超出上限时不签发。"""
    from .callgraph_state import CALL_GRAPH_PIPELINE_VERSION

    record = StableFailureRecord(
        root=os.path.realpath(os.path.abspath(project_root)),
        scope=scope,
        extractor_version=extractor_version,
        pipeline_version=CALL_GRAPH_PIPELINE_VERSION,
        failures=failures,
    )
    value = _encode(record)
    if len(value) > _RECORD_BYTE_LIMIT or not _has_metadata_table(conn):
        return False
    conn.execute(
        "INSERT INTO ast_cache_metadata (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (RECORD_KEY, value),
    )
    conn.commit()
    return True


def _indexed_paths(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0]).replace("\\", "/") if os.name == "nt" else str(row[0])
        for row in conn.execute("SELECT file_path FROM ast_index")
    }


def issue_after_stamp(
    conn: sqlite3.Connection, project_root: str, candidate: Any, scope: Any
) -> bool:
    """调用方刚成功盖出清单（无失败、调用图标记当前）后签发记录。

    供在索引运行之外单独盖清单的路由（``index action=full``）使用：盖戳本身已
    要求调用图标记当前、源码清单与索引行一致；这里再核验候选精确与行集合。
    """
    from ..index_source_snapshot import canonical_source_scope_descriptor
    from .callgraph_state import call_graph_marker_is_current

    if scope is None or not call_graph_marker_is_current(conn):
        return False
    return issue_after_run(
        conn,
        project_root=project_root,
        candidate=candidate,
        scope=canonical_source_scope_descriptor(scope),
        extractor_version=current_extractor_version(),
        details=(),
        errors=0,
        converged=True,
        stamped=True,
    )


def candidate_is_exact(candidate: Any) -> bool:
    """候选覆盖完整范围：无发现错误、无截断、计数对账。"""
    return bool(
        candidate is not None
        and candidate.errors == 0
        and candidate.discovery_error is None
        and not candidate.truncated_by_max_files
        and candidate.discovery_reconciled
    )


def issue_after_run(
    conn: sqlite3.Connection,
    *,
    project_root: str,
    candidate: Any,
    scope: str,
    extractor_version: int,
    details: Iterable[Any],
    errors: int,
    converged: bool,
    stamped: bool,
) -> bool:
    """运行结束时签发记录：仅当除稳定失败外完全精确且调用图流水线已收敛。

    ``converged`` 由调用方给出：本次运行完整执行了回填且零错误、运行中无文件
    变化、无截断、无不完整跳过。``stamped``：本次运行成功盖了清单；没有失败时
    必须为真（继承自父版本的清单不能代表本次内容）。其余条件在此核验。
    """
    if not converged or not candidate_is_exact(candidate):
        return False
    failures = failures_from_details(details, errors)
    if failures is None or (not failures and not stamped):
        return False
    selected = {entry.rel_path for entry in candidate.selected_entries}
    failed = {failure.file for failure in failures}
    if not failed <= selected or _indexed_paths(conn) != selected - failed:
        return False
    try:
        return issue_record(
            conn,
            project_root=project_root,
            scope=scope,
            extractor_version=extractor_version,
            failures=failures,
        )
    except sqlite3.Error:
        # 签发失败只意味着下一次刷新走真实运行；绝不影响本次结果。
        conn.rollback()
        logger.warning("stable-failure record could not be issued", exc_info=True)
        return False
