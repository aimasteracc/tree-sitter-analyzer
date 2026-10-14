#!/usr/bin/env python3
"""nav 调用关系答案的索引身份与源码新鲜度证据。

dogfood 2026-10-14：同一 MCP 服务器内，nav 一直使用首次构建的内存调用图；
重建索引后不刷新，源码编辑后也没有任何过期标记，新函数还被归咎为拼写错误。

本模块提供两层廉价检查，词汇沿用 RFC-0030 Pulse 的 ``source_evidence``
（freshness / snapshot_id / source_generation / reason），不另起一套：

1. ``index_identity``：廉价的索引内容身份（解析后的库路径、发布 generation、
   ``ast_index`` 行数与最新 ``indexed_at``、``edges`` 最大 rowid）。
   内存调用图绑定该身份，身份变化即重建。
2. ``relation_source_evidence``：只复核答案涉及的文件（O(k)）。答案为空
   （绝对否定）时，额外在限时预算内复核全部已索引文件的戳记，因为“确定的
   不存在”是最有害的错误答案；该路径不遍历目录树发现新文件。

两层都不能证明全仓源码与索引一致，因此通过时报告 ``unknown`` /
``SOURCE_REVALIDATION_SCOPED``，从不报告 ``fresh``；检测到差异时报告
``stale`` / ``SOURCE_INDEX_MISMATCH`` 并给出真正会刷新的 next_step。
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterable
from typing import Any

#: 与 Pulse 相同的稳定过期原因（api/pulse_evidence.py 的 _STALE_REASONS）。
STALE_REASON = "SOURCE_INDEX_MISMATCH"
#: 范围内文件均与索引一致，但范围外文件未复核，所以只能是 unknown。
SCOPED_REASON = "SOURCE_REVALIDATION_SCOPED"
#: 复核超出预算或索引不可读，沿用既有的范围未知原因。
UNKNOWN_REASON = "SOURCE_SCOPE_UNKNOWN"
#: 没有可用索引，沿用 Pulse 的缺失原因。
MISSING_REASON = "MISSING_INDEX"

#: 会真正刷新索引的命令（MCP 与 CLI 两个入口）。
REFRESH_COMMAND = (
    "`index action=cache mode=index` (CLI: `--ast-cache --ast-cache-mode index`)"
)

#: 绝对否定路径的整体复核期限；超出即为 unknown，不以部分结果冒充一致。
_ABSENCE_SCAN_DEADLINE_SECONDS = 0.5
#: next_step 中最多点名的变更文件数；找到这么多后即可停止复核。
_NAMED_FILES = 3
#: 单条 SQL IN 子句的参数上限，低于 SQLite 默认变量上限。
_SQL_CHUNK = 500


def index_identity(project_root: str) -> tuple[Any, ...]:
    """返回廉价且稳定的索引内容身份；重建索引或 generation 切换都会改变它。

    不能使用主库/WAL 的物理戳记：实测每次打开 ASTCache 都会向 WAL 写入
    （约 57 KB），物理戳记每次调用都变，内存图将每次重建。这里改用内容身份：
    发布 generation、``ast_index`` 的行数与最新 ``indexed_at``，以及
    ``edges`` 的最大 rowid。任何文件重新索引都会刷新 ``indexed_at``，
    增删文件会改变行数或最新时间，新写入的调用边会推高 rowid。
    三条查询都走聚合或主键，开销与一次 SQL 查询相当，不遍历源码树。
    """
    from ...cache.generation_routing import resolve_index_location

    try:
        location = resolve_index_location(project_root)
    except (OSError, ValueError) as exc:
        return ("unresolvable", type(exc).__name__, str(exc))
    generation = getattr(location.selector, "generation_id", None)
    database = location.path
    if not database.is_file():
        return (str(database), generation, "absent")
    try:
        # 与 is_ast_index_stale 相同：rw 打开拒绝创建空库，query_only 保证只读。
        conn = sqlite3.connect(
            database.absolute().as_uri() + "?mode=rw",
            uri=True,
            timeout=10,
            check_same_thread=False,
        )
        try:
            conn.execute("PRAGMA query_only=ON")
            files = conn.execute(
                "SELECT COUNT(*), COALESCE(MAX(indexed_at), '') FROM ast_index"
            ).fetchone()
            edges = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM edges").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return (str(database), generation, "unreadable", type(exc).__name__)
    return (str(database), generation, tuple(files), tuple(edges))


def _stamp(path: str) -> tuple[int, int] | None:
    """单个文件的 (mtime_ns, size)；文件不存在时为 None。"""
    try:
        info = os.stat(path)
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _evidence(freshness: str, reason: str) -> dict[str, Any]:
    """与 Pulse 相同的证据结构；nav 未经快照认证，因此身份字段为 None。"""
    return {
        "freshness": freshness,
        "snapshot_id": None,
        "source_generation": None,
        "reason": reason,
    }


def relation_source_evidence(
    cache: Any,
    project_root: str | None,
    files: Iterable[str],
    *,
    absence: bool,
) -> tuple[dict[str, Any], list[str]]:
    """复核答案所依据的索引戳记与磁盘源码，返回 (证据, 已变更文件)。"""
    if cache is None or not project_root:
        return _evidence("missing", MISSING_REASON), []
    deadline = time.monotonic() + _ABSENCE_SCAN_DEADLINE_SECONDS
    try:
        conn = cache.get_conn()
        scoped = _scoped_rows(conn, files)
        rows = _all_rows(conn) if absence else scoped
    except (sqlite3.Error, AttributeError, OSError):
        return _evidence("unknown", UNKNOWN_REASON), []
    changed = _changed_files(project_root, rows, deadline if absence else None)
    if changed is None:
        return _evidence("unknown", UNKNOWN_REASON), []
    if changed:
        return _evidence("stale", STALE_REASON), changed
    return _evidence("unknown", SCOPED_REASON), []


def _scoped_rows(conn: Any, files: Iterable[str]) -> list[tuple[str, int, int, str]]:
    """读取答案涉及文件的索引戳记；未入索引的文件不在复核范围内。"""
    wanted = sorted({path for path in files if path})
    rows: list[tuple[str, int, int, str]] = []
    for start in range(0, len(wanted), _SQL_CHUNK):
        chunk = wanted[start : start + _SQL_CHUNK]
        marks = ",".join("?" * len(chunk))
        rows.extend(
            (str(row[0]), int(row[1]), int(row[2]), str(row[3]))
            for row in conn.execute(
                "SELECT file_path, mtime_ns, file_size, content_hash "  # nosec B608
                f"FROM ast_index WHERE file_path IN ({marks})",
                chunk,
            )
        )
    return rows


def _all_rows(conn: Any) -> list[tuple[str, int, int, str]]:
    """读取全部已索引文件的戳记，供绝对否定路径的限时复核。"""
    return [
        (str(row[0]), int(row[1]), int(row[2]), str(row[3]))
        for row in conn.execute(
            "SELECT file_path, mtime_ns, file_size, content_hash FROM ast_index"
        )
    ]


def _changed_files(
    project_root: str,
    rows: list[tuple[str, int, int, str]],
    deadline: float | None,
) -> list[str] | None:
    """返回与索引不一致的文件（最多点名数个）；超出期限返回 None。

    大小不同即为变更；大小相同且 mtime 相同视为未变；仅 mtime 不同时比较
    内容摘要，与增量同步 ``file_changed`` 使用同一归一化摘要，避免 touch 误报。
    """
    from ...incremental_sync_support import file_content_hash

    changed: list[str] = []
    for rel_path, mtime_ns, size, content_hash in sorted(rows):
        if deadline is not None and time.monotonic() > deadline:
            return None
        abs_path = os.path.join(project_root, rel_path)
        disk = _stamp(abs_path)
        if disk is None or disk[1] != size:
            changed.append(rel_path)
        elif disk[0] != mtime_ns:
            try:
                if file_content_hash(abs_path) != content_hash:
                    changed.append(rel_path)
            except OSError:
                changed.append(rel_path)
        if len(changed) >= _NAMED_FILES:
            break
    return changed


def stale_next_step(changed: list[str]) -> str:
    """过期答案的可执行下一步：点名变更文件并给出真正刷新索引的命令。"""
    return (
        f"Source changed since the index was built: {', '.join(changed)}. "
        "This answer reflects the index, not the edited files. "
        f"Run {REFRESH_COMMAND} to refresh, then retry."
    )


def not_in_index_hint(
    func_name: str, evidence: dict[str, Any], *, indexed: bool = False
) -> str:
    """符号不在索引中时的提示；索引可能过期时不得归咎于拼写。

    ``indexed`` 为真表示符号有定义行（#1578）：此时零结果是关于调用边的事实，
    不得说成"不在索引中"并建议重建索引。索引过期的提示由 ``apply_source_evidence``
    统一前置，这里不重复。
    """
    if indexed:
        return (
            f"{func_name!r} is defined in the index and no resolved call edge "
            "reaches it."
        )
    if evidence.get("freshness") == "stale":
        return (
            f"Symbol {func_name!r} is not in the index, but the index is stale, "
            "so this is not evidence of absence."
        )
    return (
        f"Symbol {func_name!r} not in the index. If it was added or renamed "
        f"since the last index, run {REFRESH_COMMAND} and retry; otherwise "
        "check spelling or run --codegraph-navigate to browse."
    )


def name_only_hint(func_name: str, count: int) -> str:
    """#1578：同名入边无法绑定到目标时的提示——它们可能就是调用方。"""
    return (
        f"No resolved caller for {func_name!r}, but {count} call site(s) reach a "
        "same-named method through a receiver that could not be bound to it, so "
        "it may still be called. Read those call sites directly rather than "
        "treating this as absence."
    )


def relation_files(cache: Any, func_name: str, entries: list[dict]) -> list[str]:
    """答案涉及的文件：目标符号的声明文件加上每条关系所在的文件。

    路径统一为索引使用的 POSIX 形式；与索引行不匹配的路径不在复核范围内，
    结果只会更保守（unknown），不会因此宣称一致。
    """
    files = [str(entry.get("file") or "") for entry in entries]
    if cache is not None:
        files.extend(cache.symbol_declaring_files(func_name.rpartition(".")[2]) or ())
    return [path.replace("\\", "/") for path in files]


def apply_source_evidence(
    result: dict[str, Any], evidence: dict[str, Any], changed: list[str]
) -> None:
    """把证据写入响应；过期时把刷新步骤置于 next_step 与 agent_summary 之首。"""
    result["source_evidence"] = evidence
    if evidence.get("freshness") != "stale":
        return
    step = stale_next_step(changed)
    previous = result.get("next_step")
    result["next_step"] = f"{step} {previous}" if previous else step
    summary = result["agent_summary"]
    summary["next_step"] = result["next_step"]
    summary["summary_line"] = f"{summary['summary_line']} (index stale)"
