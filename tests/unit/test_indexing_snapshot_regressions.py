from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.callgraph_state import clear_call_graph_built
from tree_sitter_analyzer.cache.indexer import _clear_full_rebuild_rows
from tree_sitter_analyzer.cache.write import invalidate_file_rows
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    build_index_candidate_snapshot,
)


def _python_language(path: str) -> str | None:
    return "python" if path.endswith(".py") else None


def _snapshot(tmp_path, path) -> IndexCandidateSnapshot:
    return build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
    )


def test_force_index_rejects_wrong_root_before_clearing_cache(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    before = cache.lookup(str(path))
    snapshot = replace(
        _snapshot(tmp_path, path),
        project_root=os.path.abspath(tmp_path / "other"),
    )

    try:
        with pytest.raises(ValueError, match="different project root"):
            cache.index_project(
                max_files=10,
                force=True,
                candidate_snapshot=snapshot,
            )
        row = cache.lookup(str(path))
    finally:
        cache.close()

    assert row == before


def test_force_index_rejects_wrong_limit_before_clearing_cache(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    before = cache.lookup(str(path))
    snapshot = _snapshot(tmp_path, path)

    try:
        with pytest.raises(ValueError, match="different max_files"):
            cache.index_project(
                max_files=11,
                force=True,
                candidate_snapshot=snapshot,
            )
        row = cache.lookup(str(path))
    finally:
        cache.close()

    assert row == before


def test_force_index_rejects_missing_metadata_before_clearing_cache(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    before = cache.lookup(str(path))
    snapshot = _snapshot(tmp_path, path)
    malformed = replace(
        snapshot,
        entries=(replace(snapshot.selected_entries[0], fingerprint=None),),
    )

    try:
        with pytest.raises(ValueError, match="lacks metadata"):
            cache.index_project(
                max_files=10,
                force=True,
                candidate_snapshot=malformed,
            )
        row = cache.lookup(str(path))
    finally:
        cache.close()

    assert row == before


def test_force_index_discards_all_stale_derived_rows(tmp_path):
    from tree_sitter_analyzer.cache import extraction

    path = tmp_path / "app.py"
    path.write_text("import os\n\ndef stale():\n    return os.getcwd()\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)
    real_worker = extraction._worker_index_file

    def worker_then_mutate(args):
        result = real_worker(args)
        path.write_text("def changed():\n    return 2\n")
        return result

    try:
        with patch.object(
            extraction,
            "_worker_index_file",
            side_effect=worker_then_mutate,
        ):
            cache.index_project(
                max_files=10,
                force=True,
                workers=0,
                exclude_patterns=frozenset(),
                candidate_snapshot=snapshot,
            )
        conn = cache.get_conn()
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "ast_index",
                "ast_symbol_rows",
                "ast_symbols_fts",
                "ast_imports",
                "ast_symbol_activation",
                "edges",
            )
        }
    finally:
        cache.close()

    assert counts == {
        "ast_index": 0,
        "ast_symbol_rows": 0,
        "ast_symbols_fts": 0,
        "ast_imports": 0,
        "ast_symbol_activation": 0,
        "edges": 0,
    }


def test_cached_snapshot_mutation_does_not_stamp_graph_complete(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)
    clear_call_graph_built(cache.get_conn())

    def mutate_after_partition(_workers, _candidates):
        path.write_text("value = 200\n")
        return 0

    try:
        with patch.object(
            cache,
            "_resolve_worker_count",
            side_effect=mutate_after_partition,
        ):
            cache.index_project(
                max_files=10,
                candidate_snapshot=snapshot,
            )
        built = (
            cache.get_conn()
            .execute("SELECT built FROM ast_call_graph_state WHERE id = 1")
            .fetchone()[0]
        )
    finally:
        cache.close()

    assert built == 0


def test_full_rebuild_clear_tolerates_legacy_primary_only_schema():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py')")

    _clear_full_rebuild_rows(SimpleNamespace(fts5_available=False), conn)

    assert conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0] == 0
    conn.close()


def test_file_invalidation_tolerates_legacy_primary_only_schema():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py')")

    removed = invalidate_file_rows(conn, "app.py", False)

    assert removed is True
    conn.close()
