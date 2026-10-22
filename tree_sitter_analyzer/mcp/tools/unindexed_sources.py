"""绝对否定的文件集合证据：索引之后新增的同语言源码可能就是调用方（#1607）。

dogfood 第 4 轮实测：新建一个尚未入索引、两次直接调用某方法的 ``.py`` 文件后，
``nav callers`` 仍答 ``complete, 0``。``relation_freshness`` 只复核已入索引的文件，
从不发现新文件。

本模块以与全量索引相同的发现规则（``walk_index_candidate_entries``：排除目录、
点目录、``.gitignore``，以及索引清单记录的 exclude 模式）列出目录，找出目标
语言中尚未入索引的源码文件。墙钟预算沿用 ``discovery_budget``（#1597/#1604）的
唯一公式；超出预算或列表失败时返回 None——答案只能是 unknown，不得假定没有新文件。

#1624：同一次遍历还列出需要做非调用引用扫描的配置 / 脚本文件（另加
``.github``，点目录本身仍被跳过），避免为它们再走一遍目录。
#1633：JSON（不超过大小上限）、Notebook 与模板文件同样在这次遍历中列出。
#1738：额外根目录不在索引的发现范围内，其中的源码只做文本引用扫描，从不计入
未入索引源码——建议的刷新永远不会入库它们，否则答案再也不能 ``complete``。
"""

from __future__ import annotations

import fnmatch
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .project_walk_cache import WALK_CACHE

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


#: #1624：点目录照常跳过，但 CI 工作流目录会点名测试与脚本，须一并列出。
_EXTRA_ROOTS = (".github",)


@dataclass(frozen=True)
class ProjectFiles:
    """一次目录遍历的结果：语言匹配的未入索引源码，以及需扫描的配置文件。"""

    unindexed: list[str]
    config: list[str]


def unindexed_source_files(
    cache: Any, project_root: str, languages: frozenset[str]
) -> list[str] | None:
    """``languages`` 中未入索引的源码文件（相对 POSIX 路径、有序）；失败为 None。"""
    if not languages:
        return []
    files = project_files(cache, project_root, languages)
    return None if files is None else files.unindexed


def project_files(
    cache: Any, project_root: str, languages: frozenset[str]
) -> ProjectFiles | None:
    """同一次遍历同时找出未入索引的源码与配置文件（#1607、#1624）；失败为 None。"""
    from ...constants import EXCLUDE_DIRS
    from ...index_candidate_walker import (
        CandidateDiscoveryBudgetExceeded,
        CandidateDiscoveryError,
        walk_candidate_entries,
    )
    from .absence_text_kinds import wanted_as

    try:
        conn = cache.get_conn()
        indexed = {
            str(row[0]) for row in conn.execute("SELECT file_path FROM ast_index")
        }
    except (sqlite3.Error, AttributeError):
        return None
    excludes = effective_excludes(conn)
    unindexed: list[str] = []
    config: list[str] = []
    starts = [""] + [
        extra
        for extra in _EXTRA_ROOTS
        if os.path.isdir(os.path.join(project_root, extra))
    ]
    excluded_dir_names = frozenset(EXCLUDE_DIRS)
    entry_budget = _ENTRY_BUDGET
    path_byte_budget = _PATH_BYTE_BUDGET
    try:
        for start in starts:

            def walk(visited: list[str], start: str = start) -> Iterable[str]:
                return walk_candidate_entries(
                    project_root,
                    excluded_dir_names=excluded_dir_names,
                    entry_budget=entry_budget,
                    path_byte_budget=path_byte_budget,
                    discovery_seconds=None,
                    budget_error=UNCHECKED_REASON,
                    start_relative=start,
                    visited_dirs=visited,
                )

            # dogfood 第 7 轮：遍历按目录 / 规则文件的 lstat 证据记忆，证据变即重走。
            walked = WALK_CACHE.walk(
                project_root,
                (excluded_dir_names, entry_budget, path_byte_budget),
                start,
                walk,
            )
            for abs_path, rel_path, ext_language, text_kind in _classified(
                project_root, walked, excludes
            ):
                source = ext_language in languages
                if not source and not wanted_as(abs_path, text_kind):
                    continue
                if not source:
                    config.append(rel_path)
                elif start:
                    # #1738：额外根目录在索引的发现规则之外，其中源码永不入库，
                    # 不是“索引之后新增”；仍按文本扫描非调用引用（#1624）。
                    if rel_path not in indexed:
                        config.append(rel_path)
                elif rel_path not in indexed:
                    unindexed.append(rel_path)
    except (CandidateDiscoveryBudgetExceeded, CandidateDiscoveryError, OSError):
        return None
    return ProjectFiles(sorted(unindexed), sorted(config))


#: 一次遍历结果的路径分类：(abs_path, rel_path, 扩展名语言, 文本扫描语言)。
_Classified = tuple[tuple[str, str, str | None, str | None], ...]
#: ``_classified`` 的记忆：键含遍历结果对象本身，遍历重走即换新对象。
_CLASSIFIED_MEMO: dict[
    tuple[str, int, frozenset[str]], tuple[tuple[str, ...], _Classified]
] = {}
_CLASSIFIED_MEMO_MAX = 8


def _classified(
    project_root: str, walked: tuple[str, ...], excludes: frozenset[str]
) -> _Classified:
    """遍历结果中未被 exclude 模式排除的路径及其只取决于路径字符串的分类。

    相对路径、扩展名语言、文本扫描语言与 exclude 匹配都是路径字符串的纯函数，
    因此与遍历结果一起记忆；JSON 大小等磁盘状态仍由调用方每次读取。
    """
    from ...project_graph import _language_from_ext
    from .absence_text_kinds import text_language

    key = (project_root, id(walked), excludes)
    cached = _CLASSIFIED_MEMO.get(key)
    if cached is not None and cached[0] is walked:
        return cached[1]
    rows: list[tuple[str, str, str | None, str | None]] = []
    for abs_path in walked:
        rel_path = os.path.relpath(abs_path, project_root).replace("\\", "/")
        if any(fnmatch.fnmatch(rel_path, pattern) for pattern in excludes):
            continue
        rows.append(
            (abs_path, rel_path, _language_from_ext(abs_path), text_language(abs_path))
        )
    classified = tuple(rows)
    if len(_CLASSIFIED_MEMO) >= _CLASSIFIED_MEMO_MAX:
        _CLASSIFIED_MEMO.pop(next(iter(_CLASSIFIED_MEMO)))
    _CLASSIFIED_MEMO[key] = (walked, classified)
    return classified


def effective_excludes(conn: Any) -> frozenset[str]:
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
