"""#1376：test_ast_cache_projection_state 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import tests.unit._ast_cache_helpers as _fixtures
import tree_sitter_analyzer.ast_cache as ast_cache_module
from tests.unit._ast_cache_helpers import _BACKFILL_ROUTES
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.cache.write import invalidate_file_rows

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
engine = _fixtures.engine
method_project = _fixtures.method_project


def test_disabled_synapse_backfill_returns_complete_zero_stats(tmp_path, monkeypatch):
    # PR #1172: 禁用解析是完整的零操作，而非不确定状态。
    monkeypatch.setenv("TSA_SYNAPSE", "0")
    cache = ASTCache(str(tmp_path))
    try:
        result = cache._run_synapse_backfill()
    finally:
        cache.close()

    assert result == {"total": 0, "resolved": 0, "unchanged": 0, "errors": 0}


def test_no_fts_upgrade_backfills_legacy_symbols_for_cached_consumers(
    tmp_path, monkeypatch
):
    # PR #1253: 未改变的旧版行无需重新索引也必须可见。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache.schema import SCHEMA_V1
    from tree_sitter_analyzer.miswire_audit import _iter_symbol_defs

    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    conn = sqlite3.connect(cache_dir / "index.db")
    conn.executescript(SCHEMA_V1)
    conn.execute(
        "INSERT INTO ast_index "
        "(file_path, content_hash, language, mtime_ns, file_size, "
        "extractor_version, symbols_json, imports_json, structure_json, indexed_at) "
        "VALUES (?, ?, ?, 0, 0, 0, ?, '[]', '{}', 'now')",
        (
            "legacy.py",
            "hash",
            "python",
            json.dumps(
                {"symbols": [{"name": "legacy", "kind": "function", "line": 3}]}
            ),
        ),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(ast_cache_module, "_has_fts5", lambda _conn: False)

    cache = ASTCache(str(tmp_path))
    try:
        definitions = _iter_symbol_defs(cache.get_conn())
    finally:
        cache.close()

    assert definitions == [("legacy", "legacy.py", "python")]


def test_fully_cached_missing_marker_reruns_every_backfill(engine, monkeypatch):
    # PR #1253: 缺少持久 marker 的边行不能证明收敛。
    first = engine.index_project(workers=0)
    assert first["indexed"] == 2
    conn = engine.get_conn()
    conn.execute("DELETE FROM ast_call_graph_state")
    conn.commit()
    calls = {name: 0 for name, _key in _BACKFILL_ROUTES}

    for name, _key in _BACKFILL_ROUTES:

        def clean(name=name):
            calls[name] += 1
            return {"errors": 0}

        monkeypatch.setattr(engine, name, clean)
    second = engine.index_project(workers=0)

    assert (second["indexed"], calls, engine.call_graph_built()) == (
        0,
        {name: 1 for name, _key in _BACKFILL_ROUTES},
        True,
    )


def test_fully_cached_failed_retry_keeps_marker_clear(engine, monkeypatch):
    # PR #1253: 缓存 backfill 重试失败必须保持可见的不完整状态。
    engine.index_project(workers=0)
    conn = engine.get_conn()
    conn.execute("DELETE FROM ast_call_graph_state")
    conn.commit()
    for name, _key in _BACKFILL_ROUTES:
        monkeypatch.setattr(engine, name, lambda: {"errors": 0})
    monkeypatch.setattr(engine, "_run_synapse_backfill", lambda: {"errors": 1})

    result = engine.index_project(workers=0)
    marker = conn.execute(
        "SELECT built FROM ast_call_graph_state WHERE id = 1"
    ).fetchone()
    manifest_count = conn.execute(
        "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
    ).fetchone()[0]

    assert (result["backfill_errors"], marker[0], manifest_count) == (1, 0, 0)


def test_cached_graph_refresh_propagates_edge_write_failure(monkeypatch):
    # PR #1253: 缓存主表行不能隐藏图刷新失败。
    from tree_sitter_analyzer._ast_cache_index_mixin import _refresh_cached_graph_row
    from tree_sitter_analyzer.cache import write

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT 'app.py' AS file_path, 'python' AS language, "
        "'{}' AS symbols_json, '[]' AS imports_json"
    ).fetchone()
    monkeypatch.setattr(
        write, "write_graph_edges_for_file", lambda *_args, **_kwargs: False
    )

    try:
        refreshed = _refresh_cached_graph_row(conn, row)
    finally:
        conn.close()

    assert refreshed is False


def test_projection_state_tracks_file_update(tmp_path):
    # PR #1253 review thread 3756380009: writer 将行绑定到当前哈希。
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "state_update.py"
    source.write_text("def before():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        source.write_text("def after():\n    pass\n", encoding="utf-8")
        cache.index_file(str(source))
        row = (
            cache.get_conn()
            .execute(
                "SELECT state.content_hash, state.symbol_count, idx.content_hash "
                "FROM ast_symbol_projection_state AS state JOIN ast_index AS idx "
                "ON idx.file_path=state.file_path WHERE state.file_path='state_update.py'"
            )
            .fetchone()
        )
    finally:
        cache.close()

    assert tuple(row) == (row[2], 1, row[2])


def test_projection_state_is_deleted_with_file_generation(tmp_path):
    # PR #1253 review thread 3756380009: 失效操作必须删除投影证据。

    source = tmp_path / "state_delete.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = _fixtures.engine_cache(tmp_path)
    try:
        cache.index_file(str(source))
        invalidate_file_rows(cache.get_conn(), "state_delete.py", cache.fts5_available)
        state = (
            cache.get_conn()
            .execute(
                "SELECT file_path FROM ast_symbol_projection_state "
                "WHERE file_path='state_delete.py'"
            )
            .fetchone()
        )
    finally:
        cache.close()

    assert state is None


def test_projection_repair_without_fts_skips_fts_rebuild(tmp_path):
    # PR #1253: 普通投影修复必须支持没有 FTS5 的 SQLite。
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = _fixtures.engine_cache(tmp_path)
    cache.index_project(workers=0)
    conn = cache.get_conn()
    conn.execute("DELETE FROM ast_cache_metadata WHERE key='symbol_rows_projection_v1'")
    conn.commit()
    cache._fts5_available = False

    try:
        result = cache.index_project(workers=0)
    finally:
        cache.close()

    assert (result["errors"], result["total_files"]) == (0, 1)


def test_projection_repair_signals_incomplete_epoch_before_batch_write(tmp_path):
    # PR #1253 thread 3757429352: 并发读取者不能信任正在修复的批次。
    from tree_sitter_analyzer.cache.build_state import build_in_progress
    from tree_sitter_analyzer.cache.callgraph_state import call_graph_built

    source = tmp_path / "app.py"
    source.write_text("def target():\n    return 1\n", encoding="utf-8")
    cache = _fixtures.engine_cache(tmp_path)
    cache.index_project(workers=0)
    conn = cache.get_conn()
    conn.execute(
        "UPDATE ast_symbol_rows SET kind = 'forged' WHERE file_path = 'app.py'"
    )
    conn.commit()
    observed = []
    original = ast_cache_module._commit_index_results

    def inspect_reader(*args, **kwargs):
        reader = sqlite3.connect(cache.db_path)
        try:
            observed.append(
                (
                    build_in_progress(reader),
                    call_graph_built(reader),
                    reader.execute(
                        "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
                    ).fetchone()[0],
                )
            )
        finally:
            reader.close()
        return original(*args, **kwargs)

    try:
        with patch.object(ast_cache_module, "_commit_index_results", inspect_reader):
            result = cache.index_project(workers=0)
    finally:
        cache.close()

    assert (result["errors"], observed) == (0, [(True, False, 0)])


def test_projection_repair_records_failed_projection_certification(tmp_path):
    # PR #1253 thread 3757429352: 修复认证失败必须保持可见。
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = _fixtures.engine_cache(tmp_path)
    cache.index_project(workers=0)
    conn = cache.get_conn()
    conn.execute(
        "DELETE FROM ast_cache_metadata WHERE key = 'symbol_rows_projection_v1'"
    )
    conn.commit()

    try:
        with patch(
            "tree_sitter_analyzer.index_snapshot_symbols.ensure_symbol_rows_backfilled",
            return_value=False,
        ):
            result = cache.index_project(workers=0)
    finally:
        cache.close()

    assert result["backfill_errors"] == 1


def test_oversized_legacy_projection_opens_incomplete_then_repairs(
    tmp_path, monkeypatch
):
    # PR #1253 thread 3760944100: 迁移预算不能导致缓存无法打开。
    import tree_sitter_analyzer.index_snapshot_symbols as snapshot_symbols
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache.schema import SCHEMA_V1

    source = tmp_path / "legacy.py"
    source.write_text("def repaired():\n    return 1\n", encoding="utf-8")
    cache_dir = tmp_path / ".ast-cache"
    cache_dir.mkdir()
    conn = sqlite3.connect(cache_dir / "index.db")
    conn.executescript(SCHEMA_V1)
    conn.execute(
        "INSERT INTO ast_index "
        "(file_path, content_hash, language, mtime_ns, file_size, "
        "extractor_version, symbols_json, imports_json, structure_json, indexed_at) "
        "VALUES ('legacy.py', 'old', 'python', 0, 0, 0, ?, '[]', '{}', 'now')",
        (json.dumps({"symbols": [{"name": "legacy", "kind": "function"}]}),),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(ast_cache_module, "_has_fts5", lambda _conn: False)

    with monkeypatch.context() as migration_budget:
        migration_budget.setattr(
            snapshot_symbols, "_LEGACY_SYMBOL_MIGRATION_ROW_BUDGET", 0
        )
        cache = ASTCache(str(tmp_path))
    try:
        marker_before = (
            cache.get_conn()
            .execute(
                "SELECT value FROM ast_cache_metadata "
                "WHERE key='symbol_rows_projection_v1'"
            )
            .fetchone()
        )
        repaired = cache.index_project(workers=0)
        marker_after_row = (
            cache.get_conn()
            .execute(
                "SELECT value FROM ast_cache_metadata "
                "WHERE key='symbol_rows_projection_v1'"
            )
            .fetchone()
        )
        marker_after = tuple(marker_after_row) if marker_after_row is not None else None

        assert (marker_before, repaired["indexed"], marker_after) == (
            None,
            1,
            ("complete",),
        )
    finally:
        cache.close()


def test_reopen_revokes_certification_when_projection_backfill_is_incomplete(
    tmp_path, monkeypatch
):
    # PR #1253 thread 3761703241: 不完整的迁移不能保留之前的
    # 调用图或权威 manifest 完整性信号。
    import tree_sitter_analyzer.cache.schema as cache_schema
    from tree_sitter_analyzer.cache.callgraph_state import mark_call_graph_built_strict

    cache = _fixtures.engine_cache(tmp_path)
    conn = cache.get_conn()
    mark_call_graph_built_strict(conn)
    conn.execute(
        "INSERT OR REPLACE INTO ast_index_snapshot_manifest "
        "(singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version) "
        "VALUES (1, ?, 'source', 'index', 0, '{}', 2)",
        (str(tmp_path.resolve()),),
    )
    conn.commit()
    cache.close()

    monkeypatch.setattr(
        cache_schema, "ensure_symbol_rows_backfilled", lambda *_args, **_kwargs: False
    )
    reopened = _fixtures.engine_cache(tmp_path)
    try:
        reopened_conn = reopened.get_conn()
        marker = reopened.call_graph_built()
        manifest_count = reopened_conn.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
    finally:
        reopened.close()

    assert (marker, manifest_count) == (False, 0)


def test_incomplete_cached_noop_clears_current_global_marker(tmp_path: Path) -> None:
    # PR #1253 thread 3760046643: 即使是 no-op，scope 缺口仍须撤销认证。
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


def test_projection_residue_converges_without_full_reindex(engine):
    """dogfood 2026-11-09：内部残余收敛后，索引必须仍是增量。

    修复前，陈旧行 / 缺失投影状态会让 ``symbol_projection_is_exact`` 永远为假，
    每次 ``index`` 都把全部文件重新提取（本仓库 2917 文件实测 0.6 s → 57 s）。
    """
    first = engine.index_project(workers=0)
    assert first["indexed"] == 2
    conn = engine.get_conn()
    conn.execute(
        "DELETE FROM ast_symbol_projection_state WHERE file_path = "
        "(SELECT file_path FROM ast_index ORDER BY file_path LIMIT 1)"
    )
    conn.execute(
        "INSERT INTO ast_symbol_rows(name, kind, file_path, language, line, end_line) "
        "VALUES ('ghost', 'function', 'gone.py', 'python', 1, 2)"
    )
    conn.commit()

    stats = engine.index_project(workers=0)

    assert stats["indexed"] == 0
    assert stats["cached"] == 2
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM ast_symbol_rows WHERE file_path = 'gone.py'"
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM ast_symbol_projection_state").fetchone()[0]
        == conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
    )


def _projection_fixture_conn():
    """最小的投影 schema：索引源 + 参考行 + 状态 + 外部内容 FTS。"""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE ast_index(file_path TEXT PRIMARY KEY, content_hash TEXT);
        CREATE TABLE ast_symbol_rows(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, kind TEXT NOT NULL, file_path TEXT NOT NULL,
            language TEXT NOT NULL, line INTEGER NOT NULL DEFAULT 0,
            end_line INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE ast_symbol_projection_state(
            file_path TEXT PRIMARY KEY, content_hash TEXT NOT NULL,
            symbol_count INTEGER NOT NULL CHECK(symbol_count >= 0),
            projection_digest TEXT NOT NULL);
        CREATE VIRTUAL TABLE ast_symbols_fts USING fts5(
            name, kind, file_path, language,
            content='ast_symbol_rows', content_rowid='id',
            tokenize='porter unicode61');
        CREATE TABLE ast_cache_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    return conn


def _fts_docsize(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM ast_symbols_fts_docsize").fetchone()[0]


def test_converge_symbol_projection_repairs_internal_residue():
    """dogfood 2026-11-09：陈旧行 / 缺状态 / 孤儿 FTS 是三种可收敛的内部残余。

    迁移后的旧缓存会同时带着它们，`symbol_projection_is_exact` 因此永远为假，
    于是每次索引都重写全部文件。收敛只动这三类残余，不重写参考行。
    """
    from tree_sitter_analyzer.index_symbol_projection import (
        converge_symbol_projection,
        upsert_symbol_projection_state,
    )

    conn = _projection_fixture_conn()
    conn.execute("INSERT INTO ast_index VALUES ('a.py', 'h1')")
    # 解析失败/空文件：在 ast_index 里，但没有任何符号行与状态
    conn.execute("INSERT INTO ast_index VALUES ('broken.swift', 'h2')")
    conn.execute(
        "INSERT INTO ast_symbol_rows(name, kind, file_path, language, line, end_line) "
        "VALUES ('a', 'function', 'a.py', 'python', 1, 2)"
    )
    # 陈旧行：文件已不在 ast_index 中
    conn.execute(
        "INSERT INTO ast_symbol_rows(name, kind, file_path, language, line, end_line) "
        "VALUES ('gone', 'function', 'gone.py', 'python', 3, 4)"
    )
    upsert_symbol_projection_state(conn, "a.py")
    # FTS 与参考行同步一条，再加一条只存在于 FTS 的孤儿行
    conn.execute(
        "INSERT INTO ast_symbols_fts(rowid, name, kind, file_path, language) "
        "SELECT id, name, kind, file_path, language FROM ast_symbol_rows ORDER BY id"
    )
    conn.execute(
        "INSERT INTO ast_symbols_fts(rowid, name, kind, file_path, language) "
        "VALUES (999, 'ghost', 'function', 'gone.py', 'python')"
    )
    assert _fts_docsize(conn) == 3
    assert conn.execute("SELECT COUNT(*) FROM ast_symbol_rows").fetchone()[0] == 2

    assert converge_symbol_projection(conn, require_fts=True) is True

    assert conn.execute(
        "SELECT file_path FROM ast_symbol_rows ORDER BY file_path"
    ).fetchall() == [("a.py",)]
    assert conn.execute(
        "SELECT file_path FROM ast_symbol_projection_state ORDER BY file_path"
    ).fetchall() == [("a.py",), ("broken.swift",)]
    assert _fts_docsize(conn) == 1
    # 幂等：第二次没有可收敛的残余
    assert converge_symbol_projection(conn, require_fts=True) is False


def test_convergence_requires_the_projection_tables():
    """没有投影表的连接不参与收敛（预投影/最小 fixture 保持原样）。"""
    from tree_sitter_analyzer.index_symbol_projection import (
        converge_symbol_projection,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path TEXT)")

    assert converge_symbol_projection(conn, require_fts=True) is False


@pytest.mark.parametrize("first_outcome", ["raise", "returns_false"])
def test_failed_convergence_certification_falls_back_to_a_full_repair(
    engine, monkeypatch, first_outcome
):
    """收敛后认证失败（抛错或不认账）都必须退回全量修复。"""
    engine.index_project(workers=0)
    conn = engine.get_conn()
    conn.execute(
        "DELETE FROM ast_symbol_projection_state WHERE file_path = "
        "(SELECT file_path FROM ast_index ORDER BY file_path LIMIT 1)"
    )
    conn.commit()

    calls = {"n": 0}

    def _fail_first(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            if first_outcome == "raise":
                raise RuntimeError("certification failed")
            return False
        return False

    monkeypatch.setattr(
        "tree_sitter_analyzer.index_snapshot_symbols.ensure_symbol_rows_backfilled",
        _fail_first,
    )

    stats = engine.index_project(workers=0)

    # 退回全量投影修复：每个文件都重新走写方路径。
    assert stats["indexed"] == 2
    assert stats["cached"] == 0


def test_force_rebuild_skips_convergence_and_rewrites_every_file(engine):
    """force 语义是「忽略缓存重建」：不先收敛，直接走全量重写。"""
    engine.index_project(workers=0)

    stats = engine.index_project(force=True, workers=0)

    assert (stats["mode_used"], stats["indexed"], stats["cached"]) == ("full", 2, 0)
