"""#1376：test_ast_cache_snapshot_epoch 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
from unittest.mock import patch

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _python_language, _snapshot, requires_posix_fd
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
    _content_hash,
)
from tree_sitter_analyzer.cache.callgraph_state import clear_call_graph_built
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


@pytest.mark.skipif(os.name != "posix", reason="GH-1253: authoritative frozen epoch")
def test_force_index_retains_complete_frozen_epoch_on_live_mutation(tmp_path):
    from tree_sitter_analyzer.cache import extraction

    path = tmp_path / "app.py"
    path.write_text(
        "import os\n\ndef stale():\n    return os.getcwd()\n", encoding="utf-8"
    )
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    # PR #1253 thread 3759852177: 最终实时重放发生漂移时，冻结行仍须保留。
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(path),),
        language_fn=_python_language,
        materialize=True,
    )
    mirror = tmp_path / ".ast-cache" / "knowledge-graph.lbug"
    mirror.write_text("stale mirror", encoding="utf-8")
    real_worker = extraction._worker_index_file

    def worker_then_mutate(args):
        result = real_worker(args)
        path.write_text("def changed():\n    return 2\n", encoding="utf-8")
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
        graph_built = cache.call_graph_built()
        manifest_count = conn.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
        mirror_exists = mirror.exists()
    finally:
        from tree_sitter_analyzer.indexing_candidate_materialization import (
            cleanup_index_candidate_snapshot,
        )

        cleanup_index_candidate_snapshot(snapshot)
        cache.close()

    assert counts == {
        "ast_index": 1,
        "ast_symbol_rows": 2,
        "ast_symbols_fts": 2,
        "ast_imports": 1,
        "ast_symbol_activation": 0,
        "edges": 2,
    }
    assert (graph_built, manifest_count, mirror_exists) == (False, 0, False)


def test_snapshot_guard_discards_preexisting_stale_generation(tmp_path):
    # PR #1172 review 2026-07-27: 被拒绝的 worker 曾让旧缓存行继续存活。
    from tree_sitter_analyzer.cache import extraction

    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    path.write_text("value = 20\n", encoding="utf-8")
    snapshot = _snapshot(tmp_path, path)
    real_worker = extraction._worker_index_file

    def worker_then_mutate(args):
        result = real_worker(args)
        path.write_text("value = 300\n", encoding="utf-8")
        return result

    try:
        with patch.object(
            extraction,
            "_worker_index_file",
            side_effect=worker_then_mutate,
        ):
            cache.index_project(
                max_files=10,
                workers=0,
                candidate_snapshot=snapshot,
            )
        cached = cache.lookup(str(path))
    finally:
        cache.close()

    assert cached is None


def test_snapshot_guard_removes_ladybug_mirror(tmp_path):
    # PR #1172 review 2026-07-27: 直接丢弃行必须使投影失效。
    from tree_sitter_analyzer.cache.indexer import _snapshot_result_is_stable

    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    path.write_text("value = 20\n", encoding="utf-8")
    entry = _snapshot(tmp_path, path).selected_entries[0]
    mirror = tmp_path / ".ast-cache" / "knowledge-graph.lbug"
    mirror.write_text("stale", encoding="utf-8")
    path.write_text("value = 300\n", encoding="utf-8")
    stats = {
        "skipped": 0,
        "processed": 1,
        "changed_during_run": 0,
        "changed_during_run_files": [],
        "files": [],
    }

    try:
        stable = _snapshot_result_is_stable(
            {"rel_path": "app.py"},
            {"app.py": entry},
            stats,
            cache=cache,
            conn=cache.get_conn(),
        )
        mirror_exists = mirror.exists()
    finally:
        cache.close()

    assert (stable, mirror_exists) == (False, False)


def test_snapshot_guard_tolerates_ladybug_cleanup_failure(tmp_path):
    # PR #1172 review 2026-07-27: 镜像清理仍采用尽力而为策略。
    from tree_sitter_analyzer.cache.indexer import _snapshot_result_is_stable

    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    path.write_text("value = 20\n", encoding="utf-8")
    entry = _snapshot(tmp_path, path).selected_entries[0]
    path.write_text("value = 300\n", encoding="utf-8")
    stats = {
        "skipped": 0,
        "processed": 1,
        "changed_during_run": 0,
        "changed_during_run_files": [],
        "files": [],
    }

    try:
        with patch(
            "tree_sitter_analyzer.knowledge_graph.stores."
            "LadybugKnowledgeGraphStore.remove_if_exists",
            side_effect=OSError("mirror is busy"),
        ):
            stable = _snapshot_result_is_stable(
                {"rel_path": "app.py"},
                {"app.py": entry},
                stats,
                cache=cache,
                conn=cache.get_conn(),
            )
    finally:
        cache.close()

    assert stable is False


@requires_posix_fd
def test_candidate_hash_change_reindexes_with_preserved_mtime_and_size(tmp_path):
    # PR #1253 review 3755386837: 候选缓存复用必须绑定内容。
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    admitted = path.stat()
    path.write_text("value = 2\n", encoding="utf-8")
    os.utime(path, ns=(admitted.st_atime_ns, admitted.st_mtime_ns))
    snapshot = _snapshot(tmp_path, path)

    try:
        result = cache.index_project(max_files=10, candidate_snapshot=snapshot)
        stored_hash = (
            cache.get_conn()
            .execute("SELECT content_hash FROM ast_index WHERE file_path = 'app.py'")
            .fetchone()[0]
        )
    finally:
        cache.close()

    assert (result["indexed"], result["cached"], stored_hash) == (
        1,
        0,
        _content_hash("value = 2\n"),
    )


def test_cached_snapshot_mutation_does_not_stamp_graph_complete(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)
    clear_call_graph_built(cache.get_conn())

    def mutate_after_partition(_workers, _candidates):
        path.write_text("value = 200\n", encoding="utf-8")
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
