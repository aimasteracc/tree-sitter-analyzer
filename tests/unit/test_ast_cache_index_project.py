"""#1376：test_ast_cache_index_project 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

from unittest.mock import patch

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import (
    _BACKFILL_ROUTES,
    _run_backfill_with_route_result,
)
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
engine = _fixtures.engine
method_project = _fixtures.method_project


class TestIndexProject:
    def test_index_project(self, cache):
        result = cache.index_project()
        # #1625：增量运行改由捕获的候选快照驱动，total_files 计入快照中的全部
        # 候选条目（main.py、util.js 与不受支持的 readme.md），重新钉为 3。
        assert result["total_files"] == 3
        assert result["indexed"] == 2

    def test_index_project_language_filter_indexes_only_matching(self, cache):
        """#1018：language_filter 只遍历指定语言的文件。夹具项目包含 main.py 和 util.js；readme.md 的扩展名不受支持，不计入数量。language_filter=python 时只索引一个 .py 文件，.js 在解析前被跳过，且被排除语言不会产生解析错误。"""
        result = cache.index_project(language_filter="python")
        assert result["indexed"] == 1
        assert result["skipped"] == 1
        assert result["errors"] == 0

    def test_index_project_cached(self, cache):
        cache.index_project()
        result = cache.index_project()
        assert result["cached"] == 2

    def test_index_project_reindexes_stale_extractor_version(self, engine):
        engine.index_project(workers=0)
        conn = engine._get_conn()
        conn.execute("UPDATE ast_index SET extractor_version = 0")
        conn.commit()

        result = engine.index_project(workers=0)

        assert result["indexed"] == 2
        assert result["cached"] == 0

    def test_index_project_force(self, cache):
        cache.index_project()
        result = cache.index_project(force=True)
        assert result["indexed"] == 2

    def test_force_rebuild_skips_per_file_resolution_invalidation(self, cache):
        """全量重建已先清空全部边，不能再为每个文件扫描逐步增长的边表。"""
        with patch(
            "tree_sitter_analyzer.cache.write._reset_incoming_edge_resolutions"
        ) as reset:
            result = cache.index_project(force=True, workers=0)

        assert result["indexed"] == 2
        reset.assert_not_called()

    def test_index_project_max_files(self, cache):
        result = cache.index_project(max_files=1)
        # #1625：快照驱动后上限如实标为截断，只索引一个文件（截断时不推断删除）。
        assert (result["indexed"], result["truncated_by_max_files"]) == (1, True)

    def test_index_project_workers_field_in_stats(self, cache):
        """PERF-4：统计中包含最终生效的 worker 数量。"""
        result = cache.index_project(workers=0)
        assert "workers" in result
        assert result["workers"] == 0

    def test_auto_workers_start_at_64_candidates(self, monkeypatch):
        """只有能够摊薄 spawn 开销时才启动自动进程池。"""
        # 2026-07-15 基准：Windows 上 50 个文件串行耗时 5.77 秒，自动并行耗时 9.55 秒。
        monkeypatch.delenv("TSA_INDEX_WORKERS", raising=False)
        monkeypatch.setattr("tree_sitter_analyzer.ast_cache.os.cpu_count", lambda: 8)

        assert ASTCache._resolve_worker_count(None, list(range(63))) == 0
        # One worker per 64 files (at least 2): spawn start-up is paid per worker.
        assert ASTCache._resolve_worker_count(None, list(range(64))) == 2
        assert ASTCache._resolve_worker_count(None, list(range(213))) == 3
        # Capped at cpu_count - 1.
        assert ASTCache._resolve_worker_count(None, list(range(1191))) == 7

    def test_explicit_worker_counts_are_not_scaled(self, monkeypatch):
        monkeypatch.delenv("TSA_INDEX_WORKERS", raising=False)
        assert ASTCache._resolve_worker_count(12, list(range(64))) == 12
        monkeypatch.setenv("TSA_INDEX_WORKERS", "9")
        assert ASTCache._resolve_worker_count(None, list(range(64))) == 9

    def test_index_project_serial_and_parallel_agree(self, tmp_project):
        """PERF-4 正确性：并行和串行路径必须产生相同的索引数量和 SQLite 内容。"""
        from tree_sitter_analyzer.ast_cache import ASTCache

        db_serial = tmp_project / "ser.db"
        db_parallel = tmp_project / "par.db"
        for db in (db_serial, db_parallel):
            if db.exists():
                db.unlink()

        serial_cache = ASTCache(str(tmp_project), db_path=str(db_serial))
        serial_result = serial_cache.index_project(workers=0)

        parallel_cache = ASTCache(str(tmp_project), db_path=str(db_parallel))
        # 两个 worker 足以覆盖 spawn 和 IPC 路径。
        parallel_result = parallel_cache.index_project(workers=2)

        assert serial_result["indexed"] == parallel_result["indexed"]
        assert serial_result["errors"] == parallel_result["errors"]

        # 比较真实的行集合：文件、content_hash 和
        # symbols 数据都必须一致；这里在进程内执行以避免启动 worker。
        serial_conn = serial_cache._get_conn()
        parallel_conn = parallel_cache._get_conn()
        s_rows = sorted(
            tuple(r)
            for r in serial_conn.execute(
                "SELECT file_path, content_hash, language FROM ast_index"
            ).fetchall()
        )
        p_rows = sorted(
            tuple(r)
            for r in parallel_conn.execute(
                "SELECT file_path, content_hash, language FROM ast_index"
            ).fetchall()
        )
        assert s_rows == p_rows

        symbol_sql = (
            "SELECT name, kind, file_path, language, line, end_line "
            "FROM ast_symbol_rows ORDER BY file_path, name, kind, line"
        )
        assert [tuple(r) for r in serial_conn.execute(symbol_sql).fetchall()] == [
            tuple(r) for r in parallel_conn.execute(symbol_sql).fetchall()
        ]

        # B1.3：CALLS 行位于统一的 edges 表；file_path 表示
        # 调用方文件，等同于旧 caller_file；callee_line 表示调用位置。
        edge_sql = (
            "SELECT caller_name, file_path AS caller_file, caller_line, callee_name, "
            "callee_full, callee_line, file_path, language "
            "FROM edges WHERE kind = 'calls' "
            "ORDER BY file_path, caller_name, callee_name, callee_line"
        )
        assert [tuple(r) for r in serial_conn.execute(edge_sql).fetchall()] == [
            tuple(r) for r in parallel_conn.execute(edge_sql).fetchall()
        ]

    def test_index_project_env_workers_override(self, cache, monkeypatch):
        """PERF-4：TSA_INDEX_WORKERS 环境变量覆盖 workers keyword 参数。"""
        monkeypatch.setenv("TSA_INDEX_WORKERS", "0")
        # 显式传入 workers=4；环境变量优先并强制串行。
        result = cache.index_project(workers=4)
        assert result["workers"] == 0

    def test_index_project_tolerates_knowledge_graph_build_failure(
        self, cache, monkeypatch
    ):
        monkeypatch.setattr(
            "tree_sitter_analyzer.knowledge_graph.builder.KnowledgeGraphBuilder.build",
            lambda self: (_ for _ in ()).throw(RuntimeError("graph failed")),
        )

        result = cache.index_project(workers=0)

        assert result["indexed"] == 2
        assert "knowledge_graph" not in result

    def test_index_project_reports_unresolved_reference_backfill(
        self, engine, monkeypatch
    ):
        monkeypatch.setattr(
            engine,
            "_run_unresolved_refs_backfill",
            lambda: {"resolved": 3, "remaining": 1},
        )

        result = engine.index_project(workers=0)

        assert result["unresolved_refs_backfill"] == {
            "resolved": 3,
            "remaining": 1,
        }

    def test_index_project_omits_empty_unresolved_backfill(self, engine, monkeypatch):
        monkeypatch.setattr(engine, "_run_unresolved_refs_backfill", lambda: None)

        result = engine.index_project(workers=0)

        assert result["indexed"] == 2
        assert result["unresolved_refs_backfill"] is None
        assert result["backfill_errors"] == 1

    def test_index_project_tolerates_unresolved_backfill_failure(
        self, engine, monkeypatch
    ):
        def fail_unresolved_backfill():
            raise RuntimeError("unresolved failed")

        monkeypatch.setattr(
            engine,
            "_run_unresolved_refs_backfill",
            fail_unresolved_backfill,
        )

        result = engine.index_project(workers=0)

        assert result["indexed"] == 2
        assert "unresolved_refs_backfill" not in result
        assert result["backfill_errors"] == 1
        manifest_count = (
            engine.get_conn()
            .execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest")
            .fetchone()[0]
        )
        assert manifest_count == 0

    def test_index_project_tolerates_resolution_convergence_failure(
        self, cache, monkeypatch
    ):
        def fail_mark_resolution_converged(conn):
            raise RuntimeError("convergence failed")

        monkeypatch.setattr(
            "tree_sitter_analyzer.cache.unresolved.mark_resolution_converged",
            fail_mark_resolution_converged,
        )

        result = cache.index_project(workers=0)

        assert result["indexed"] == 2
        assert "knowledge_graph" not in result

    def test_index_project_skips_activation_by_default(self, cache, monkeypatch):
        """大型仓库的暖缓存构建默认不能逐文件运行 git history。"""
        monkeypatch.delenv("TSA_INDEX_ACTIVATION", raising=False)
        with patch(
            "tree_sitter_analyzer.git_activation.compute_symbol_activation"
        ) as compute:
            result = cache.index_project(workers=0)

        assert result["activation_enabled"] is False
        compute.assert_not_called()
        conn = cache._get_conn()
        activation_rows = conn.execute(
            "SELECT COUNT(*) FROM ast_symbol_activation"
        ).fetchone()[0]
        assert activation_rows == 0

    def test_index_project_activation_opt_in_via_argument(self, cache, monkeypatch):
        monkeypatch.delenv("TSA_INDEX_ACTIVATION", raising=False)
        with patch(
            "tree_sitter_analyzer.git_activation.compute_symbol_activation",
            return_value=[],
        ) as compute:
            result = cache.index_project(workers=0, include_activation=True)

        assert result["activation_enabled"] is True
        assert compute.called

    def test_index_project_activation_opt_in_via_env(self, cache, monkeypatch):
        monkeypatch.setenv("TSA_INDEX_ACTIVATION", "1")
        with patch(
            "tree_sitter_analyzer.git_activation.compute_symbol_activation",
            return_value=[],
        ) as compute:
            result = cache.index_project(workers=0)

        assert result["activation_enabled"] is True
        assert compute.called


