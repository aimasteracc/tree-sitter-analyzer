"""#1672：引用扫描命中的文件是否已与索引不一致。

dogfood 第 8 轮：刷新前，在既不是声明文件、也不是既有调用方文件的已索引文件里新增
一次调用。``relation_source_evidence`` 只复核答案涉及的文件（O(k)），看不到它；
非调用引用扫描（#1593）能看到这一行，却把它报告为 ``NON_CALL_REFERENCES``——
新增的调用还没有调用边，处于调用位置也不会被跳过。同一次编辑，0 调用方的目标
（绝对否定路径复核全部戳记）得到 ``stale`` / ``SOURCE_INDEX_MISMATCH``，有调用方
的目标却得到另一个诊断。

扫描已经为每个命中文件取得了字节与 stat 证据（#1651 的 ``FILE_CACHE`` 本就按
stat 键控），这里只把命中引用的文件与它们的索引戳记比对：一次按主键的 SQL 查询，
不再 stat、不遍历全树。比对规则与 ``relation_freshness._changed_files`` 相同：
大小不同即变更；大小与 mtime 都相同视为未变；仅 mtime 不同时比较归一化摘要，
避免 touch 误报。
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from typing import Any

from .evidence_file_cache import StatKey
from .relation_freshness import _scoped_rows


def stale_reference_files(
    cache: Any,
    project_root: str,
    sites: list[dict[str, Any]],
    stamps: Mapping[str, StatKey | None],
) -> list[str] | None:
    """命中引用、且磁盘内容已与索引戳记不一致的已索引文件（有序）。

    ``stamps`` 为扫描读取各文件时的 stat 证据；缺失或为 ``None``（读取期间被改写）
    时比较摘要。未入索引的文件（配置文件等）不在比对范围内。索引不可读为 ``None``。
    """
    files = sorted({str(site["file"]) for site in sites})
    if not files:
        return []
    try:
        rows = _scoped_rows(cache.get_conn(), files)
    except (sqlite3.Error, AttributeError, OSError):
        return None
    from ...cache import stat_evidence

    evidence = stat_evidence.load(project_root)
    stale = [
        rel_path
        for rel_path, mtime_ns, size, content_hash in rows
        if _differs(
            os.path.join(project_root, rel_path),
            stamps.get(rel_path),
            (mtime_ns, size, content_hash),
            evidence=evidence,
            rel_path=rel_path,
        )
    ]
    return sorted(stale)


def _differs(
    abs_path: str,
    stamp: StatKey | None,
    indexed: tuple[int, int, str],
    *,
    evidence: Mapping[str, tuple[int, int, str]] | None = None,
    rel_path: str = "",
) -> bool:
    from ...cache import stat_evidence
    from ...incremental_sync_support import file_content_hash

    mtime_ns, size, content_hash = indexed
    if stamp is not None:
        if stamp[0] != size:
            return True
        if stamp[1] == mtime_ns:
            return False
        # #1707：只有 mtime 变化、已在刷新时核对过内容的文件，由 stat 证据作证。
        if evidence and stat_evidence.vouches(
            evidence, rel_path, (stamp[1], stamp[0]), (size, content_hash)
        ):
            return False
    try:
        return file_content_hash(abs_path) != content_hash
    except OSError:
        return True
