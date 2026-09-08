"""#1376：test_ast_cache_storage_transactions 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.cache.indexer import (
    _clear_full_rebuild_rows,
)
from tree_sitter_analyzer.cache.write import invalidate_file_rows
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


class TestAstCacheWriteHelpers:
    def test_empty_fts5_symbol_batches_return_empty(self):
        from tree_sitter_analyzer.cache.write import (
            write_fts5_symbols,
            write_fts5_symbols_from_tuples,
        )

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE ast_symbol_rows ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, kind TEXT, "
            "file_path TEXT, language TEXT, line INTEGER, end_line INTEGER)"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE ast_symbols_fts "
            "USING fts5(name, kind, file_path, language, content='')"
        )

        assert write_fts5_symbols(conn, "empty.py", "python", {"symbols": []}) == []
        assert write_fts5_symbols_from_tuples(conn, "empty.py", "python", []) == []


@pytest.mark.parametrize("kind", ["extends", "implements"])
def test_invalidation_removes_incoming_resolved_hierarchy_edges(tmp_path, kind):
    # PR #1172 review 2026-07-27: 使目标失效后曾遗留派生层级行。
    from tree_sitter_analyzer.graph.edge_store import Edge, EdgeStore

    target = tmp_path / "target.py"
    target.write_text("class Base:\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(target))
    conn = cache.get_conn()
    EdgeStore(conn, ensure_schema=False).upsert_edges(
        [
            Edge("caller.py:Child:1", "class:Base", kind, line=1),
            Edge(
                "caller.py:Child:1",
                "target.py:Base:1",
                kind,
                line=1,
                provenance="unresolved_refs",
                metadata={
                    "resolution": "unresolved_refs",
                    "resolved_file": "target.py",
                    "resolved_name": "Base",
                    "resolved_symbol_id": 1,
                },
            ),
        ]
    )
    conn.commit()

    try:
        cache.invalidate(str(target))
        targets = [
            row["target_node_id"]
            for row in conn.execute(
                "SELECT target_node_id FROM edges WHERE kind = ? ORDER BY target_node_id",
                (kind,),
            ).fetchall()
        ]
    finally:
        cache.close()

    assert targets == ["class:Base"]


def test_full_rebuild_clear_tolerates_legacy_primary_only_schema():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py')")

    _clear_full_rebuild_rows(SimpleNamespace(fts5_available=False), conn)

    assert conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0] == 0
    conn.close()


def test_full_rebuild_clear_propagates_derived_table_failure(tmp_path):
    cache = ASTCache(str(tmp_path))
    conn = cache.get_conn()

    class FailingDerivedDelete:
        def execute(self, sql, *args, **kwargs):
            if sql == "DELETE FROM ast_imports":
                raise sqlite3.OperationalError("database or disk is full")
            return conn.execute(sql, *args, **kwargs)

    try:
        with pytest.raises(sqlite3.OperationalError, match="disk is full"):
            _clear_full_rebuild_rows(
                SimpleNamespace(fts5_available=False),
                FailingDerivedDelete(),
            )
        conn.rollback()
    finally:
        cache.close()


def test_file_invalidation_tolerates_legacy_primary_only_schema():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py')")

    removed = invalidate_file_rows(conn, "app.py", False)

    assert removed is True
    conn.close()


def test_missing_file_invalidation_preserves_complete_graph_marker(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("def caller():\n    return caller()\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_project(workers=0)

    try:
        removed = cache.invalidate(str(tmp_path / "missing.py"))
        graph_built = cache.call_graph_built()
    finally:
        cache.close()

    assert (removed, graph_built) == (False, True)


def test_file_invalidation_tolerates_ladybug_cleanup_failure(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))

    try:
        with patch(
            "tree_sitter_analyzer.knowledge_graph.stores."
            "LadybugKnowledgeGraphStore.remove_if_exists",
            side_effect=OSError("mirror is busy"),
        ):
            removed = cache.invalidate(str(path))
        cached = cache.lookup(str(path))
    finally:
        cache.close()

    assert (removed, cached) == (True, None)


def test_file_invalidation_rolls_back_derived_table_failure(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    conn = cache.get_conn()
    before = cache.lookup(str(path))

    class FailingDerivedDelete:
        @property
        def total_changes(self):
            return conn.total_changes

        def execute(self, sql, *args, **kwargs):
            if sql == "DELETE FROM ast_imports WHERE file_path = ?":
                raise sqlite3.OperationalError("database or disk is full")
            return conn.execute(sql, *args, **kwargs)

        def rollback(self):
            conn.rollback()

    try:
        with pytest.raises(sqlite3.OperationalError, match="disk is full"):
            invalidate_file_rows(FailingDerivedDelete(), "app.py", True)
        after = cache.lookup(str(path))
    finally:
        cache.close()

    assert after == before


def test_file_invalidation_rolls_back_marker_clear_failure(tmp_path):
    # PR #1172 review 2026-07-27: marker 失败曾导致删除事务未提交。
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    conn = cache.get_conn()
    before = cache.lookup(str(path))

    class FailingMarkerClear:
        @property
        def total_changes(self):
            return conn.total_changes

        def execute(self, sql, *args, **kwargs):
            if sql.startswith("INSERT INTO ast_call_graph_state"):
                raise sqlite3.OperationalError("database or disk is full")
            return conn.execute(sql, *args, **kwargs)

        def commit(self):
            conn.commit()

        def rollback(self):
            conn.rollback()

    try:
        with pytest.raises(sqlite3.OperationalError, match="disk is full"):
            invalidate_file_rows(FailingMarkerClear(), "app.py", True)
        after = cache.lookup(str(path))
    finally:
        cache.close()

    assert after == before


def test_scope_prune_failure_rolls_back_all_stale_rows(cache, monkeypatch):
    # PR #1253: scope 协调必须在认证之前原子完成。
    from tree_sitter_analyzer.cache import indexer

    cache.index_project(workers=0)
    conn = cache.get_conn()
    original_paths = {
        str(row[0]) for row in conn.execute("SELECT file_path FROM ast_index")
    }
    selected_path = sorted(original_paths)[0]
    candidate = IndexCandidateSnapshot(
        project_root=cache.project_root,
        max_files=10,
        entries=(),
        present_paths=frozenset({selected_path}),
        discovered=1,
        selected=0,
        excluded=0,
        skipped=0,
        errors=0,
        limited=0,
    )
    monkeypatch.setattr(
        indexer,
        "_discard_snapshot_generation",
        lambda *_args: (_ for _ in ()).throw(sqlite3.OperationalError("prune failed")),
    )

    with pytest.raises(sqlite3.OperationalError, match="prune failed"):
        indexer._prune_to_selected_scope(cache, conn, candidate)
    remaining = {str(row[0]) for row in conn.execute("SELECT file_path FROM ast_index")}

    assert remaining == original_paths


def test_single_file_edge_write_failure_is_index_error(tmp_path, monkeypatch):
    # PR #1253 review thread 2088: 没有图边时，主表行不能认证完整性。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import write

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    monkeypatch.setattr(
        write, "write_graph_edges_for_file", lambda *_args, **_kwargs: False
    )

    result = cache.index_file(str(source))
    indexed = cache.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
    complete = cache.call_graph_built()
    cache.close()
    assert (result["status"], result["certification_errors"], indexed, complete) == (
        "error",
        1,
        0,
        False,
    )


@pytest.mark.parametrize("route", ["single", "project"])
@pytest.mark.parametrize("fault", ["sql_error", "schema_changed"])
def test_certification_write_fault_propagates_and_rolls_back(tmp_path, route, fault):
    # PR #1350：真实 SQLite 更新错误不能被 pre-v14 兼容层吞掉并提交新行。
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("def before():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(source))["status"] == "indexed"
        conn = cache.get_conn()
        if fault == "sql_error":
            conn.execute(
                "CREATE TRIGGER reject_certification BEFORE UPDATE OF certified_at ON ast_index BEGIN SELECT abs(-9223372036854775808); END"
            )
            error = "integer overflow"
        else:
            conn.execute("ALTER TABLE ast_index DROP COLUMN certified_at")
            error = "no such column: certified_at"
        conn.commit()
        before = tuple(conn.execute("SELECT * FROM ast_index").fetchone())
        source.write_text("def after_change():\n    return 22\n", encoding="utf-8")
        with pytest.raises(sqlite3.OperationalError, match=error):
            if route == "single":
                cache.index_file(str(source))
            else:
                cache.index_project(workers=0)
        assert conn.in_transaction is False
        assert tuple(conn.execute("SELECT * FROM ast_index").fetchone()) == before
        assert [r[0] for r in conn.execute("SELECT name FROM ast_symbol_rows")] == [
            "before"
        ]
        if fault == "sql_error":
            conn.execute("DROP TRIGGER reject_certification")
        else:
            conn.execute("ALTER TABLE ast_index ADD COLUMN certified_at INTEGER")
        conn.commit()
        if route == "single":
            assert cache.index_file(str(source))["status"] == "indexed"
        else:
            assert cache.index_project(workers=0)["indexed"] == 1
        assert [r[0] for r in conn.execute("SELECT name FROM ast_symbol_rows")] == [
            "after_change"
        ]
    finally:
        cache.close()


def test_project_edge_write_failure_rolls_back_batch(tmp_path, monkeypatch):
    # PR #1253 review thread 2088: worker 结果提交必须传播边写入失败。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import write

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    monkeypatch.setattr(
        write, "write_graph_edges_for_file", lambda *_args, **_kwargs: False
    )

    with pytest.raises(sqlite3.OperationalError, match="^GRAPH_EDGE_WRITE_FAILED$"):
        cache.index_project(force=True, workers=1)
    indexed = cache.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
    complete = cache.call_graph_built()
    cache.close()
    assert (indexed, complete) == (0, False)


def test_single_file_marker_write_failure_is_safely_suppressed(tmp_path):
    # PR #1253: 单次认证写入失败不能破坏索引可用性。
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))

    try:
        with patch(
            "tree_sitter_analyzer._ast_cache_index_mixin._mark_call_graph_built_strict",
            side_effect=sqlite3.OperationalError("malformed marker"),
        ) as marker:
            cache._mark_single_file_index_complete_if_needed(
                True,
                {"status": "cached"},
            )
    finally:
        cache.close()

    assert marker.call_count == 1