@pytest.mark.parametrize(("route", "key"), _BACKFILL_ROUTES)
def test_backfill_returned_errors_fail_certification(cache, monkeypatch, route, key):
    diagnostic = {"errors": 2, "detail": route}
    stats, converged = _run_backfill_with_route_result(
        cache, monkeypatch, route, diagnostic
    )

    assert stats[key] == diagnostic
    assert stats["backfill_errors"] == 1
    converged.assert_not_called()


@pytest.mark.parametrize(("route", "key"), _BACKFILL_ROUTES)
def test_backfill_none_fails_certification_and_is_preserved(
    cache, monkeypatch, route, key
):
    stats, converged = _run_backfill_with_route_result(cache, monkeypatch, route, None)

    assert key in stats
    assert stats[key] is None
    assert stats["backfill_errors"] == 1
    converged.assert_not_called()


@pytest.mark.parametrize(("route", "key"), _BACKFILL_ROUTES)
def test_backfill_nonmapping_fails_certification_and_is_preserved(
    cache, monkeypatch, route, key
):
    stats, converged = _run_backfill_with_route_result(
        cache, monkeypatch, route, ["unexpected"]
    )

    assert stats[key] == ["unexpected"]
    assert stats["backfill_errors"] == 1
    converged.assert_not_called()


