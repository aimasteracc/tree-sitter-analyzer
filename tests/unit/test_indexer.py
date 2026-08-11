from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.indexer import walk_and_partition
from tree_sitter_analyzer.index_candidate_walker import walk_candidate_entries
from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest
from tree_sitter_analyzer.indexing_snapshot import build_index_candidate_snapshot


class _CacheRoot:
    def __init__(self, project_root: str) -> None:
        self.project_root = project_root


def test_language_scoped_partition_marks_other_language_skip_incomplete(
    tmp_path: Path,
) -> None:
    source = tmp_path / "client.js"
    source.write_text("const answer = 42;\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        language_filter="python",
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "javascript",
    )
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT PRIMARY KEY, content_hash TEXT, "
        "mtime_ns INTEGER, file_size INTEGER, extractor_version INTEGER)"
    )

    stats, candidates, count = walk_and_partition(
        _CacheRoot(str(tmp_path)),
        conn,
        max_files=10,
        force=False,
        activation_enabled=False,
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
        extractor_version=1,
        make_error_entry=lambda path, reason: {"file": path, "reason": reason},
        language_filter="python",
        candidate_snapshot=snapshot,
    )

    assert (stats["skipped"], stats["incomplete_skips"], candidates, count) == (
        1,
        1,
        [],
        1,
    )
    conn.close()


def test_force_with_root_scandir_error_preserves_every_persisted_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # GH-1253: incomplete discovery must not authorize the destructive force clear.
    source = tmp_path / "app.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    conn = cache.get_conn()
    tables = (
        "ast_index",
        "ast_symbol_rows",
        "edges",
        "ast_index_snapshot_manifest",
    )

    def persisted_rows() -> dict[str, list[tuple[object, ...]]]:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table}")]
            for table in tables
        }

    before = persisted_rows()

    def fail_root_scandir(_root_fd):
        raise OSError("root enumeration denied")

    monkeypatch.setattr(os, "scandir", fail_root_scandir)
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda root: walk_candidate_entries(
            root,
            excluded_dir_names=frozenset(),
            entry_budget=10,
            path_byte_budget=10_000,
            discovery_seconds=10.0,
            budget_error="INDEX_CANDIDATE_DISCOVERY_BUDGET",
        ),
        language_fn=lambda path: "python" if path.endswith(".py") else None,
    )

    result = cache.index_project(
        max_files=10,
        force=True,
        exclude_patterns=frozenset(),
        candidate_snapshot=snapshot,
    )

    assert (snapshot.errors, snapshot.discovery_error) == (
        1,
        "INDEX_CANDIDATE_DISCOVERY_ERROR",
    )
    assert (result["verdict"], result["errors"], result["indexed"]) == (
        "WARN",
        1,
        0,
    )
    assert persisted_rows() == before
    cache.close()
