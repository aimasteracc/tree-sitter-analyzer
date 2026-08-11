"""Small data and scan helpers for incremental cache reconciliation."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterable
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
    processed: int = 0
    changed_during_run: int = 0
    changed_during_run_files: list[str] = field(default_factory=list)
    truncated_by_max_files: bool = False
    synapse_resolved: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode_used": "incremental",
            "scanned": self.scanned,
            "new_files": self.new_files,
            "updated_files": self.updated_files,
            "deleted_files": self.deleted_files,
            "unchanged_files": self.unchanged_files,
            "errors": self.errors,
            "processed": self.processed,
            "changed_during_run": self.changed_during_run,
            "changed_during_run_files": self.changed_during_run_files,
            "truncated_by_max_files": self.truncated_by_max_files,
            "synapse_resolved": self.synapse_resolved,
            "details": self.details,
        }


def file_content_hash(path: str) -> str:
    """Return the SHA-256 digest of one source file."""
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_changed(disk_info: dict[str, Any], indexed_info: dict[str, Any]) -> bool:
    """Compare live file metadata and content with a cached row."""
    if disk_info["file_size"] != indexed_info["file_size"]:
        return True
    if disk_info["mtime_ns"] != indexed_info["mtime_ns"]:
        try:
            return file_content_hash(disk_info["abs_path"]) != str(
                indexed_info["content_hash"]
            )
        except OSError:
            return True
    return False


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