@pytest.mark.parametrize(("route", "key"), _BACKFILL_ROUTES)
def test_backfill_exception_fails_certification(cache, monkeypatch, route, key):
    def fail():
        raise RuntimeError(route)

    for method, _key in _BACKFILL_ROUTES:
        monkeypatch.setattr(cache, method, lambda: {"errors": 0})
    monkeypatch.setattr(cache, route, fail)
    from tree_sitter_analyzer.cache.indexer import post_index_backfill

    stats = {}
    with patch(
        "tree_sitter_analyzer.cache.unresolved.mark_resolution_converged"
    ) as converged:
        post_index_backfill(cache, stats)

    assert key not in stats
    assert stats["backfill_errors"] == 1
    converged.assert_not_called()


_DELETION_PROJECT = {
    "target.py": "def target():\n    return 1\n",
    "caller_a.py": "from target import target\n\n\ndef use_a():\n    return target()\n",
    "caller_b.py": "from target import target\n\n\ndef use_b():\n    return target()\n",
    "other.py": "def other():\n    return 2\n",
}


async def _published_deletion_project(root):
    """#1625：四个文件的已认证项目；caller_b.py 调用 target.py 中的 target。"""
    from tree_sitter_analyzer.mcp.tools.index_facade import build_index_facade

    for rel, text in _DELETION_PROJECT.items():
        (root / rel).write_text(text, encoding="utf-8")
    full = await build_index_facade(str(root)).execute(
        {"action": "full", "mode": "full", "max_files": 50}
    )
    assert (full["success"], full["published"]) == (True, True)


