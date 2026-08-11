from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.cache.indexer import walk_and_partition
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
