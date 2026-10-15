"""绝对否定的文件集合证据：索引之后新增的同语言源码可能就是调用方（#1607）。

dogfood 第 4 轮实测：新建一个尚未入索引、两次直接调用某方法的 ``.py`` 文件后，
``nav callers`` 仍答 ``complete, 0``。``relation_freshness`` 只复核已入索引的文件，
从不发现新文件。

本模块以与全量索引相同的发现规则（``walk_index_candidate_entries``：排除目录、
点目录、``.gitignore``，以及索引清单记录的 exclude 模式）列出目录，找出目标
语言中尚未入索引的源码文件。墙钟预算沿用 ``discovery_budget``（#1597/#1604）的
唯一公式；超出预算或列表失败时返回 None——答案只能是 unknown，不得假定没有新文件。
"""

from __future__ import annotations

import fnmatch
import os
import sqlite3
from typing import Any

#: 存在尚未入索引的同语言源码文件。
UNINDEXED_REASON = "UNINDEXED_SOURCE_FILES"
#: 无法在预算内确认是否存在未入索引的同语言源码文件。
UNCHECKED_REASON = "UNINDEXED_SOURCE_UNCHECKED"

#: 目录项预算，与全量索引的候选发现一致。
_ENTRY_BUDGET = 100_000
#: 路径字节预算，与全量索引的候选发现一致。
_PATH_BYTE_BUDGET = 16 * 1024 * 1024
#: 响应中点名的新文件上限；总数始终并列给出。
FILES_CAP = 20
#: next_step 中内联点名的新文件数。
_FILES_NAMED = 3


def unindexed_source_files(
    cache: Any, project_root: str, languages: frozenset[str]
) -> list[str] | None:
    """``languages`` 中未入索引的源码文件（相对 POSIX 路径、有序）；失败为 None。"""
    if not languages:
        return []
    from ...constants import EXCLUDE_DIRS
    from ...index_candidate_walker import (
        CandidateDiscoveryBudgetExceeded,
        CandidateDiscoveryError,
        walk_candidate_entries,
    )
    from ...project_graph import _language_from_ext

    try:
        conn = cache.get_conn()
        indexed = {
            str(row[0]) for row in conn.execute("SELECT file_path FROM ast_index")
        }
    except (sqlite3.Error, AttributeError):
        return None
    excludes = _effective_excludes(conn)
    found: list[str] = []
    try:
        for abs_path in walk_candidate_entries(
            project_root,
            excluded_dir_names=frozenset(EXCLUDE_DIRS),
            entry_budget=_ENTRY_BUDGET,
            path_byte_budget=_PATH_BYTE_BUDGET,
            discovery_seconds=None,
            budget_error=UNCHECKED_REASON,
        ):
            if _language_from_ext(abs_path) not in languages:
                continue
            rel_path = os.path.relpath(abs_path, project_root).replace("\\", "/")
            if rel_path in indexed or any(
                fnmatch.fnmatch(rel_path, pattern) for pattern in excludes
            ):
                continue
            found.append(rel_path)
    except (CandidateDiscoveryBudgetExceeded, CandidateDiscoveryError, OSError):
        return None
    return sorted(found)


def _effective_excludes(conn: Any) -> frozenset[str]:
    """索引清单记录的 exclude 模式；清单缺失或无效时用默认模式（只会更保守）。"""
    from ...index_source_scope import (
        make_source_scope_descriptor,
        parse_source_scope_descriptor,
    )

    try:
        row = conn.execute(
            "SELECT source_scope_descriptor FROM ast_index_snapshot_manifest "
            "WHERE singleton = 1"
        ).fetchone()
        if row is not None and row[0]:
            return parse_source_scope_descriptor(str(row[0])).effective_excludes
    except (sqlite3.Error, ValueError):
        pass
    return make_source_scope_descriptor().effective_excludes


def unindexed_hint(func_name: str, languages: frozenset[str], files: list[str]) -> str:
    """点名新文件并给出真正会把它们入索引的命令。"""
    from .relation_freshness import REFRESH_COMMAND

    named = files[:_FILES_NAMED]
    listing = ", ".join(named)
    if len(files) > len(named):
        listing += f" and {len(files) - len(named)} more"
    return (
        f"No resolved caller for {func_name!r}, but {len(files)} "
        f"{'/'.join(sorted(languages))} source file(s) were added since the last "
        f"index and were not checked: {listing}. Run {REFRESH_COMMAND} to index "
        "them, then retry."
    )


def unchecked_hint(func_name: str) -> str:
    """目录列表超出预算时的提示。"""
    from .relation_freshness import REFRESH_COMMAND

    return (
        f"No resolved caller for {func_name!r}, but whether source files were "
        "added since the last index could not be checked within budget, so this "
        f"is not evidence of absence. Run {REFRESH_COMMAND}, then retry."
    )
