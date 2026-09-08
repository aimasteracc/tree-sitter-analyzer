"""#1376：test_ast_cache_snapshot_batches 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _python_language, _snapshot
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.cache.helpers import _commit_index_results
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


def test_snapshot_revalidates_pending_rows_at_batch_commit(tmp_path):
    from tree_sitter_analyzer.cache import indexer

    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("a = 1\n", encoding="utf-8")
    second.write_text("b = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(first), str(second)),
        language_fn=_python_language,
    )
    cache = ASTCache(str(tmp_path))
    real_insert = indexer.insert_index_row

    def insert_then_mutate(*args, **kwargs):
        real_insert(*args, **kwargs)
        if args[2]["rel_path"] == "b.py":
            first.write_text("a = 200\n", encoding="utf-8")

    try:
        with patch.object(indexer, "insert_index_row", side_effect=insert_then_mutate):
            result = cache.index_project(
                max_files=10,
                workers=0,
                candidate_snapshot=snapshot,
            )
        first_cached = cache.lookup(str(first))
        second_cached = cache.lookup(str(second))
        graph_built = cache.call_graph_built()
    finally:
        cache.close()

    assert result["indexed"] == 1
    assert result["changed_during_run_files"] == ["a.py"]
    assert first_cached is None
    assert second_cached is not None
    assert graph_built is False


def test_snapshot_revalidates_rows_from_earlier_committed_batches(tmp_path):
    # PR #1172 review 2026-07-27: 之前只重新验证了待提交批次。
    from tree_sitter_analyzer.cache import indexer

    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("a = 1\n", encoding="utf-8")
    second.write_text("b = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(first), str(second)),
        language_fn=_python_language,
    )
    cache = ASTCache(str(tmp_path))
    real_commit = _commit_index_results
    real_insert = indexer.insert_index_row

    def commit_one_at_a_time(*args, **kwargs):
        real_commit(*args, batch_size=1, **kwargs)

    def insert_then_mutate(*args, **kwargs):
        real_insert(*args, **kwargs)
        if args[2]["rel_path"] == "b.py":
            first.write_text("a = 200\n", encoding="utf-8")

    try:
        with (
            patch(
                "tree_sitter_analyzer.ast_cache._commit_index_results",
                side_effect=commit_one_at_a_time,
            ),
            patch.object(indexer, "insert_index_row", side_effect=insert_then_mutate),
        ):
            result = cache.index_project(
                max_files=10,
                workers=0,
                candidate_snapshot=snapshot,
            )
        outcome = (
            result["indexed"],
            result["changed_during_run_files"],
            cache.lookup(str(first)),
            cache.lookup(str(second)) is not None,
            cache.call_graph_built(),
        )
    finally:
        cache.close()

    assert outcome == (1, ["a.py"], None, True, False)


def test_commit_helper_guards_each_full_batch():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE committed_files (file_path TEXT)")
    results = [
        {
            "rel_path": rel_path,
            "status": "indexed",
            "symbols_count": 0,
            "content_hash": "0" * 64,
        }
        for rel_path in ("a.py", "b.py")
    ]
    stats = {"errors": 0, "indexed": 0, "files": []}
    guarded: list[list[str]] = []

    def insert(result, _indexed_at, *, include_activation):
        conn.execute("INSERT INTO committed_files VALUES (?)", (result["rel_path"],))

    _commit_index_results(
        conn,
        results,
        stats,
        insert,
        "now",
        False,
        batch_size=1,
        batch_guard=lambda batch: guarded.append(
            [result["rel_path"] for result in batch]
        ),
    )

    assert guarded == [["a.py"], ["b.py"]]


def test_commit_helper_commits_full_batch_without_guard():
    # PR #1172: 可选的快照 guard 不能改变普通批次的提交。
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE committed_files (file_path TEXT)")
    result = {
        "rel_path": "a.py",
        "status": "indexed",
        "symbols_count": 0,
        "content_hash": "0" * 64,
    }
    stats = {"errors": 0, "indexed": 0, "files": []}

    def insert(item, _indexed_at, *, include_activation):
        conn.execute("INSERT INTO committed_files VALUES (?)", (item["rel_path"],))

    _commit_index_results(conn, [result], stats, insert, "now", False, batch_size=1)

    assert conn.execute("SELECT file_path FROM committed_files").fetchall() == [
        ("a.py",)
    ]


def test_snapshot_batch_revalidation_handles_missing_error_detail(tmp_path):
    # PR #1172: 失败的 worker 可能没有先前的详细结果行可替换。
    from tree_sitter_analyzer.cache.indexer import _revalidate_snapshot_batch

    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    entry = _snapshot(tmp_path, path).selected_entries[0]
    path.write_text("value = 200\n", encoding="utf-8")
    stats = {
        "errors": 1,
        "indexed": 0,
        "skipped": 0,
        "processed": 1,
        "changed_during_run": 0,
        "changed_during_run_files": [],
        "files": [],
    }

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    try:
        _revalidate_snapshot_batch(
            [{"rel_path": "app.py", "status": "io_error"}],
            cache=SimpleNamespace(
                fts5_available=False,
                project_root=str(tmp_path),
            ),
            conn=conn,
            entries={"app.py": entry},
            stats=stats,
        )
    finally:
        conn.close()

    assert stats == {
        "errors": 0,
        "indexed": 0,
        "skipped": 1,
        "incomplete_skips": 1,
        "processed": 0,
        "changed_during_run": 1,
        "changed_during_run_files": ["app.py"],
        "files": [
            {
                "file": "app.py",
                "status": "skipped",
                "reason": "file changed after candidate snapshot",
            }
        ],
    }


def test_failed_worker_snapshot_revalidation_discards_old_generation(tmp_path):
    # PR #1172 review 2026-07-27: 稍后失败的 worker 不能保留过期行。
    from tree_sitter_analyzer.cache.indexer import _revalidate_snapshot_batch

    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    path.write_text("value = 20\n", encoding="utf-8")
    entry = _snapshot(tmp_path, path).selected_entries[0]
    path.write_text("value = 300\n", encoding="utf-8")
    stats = {
        "errors": 1,
        "indexed": 0,
        "skipped": 0,
        "processed": 1,
        "changed_during_run": 0,
        "changed_during_run_files": [],
        "files": [{"file": "app.py", "status": "error", "reason": "read failed"}],
    }

    try:
        _revalidate_snapshot_batch(
            [{"rel_path": "app.py", "status": "io_error"}],
            cache=cache,
            conn=cache.get_conn(),
            entries={"app.py": entry},
            stats=stats,
        )
        cached = cache.lookup(str(path))
    finally:
        cache.close()

    assert cached is None
