from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

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


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_force_with_renamed_directory_swap_preserves_persisted_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # PR #1253 thread 3758928326: a regular-directory swap is incomplete discovery.
    import tree_sitter_analyzer.index_candidate_walker as walker

    package = tmp_path / "pkg"
    package.mkdir()
    source = package / "app.py"
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
    real_open = walker.os.open
    swapped = False

    def swap_before_child_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "pkg" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            package.rename(tmp_path / "original-pkg")
            package.mkdir()
        return real_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(walker.os, "open", swap_before_child_open)
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

    assert (swapped, snapshot.errors, snapshot.discovery_error) == (
        True,
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


def test_force_without_materialized_evidence_preserves_existing_cache(
    tmp_path: Path,
) -> None:
    # PR #1253 thread 3759852177: live-path evidence cannot authorize a clear.
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    before = [tuple(row) for row in cache.get_conn().execute("SELECT * FROM ast_index")]
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )

    result = cache.index_project(
        max_files=10,
        force=True,
        exclude_patterns=frozenset(),
        candidate_snapshot=snapshot,
    )

    after = [tuple(row) for row in cache.get_conn().execute("SELECT * FROM ast_index")]
    assert (result["verdict"], result["indexed"], after) == ("WARN", 0, before)
    cache.close()


def test_incomplete_cached_noop_clears_current_global_marker(tmp_path: Path) -> None:
    # PR #1253 thread 3760046643: no-op scope gaps still revoke certification.
    source = tmp_path / "client.js"
    source.write_text("const value = 1;\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    initial = cache.index_project(max_files=10)
    assert (initial["errors"], cache.call_graph_built()) == (0, True)

    result = cache.index_project(max_files=10, language_filter="python")

    assert (
        result["indexed"],
        result["incomplete_skips"],
        result["verdict"],
        cache.call_graph_built(),
    ) == (0, 1, "WARN", False)
    cache.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_owned_truncated_force_materialization_is_cleaned_before_abort(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3759852177: failed authorization cleans private bytes.
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    (tmp_path / "a.py").write_text("a = 1\n")
    (tmp_path / "b.py").write_text("b = 1\n")
    cache = ASTCache(str(tmp_path))
    created: list[str] = []
    real_mkdtemp = materialization.tempfile.mkdtemp

    def remember_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        created.append(root)
        return root

    monkeypatch.setattr(materialization.tempfile, "mkdtemp", remember_root)
    result = cache.index_project(max_files=1, force=True)

    assert (result["verdict"], len(created), os.path.exists(created[0])) == (
        "WARN",
        1,
        False,
    )
    cache.close()
