"""Small data and scan helpers for incremental cache reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyncResult:
    """Result of an incremental sync operation."""

    scanned: int = 0
    new_files: int = 0
    updated_files: int = 0
    deleted_files: int = 0
    unchanged_files: int = 0
    errors: int = 0
    backfill_errors: int = 0
    processed: int = 0
    changed_during_run: int = 0
    changed_during_run_files: list[str] = field(default_factory=list)
    truncated_by_max_files: bool = False
    scope_complete: bool = True
    synapse_resolved: int = 0
    manifest_certification_failed: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)
    #: 默认库的同步是否发布了新版本；``None`` 表示原地同步（无发布概念）。
    published: bool | None = None
    #: 未发布的原因码（如 ``INDEX_UNCHANGED``，#1671）。
    publication_reason: str | None = None
    #: #1696：本轮回填是按依赖界定的范围还是全量，以及原因与规模。
    backfill_scope: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        publication: dict[str, Any] = {}
        if self.backfill_scope is not None:
            publication["backfill_scope"] = self.backfill_scope
        if self.published is not None:
            publication["published"] = self.published
        if self.publication_reason is not None:
            publication["publication_reason"] = self.publication_reason
        return {
            **publication,
            "mode_used": "incremental",
            "scanned": self.scanned,
            "new_files": self.new_files,
            "updated_files": self.updated_files,
            "deleted_files": self.deleted_files,
            "unchanged_files": self.unchanged_files,
            "errors": self.errors,
            "backfill_errors": self.backfill_errors,
            "processed": self.processed,
            "changed_during_run": self.changed_during_run,
            "changed_during_run_files": self.changed_during_run_files,
            "truncated_by_max_files": self.truncated_by_max_files,
            "completeness": "complete" if self.scope_complete else "incomplete",
            "synapse_resolved": self.synapse_resolved,
            "manifest_certification_failed": self.manifest_certification_failed,
            "details": self.details,
        }


def file_content_hash(path: str) -> str:
    """使用与索引写入端相同的编码检测及换行归一化。"""
    from ._bounded_read import read_at_most
    from .indexing_snapshot import _INDEX_SOURCE_BYTE_LIMIT, decode_index_source

    with open(path, "rb") as source:
        data = read_at_most(source, _INDEX_SOURCE_BYTE_LIMIT)
    if len(data) > _INDEX_SOURCE_BYTE_LIMIT:
        raise OSError("source exceeds indexing byte limit")
    return hashlib.sha256(decode_index_source(data).encode("utf-8")).hexdigest()


def file_changed(disk_info: dict[str, Any], indexed_info: dict[str, Any]) -> bool:
    """比较冻结摘要；缺少摘要时必须重读，等长等 mtime 不能证明内容相同。"""
    if disk_info["file_size"] != indexed_info["file_size"]:
        return True
    candidate_hash = disk_info.get("content_hash")
    if candidate_hash:
        return str(candidate_hash) != str(indexed_info["content_hash"])
    try:
        return file_content_hash(
            disk_info.get("source_path", disk_info["abs_path"])
        ) != str(indexed_info["content_hash"])
    except OSError:
        return True


def get_changes(
    cache: Any,
    changed_fn: Callable[[dict[str, Any], dict[str, Any], str], bool],
    walk_fn: Callable[[str], Iterable[str]],
) -> dict[str, list[str]]:
    """Scan the live tree and classify paths without modifying the cache."""
    conn = cache.get_conn()
    indexed_rows = {
        row["file_path"]: {
            "content_hash": row["content_hash"],
            "mtime_ns": row["mtime_ns"],
            "file_size": row["file_size"],
        }
        for row in conn.execute(
            "SELECT file_path, content_hash, mtime_ns, file_size FROM ast_index"
        ).fetchall()
    }
    disk_files: dict[str, dict[str, Any]] = {}
    for abs_path in walk_fn(cache.project_root):
        rel = os.path.relpath(abs_path, cache.project_root)
        if os.name == "nt":
            rel = rel.replace("\\", "/")
        try:
            source_stat = os.stat(abs_path)
        except OSError:
            continue
        disk_files[rel] = {
            "abs_path": abs_path,
            "mtime_ns": int(source_stat.st_mtime_ns),
            "file_size": source_stat.st_size,
        }

    indexed_set = set(indexed_rows)
    disk_set = set(disk_files)
    changes: dict[str, list[str]] = {
        "new": sorted(disk_set - indexed_set),
        "deleted": sorted(indexed_set - disk_set),
        "modified": [],
    }
    for rel in sorted(indexed_set & disk_set):
        if changed_fn(disk_files[rel], indexed_rows[rel], rel):
            changes["modified"].append(rel)
    return changes


#: 本轮成功处理、应带认证时间的动作。
_CERTIFIED_ACTIONS = ("new", "updated", "unchanged")


def stamp_certified_at(
    conn: Any, action_by_file: Mapping[str, str], epoch: int
) -> None:
    """为本轮成功处理的文件盖认证时间（Phase B-3，#1718 / RFC-0039 step 0）。

    新增与更新的文件盖上 ``epoch``；未变文件只在尚未认证（NULL）时补盖，已有的
    值保持不变。读者只检查 ``certified_at`` 是否为 NULL，时间值本身没有读者；
    给未变文件重写时间会让每次 1 文件刷新改写全部 ``ast_index`` 行。仍是单条
    语句（与原先相同的写入形态），写入失败向上抛出，由调用方走既有的失败闭合路径。
    """
    paths = [p for p, a in action_by_file.items() if a in _CERTIFIED_ACTIONS]
    if not paths:
        return
    changed = [p for p in paths if action_by_file[p] != "unchanged"]
    conn.execute(
        "UPDATE ast_index SET certified_at = ? "  # nosec B608 — 只拼接占位符
        f"WHERE file_path IN ({','.join('?' * len(paths))}) "
        "AND (certified_at IS NULL OR file_path IN (SELECT value FROM json_each(?)))",
        [epoch, *paths, json.dumps(changed, ensure_ascii=False)],
    )
