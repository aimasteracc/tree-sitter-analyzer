from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.incremental_sync import IncrementalSync
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexSnapshotEntry,
    build_index_candidate_snapshot,
)


def _python_language(path: str) -> str | None:
    return "python" if path.endswith(".py") else None


def _snapshot(tmp_path, *paths) -> IndexCandidateSnapshot:
    return build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: tuple(str(path) for path in paths),
        language_fn=_python_language,
    )


def test_incremental_sync_preserves_snapshot_candidate_order(tmp_path):
    first = tmp_path / "z.py"
    second = tmp_path / "a.py"
    first.write_text("z = 1\n")
    second.write_text("a = 1\n")
    snapshot = _snapshot(tmp_path, first, second)
    cache = ASTCache(str(tmp_path))
    seen: list[str] = []
    original = cache.index_file

    def record(path: str, language: str | None = None):
        seen.append(os.path.basename(path))
        return original(path, language)

    try:
        with patch.object(cache, "index_file", side_effect=record):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.processed == 2
    assert seen == ["z.py", "a.py"]


def test_incremental_sync_reports_mutation_during_processing(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))
    original = cache.index_file
    callback_details: list[dict] = []

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("value = 200\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
                callback=callback_details.append,
            )
    finally:
        cache.close()

    assert result.changed_during_run == 1
    assert result.changed_during_run_files == ["app.py"]
    assert result.processed == 0
    assert result.details[-1]["reason"] == "file changed after candidate snapshot"
    assert callback_details[-1]["reason"] == "file changed after candidate snapshot"


def test_incremental_sync_rolls_back_mutation_during_processing(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("import os\n\ndef before():\n    return os.getcwd()\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))
    original = cache.index_file

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("def after():\n    return 2\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
        conn = cache.get_conn()
        counts = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE file_path = ?",
                ("app.py",),
            ).fetchone()[0]
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


def test_incremental_sync_detects_late_mutation_without_callback(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))
    original = cache.index_file

    def index_then_mutate(file_path: str, language: str | None = None):
        indexed = original(file_path, language)
        path.write_text("value = 200\n")
        return indexed

    try:
        with patch.object(cache, "index_file", side_effect=index_then_mutate):
            result = IncrementalSync(cache).sync(
                max_files=10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()

    assert result.changed_during_run_files == ["app.py"]


def test_incremental_sync_reports_preexisting_snapshot_change_to_callback(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    path.unlink()
    cache = ASTCache(str(tmp_path))
    callback_details: list[dict] = []

    try:
        result = IncrementalSync(cache).sync(
            max_files=10,
            candidate_snapshot=snapshot,
            callback=callback_details.append,
        )
    finally:
        cache.close()

    assert result.changed_during_run == 1
    assert result.processed == 0
    assert callback_details == [
        {
            "file": "app.py",
            "considered": "skipped",
            "action": "skipped",
            "status": "skipped",
            "reason": "file disappeared after candidate snapshot",
        }
    ]


def test_incremental_sync_rejects_snapshot_root_mismatch(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    other = tmp_path / "other"
    other.mkdir()
    other_cache = ASTCache(str(other))

    try:
        with pytest.raises(ValueError, match="different project root"):
            IncrementalSync(other_cache)._scan_disk_files(
                10,
                candidate_snapshot=snapshot,
            )
    finally:
        other_cache.close()


def test_incremental_sync_rejects_snapshot_limit_mismatch(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    snapshot = _snapshot(tmp_path, path)
    cache = ASTCache(str(tmp_path))

    try:
        with pytest.raises(ValueError, match="different max_files"):
            IncrementalSync(cache)._scan_disk_files(
                11,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()


def test_incremental_sync_rejects_selected_entry_without_fingerprint(tmp_path):
    snapshot = IndexCandidateSnapshot(
        project_root=os.path.abspath(tmp_path),
        max_files=10,
        entries=(
            IndexSnapshotEntry(
                abs_path=str(tmp_path / "bad.py"),
                rel_path="bad.py",
                language="python",
                decision="selected",
            ),
        ),
        present_paths=frozenset({"bad.py"}),
        discovered=1,
        selected=1,
        excluded=0,
        skipped=0,
        errors=0,
        limited=0,
    )
    cache = ASTCache(str(tmp_path))

    try:
        with pytest.raises(ValueError, match="lacks fingerprint"):
            IncrementalSync(cache)._scan_disk_files(
                10,
                candidate_snapshot=snapshot,
            )
    finally:
        cache.close()