async def _refresh_and_status(root, action="cache"):
    """执行公开增量刷新，再以全新 facade 读取 status（不复用进程内缓存）。"""
    from tree_sitter_analyzer.mcp.tools.index_facade import build_index_facade

    arguments = {"action": action}
    if action == "cache":
        arguments["mode"] = "index"
    refreshed = await build_index_facade(str(root)).execute(arguments)
    status = await build_index_facade(str(root)).execute({"action": "status"})
    return refreshed, status


async def _callers_of_target(root):
    from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade

    return await build_nav_facade(str(root)).execute(
        {"action": "callers", "symbol": "target"}
    )


class TestIncrementalRefreshPurgesDeletedFiles:
    """#1625：增量刷新必须清除已从磁盘删除的文件，而不是永远停在 SOURCE_INDEX_MISMATCH。"""

    @pytest.mark.asyncio
    async def test_status_file_count_drops_by_deleted_files(self, tmp_path):
        await _published_deletion_project(tmp_path)
        (tmp_path / "caller_b.py").unlink()
        (tmp_path / "other.py").unlink()

        _refreshed, status = await _refresh_and_status(tmp_path)

        assert (status["total_files"], status["completeness"]) == (2, "complete")

    @pytest.mark.asyncio
    async def test_deleted_file_is_no_longer_a_caller(self, tmp_path):
        await _published_deletion_project(tmp_path)
        (tmp_path / "caller_b.py").unlink()
        (tmp_path / "other.py").unlink()
        await _refresh_and_status(tmp_path)

        callers = await _callers_of_target(tmp_path)

        assert [(c["name"], c["file"]) for c in callers["callers"]] == [
            ("use_a", "caller_a.py")
        ]
        assert callers["source_evidence"]["reason"] == "SOURCE_REVALIDATION_SCOPED"

    @pytest.mark.asyncio
    async def test_refresh_reply_reports_removed_files(self, tmp_path):
        await _published_deletion_project(tmp_path)
        (tmp_path / "caller_b.py").unlink()
        (tmp_path / "other.py").unlink()

        refreshed, _status = await _refresh_and_status(tmp_path)

        assert (refreshed["removed"], refreshed["removed_files"]) == (
            2,
            ["caller_b.py", "other.py"],
        )
        assert refreshed["summary_line"].endswith("removed=2")

    @pytest.mark.asyncio
    async def test_rename_purges_old_path_and_indexes_new_one(self, tmp_path):
        await _published_deletion_project(tmp_path)
        (tmp_path / "caller_b.py").rename(tmp_path / "caller_c.py")

        refreshed, status = await _refresh_and_status(tmp_path)
        callers = await _callers_of_target(tmp_path)

        assert (refreshed["removed_files"], status["total_files"]) == (
            ["caller_b.py"],
            4,
        )
        assert [(c["name"], c["file"]) for c in callers["callers"]] == [
            ("use_a", "caller_a.py"),
            ("use_b", "caller_c.py"),
        ]

    @pytest.mark.asyncio
    async def test_sync_route_also_purges_deleted_files(self, tmp_path):
        await _published_deletion_project(tmp_path)
        (tmp_path / "caller_b.py").unlink()
        (tmp_path / "other.py").unlink()

        _refreshed, status = await _refresh_and_status(tmp_path, action="sync")

        assert (status["total_files"], status["completeness"]) == (2, "complete")

    @pytest.mark.asyncio
    async def test_language_scoped_refresh_points_to_force(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.ast_cache_index_view import (
            FORCE_REFRESH_STEP,
        )
        from tree_sitter_analyzer.mcp.tools.index_facade import build_index_facade

        await _published_deletion_project(tmp_path)
        (tmp_path / "caller_b.py").unlink()

        refreshed = await build_index_facade(str(tmp_path)).execute(
            {"action": "cache", "mode": "index", "language": "python"}
        )

        assert (refreshed["removed"], refreshed["agent_summary"]["next_step"]) == (
            None,
            FORCE_REFRESH_STEP,
        )
