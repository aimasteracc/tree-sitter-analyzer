#!/usr/bin/env python3
"""
Incremental Sync — File watcher + content hash comparison for AST cache.

Detects changed files via mtime + content-hash comparison and re-indexes
only what actually changed. Like CodeGraph's incremental sync, avoids
full project re-parses on every analysis run.

Key features:
- Content-hash comparison (SHA-256) to skip false-positive mtime changes
- Detects new files, modified files, and deleted files
- Prunes stale index entries for deleted/moved files
- Integration with ASTCache for automatic re-indexing
"""

import hashlib
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .ast_cache import _EXT_TO_LANG, _walk_source_files

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of an incremental sync operation."""

    scanned: int = 0
    new_files: int = 0
    updated_files: int = 0
    deleted_files: int = 0
    unchanged_files: int = 0
    errors: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "new_files": self.new_files,
            "updated_files": self.updated_files,
            "deleted_files": self.deleted_files,
            "unchanged_files": self.unchanged_files,
            "errors": self.errors,
            "details": self.details,
        }


def _file_content_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class IncrementalSync:
    """
    Incremental sync engine for ASTCache.

    Compares the on-disk file tree against the SQLite index to determine
    what needs re-parsing:
    - New files: present on disk but not in index → index them
    - Modified files: content hash differs → re-index them
    - Deleted files: in index but not on disk → prune from index
    - Unchanged files: hash matches → skip
    """

    def __init__(self, cache: Any) -> None:
        self._cache = cache

    def sync(
        self,
        max_files: int = 5000,
        callback: Any | None = None,
    ) -> SyncResult:
        result = SyncResult()
        conn = self._cache._get_conn()

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
        count = 0
        for abs_path in _walk_source_files(self._cache.project_root):
            if count >= max_files:
                break
            rel = os.path.relpath(abs_path, self._cache.project_root)
            try:
                stat = os.stat(abs_path)
                disk_files[rel] = {
                    "abs_path": abs_path,
                    "mtime_ns": int(stat.st_mtime_ns),
                    "file_size": stat.st_size,
                }
            except OSError:
                continue
            count += 1

        result.scanned = len(disk_files)

        indexed_set = set(indexed_rows.keys())
        disk_set = set(disk_files.keys())

        deleted_paths = indexed_set - disk_set
        for rel in deleted_paths:
            ext = os.path.splitext(rel)[1].lower()
            if ext not in _EXT_TO_LANG:
                continue
            abs_del = os.path.join(self._cache.project_root, rel)
            self._cache.invalidate(abs_del)
            result.deleted_files += 1
            detail = {"file": rel, "action": "deleted"}
            result.details.append(detail)
            if callback:
                callback(detail)

        for rel, info in sorted(disk_files.items()):
            indexed_info = indexed_rows.get(rel)
            if indexed_info is None:
                detail = self._index_new_file(rel, info["abs_path"], conn)
                result.new_files += 1
            elif self._file_changed(info, indexed_info, rel):
                detail = self._reindex_modified(rel, info["abs_path"], conn)
                result.updated_files += 1
            else:
                result.unchanged_files += 1
                continue
            if detail.get("status") == "error":
                result.errors += 1
            result.details.append(detail)
            if callback:
                callback(detail)

        conn.commit()
        return result

    def _file_changed(
        self,
        disk_info: dict[str, Any],
        indexed_info: dict[str, Any],
        rel_path: str,
    ) -> bool:
        if disk_info["file_size"] != indexed_info["file_size"]:
            return True
        if disk_info["mtime_ns"] != indexed_info["mtime_ns"]:
            try:
                current_hash = _file_content_hash(disk_info["abs_path"])
                return current_hash != indexed_info["content_hash"]
            except OSError:
                return True
        return False

    def _index_new_file(
        self,
        rel_path: str,
        abs_path: str,
        conn: sqlite3.Connection,
    ) -> dict[str, Any]:
        index_result = self._cache.index_file(abs_path)
        return {
            "file": rel_path,
            "action": "indexed",
            "status": index_result.get("status", "unknown"),
        }

    def _reindex_modified(
        self,
        rel_path: str,
        abs_path: str,
        conn: sqlite3.Connection,
    ) -> dict[str, Any]:
        self._cache.invalidate(abs_path)
        index_result = self._cache.index_file(abs_path)
        return {
            "file": rel_path,
            "action": "updated",
            "status": index_result.get("status", "unknown"),
        }

    def get_changes(self) -> dict[str, list[str]]:
        """
        Quick scan that returns lists of changed file paths without re-indexing.

        Returns dict with keys: 'new', 'modified', 'deleted' — each a list of
        relative file paths.
        """
        conn = self._cache._get_conn()
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
        for abs_path in _walk_source_files(self._cache.project_root):
            rel = os.path.relpath(abs_path, self._cache.project_root)
            try:
                stat = os.stat(abs_path)
                disk_files[rel] = {
                    "abs_path": abs_path,
                    "mtime_ns": int(stat.st_mtime_ns),
                    "file_size": stat.st_size,
                }
            except OSError:
                continue

        indexed_set = set(indexed_rows.keys())
        disk_set = set(disk_files.keys())

        changes: dict[str, list[str]] = {
            "new": sorted(disk_set - indexed_set),
            "deleted": sorted(indexed_set - disk_set),
            "modified": [],
        }

        for rel in sorted(indexed_set & disk_set):
            if self._file_changed(disk_files[rel], indexed_rows[rel], rel):
                changes["modified"].append(rel)

        return changes
