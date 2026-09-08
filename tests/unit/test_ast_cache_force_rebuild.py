"""#1376：test_ast_cache_force_rebuild 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import sqlite3
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _python_language, _snapshot, requires_posix_fd
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


@requires_posix_fd
def test_force_snapshot_edit_aborts_before_any_database_table_changes(tmp_path):
    # PR #1253 review 3759391262: force-clear 授权必须绑定内容。
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)
    before = "\n".join(cache.get_conn().iterdump())
    path.write_text("value = 2\n", encoding="utf-8")

    try:
        result = cache.index_project(
            max_files=10, force=True, candidate_snapshot=snapshot
        )
        after = "\n".join(cache.get_conn().iterdump())
    finally:
        cache.close()

    assert (result["verdict"], result["abort_remaining_phases"]) == ("WARN", True)
    assert result["changed_during_run_files"] == ["app.py"]
    assert after == before


@requires_posix_fd
def test_force_snapshot_delete_aborts_before_any_database_table_changes(tmp_path):
    # PR #1253 review 3759391262: 删除不能授权 force clear。
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    snapshot = _snapshot(tmp_path, path)
    before = "\n".join(cache.get_conn().iterdump())
    path.unlink()

    try:
        result = cache.index_project(
            max_files=10, force=True, candidate_snapshot=snapshot
        )
        after = "\n".join(cache.get_conn().iterdump())
    finally:
        cache.close()

    assert (result["verdict"], result["abort_remaining_phases"]) == ("WARN", True)
    assert result["changed_during_run_files"] == ["app.py"]
    assert after == before


def test_force_rebuild_clear_failure_preserves_existing_index(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    before = cache.lookup(str(path))

    def clear_then_fail(_cache, conn):
        conn.execute("DELETE FROM ast_index")
        raise sqlite3.OperationalError("simulated FTS cleanup failure")

    try:
        with (
            patch(
                "tree_sitter_analyzer.cache.indexer._clear_full_rebuild_rows",
                side_effect=clear_then_fail,
            ),
            pytest.raises(sqlite3.OperationalError, match="FTS cleanup failure"),
        ):
            cache.index_project(force=True)
        after = cache.lookup(str(path))
    finally:
        cache.close()

    assert after == before


def test_force_rebuild_tolerates_ladybug_cleanup_failure(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))

    try:
        with patch(
            "tree_sitter_analyzer.cache.indexer._invalidate_ladybug",
            side_effect=OSError("mirror is busy"),
        ):
            result = cache.index_project(force=True, workers=0)
        cached = cache.lookup(str(path))
    finally:
        cache.close()

    assert result["indexed"] == 1
    assert cached is not None


def test_force_rebuild_clear_failure_restores_complete_graph_marker(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("def caller():\n    return caller()\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_project(workers=0)

    def clear_then_fail(_cache, conn):
        conn.execute("DELETE FROM ast_index")
        raise sqlite3.OperationalError("simulated derived cleanup failure")

    try:
        with (
            patch(
                "tree_sitter_analyzer.cache.indexer._clear_full_rebuild_rows",
                side_effect=clear_then_fail,
            ),
            pytest.raises(sqlite3.OperationalError, match="cleanup failure"),
        ):
            cache.index_project(force=True, workers=0)
        graph_built = cache.call_graph_built()
    finally:
        cache.close()

    assert graph_built is True


def test_force_rebuild_clear_failure_keeps_incomplete_graph_marker(tmp_path):
    cache = ASTCache(str(tmp_path))

    def fail_clear(_cache, _conn):
        raise sqlite3.OperationalError("simulated derived cleanup failure")

    try:
        with (
            patch(
                "tree_sitter_analyzer.cache.indexer._clear_full_rebuild_rows",
                side_effect=fail_clear,
            ),
            pytest.raises(sqlite3.OperationalError, match="cleanup failure"),
        ):
            cache.index_project(force=True, workers=0)
        graph_built = cache.call_graph_built()
    finally:
        cache.close()

    assert graph_built is False


def test_force_rebuild_without_secure_materialization_keeps_legacy_data_plane(
    tmp_path, monkeypatch
):
    # PR #1253: Windows 缺少权威冻结实体化能力，但原有的
    # 完整索引的数据平面和操作性 marker 仍然可用。

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=_python_language,
    )
    snapshot = replace(snapshot, frozen_error="SECURE_MATERIALIZATION_UNSUPPORTED")
    monkeypatch.setattr(
        materialization, "secure_candidate_materialization_supported", lambda: False
    )
    monkeypatch.setattr(
        materialization, "index_candidate_snapshot_is_materialized", lambda _item: False
    )
    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_project(
            force=True, max_files=10, candidate_snapshot=snapshot, workers=0
        )
        marker = cache.call_graph_built()
    finally:
        cache.close()

    assert (result["indexed"], result["mode_used"], marker) == (
        1,
        "full",
        True,
    )


def test_force_without_materialized_evidence_preserves_existing_cache(
    tmp_path: Path,
) -> None:
    # PR #1253 thread 3759852177: 实时路径证据不能授权清空。
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
