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


def test_certified_converged_noop_index_skips_the_backfills(engine):
    """认证通过 + 已收敛 + 无变化：回填重算的是同样的边，直接跳过。"""
    from tree_sitter_analyzer.cache.indexer import post_index_backfill

    engine.index_project(workers=0)
    stats: dict = {"indexed": 0, "cached": 2}

    post_index_backfill(engine, stats)

    assert (stats["backfill_skipped"], stats["backfill_errors"]) == (
        "CERTIFIED_CONVERGED",
        0,
    )
    assert "synapse_backfill" not in stats


def test_a_changed_file_still_runs_the_backfills(engine):
    """有文件变化时照旧回填：这是调用图自愈的唯一入口。"""
    from tree_sitter_analyzer.cache.indexer import post_index_backfill

    engine.index_project(workers=0)
    stats: dict = {"indexed": 1}

    post_index_backfill(engine, stats)

    assert "backfill_skipped" not in stats
    assert "backfill_errors" in stats


def test_a_converged_stable_failure_record_skips_the_backfills(engine, monkeypatch):
    """只差已记录稳定失败（#1671/#1735）时同样可跳过：内容确实收敛过。"""
    import tree_sitter_analyzer.cache.stable_failures as stable_failures
    from tree_sitter_analyzer.cache.indexer import post_index_backfill

    monkeypatch.setattr(
        stable_failures,
        "converged_except_stable_failures",
        lambda conn, parent=None: True,
    )
    # 夹具本身是可认证的；把认证分支关掉，专门验证第二条证据。
    monkeypatch.setattr(
        "tree_sitter_analyzer.cache.indexer._resolution_is_certified",
        lambda cache, conn: False,
    )
    engine.index_project(workers=0)
    stats: dict = {"indexed": 0}

    post_index_backfill(engine, stats)

    assert (stats["backfill_skipped"], stats["backfill_errors"]) == (
        "CONVERGED_STABLE_FAILURES",
        0,
    )


def test_without_any_convergence_evidence_the_backfills_run(engine, monkeypatch):
    """既没认证也没收敛记录时照旧回填（#1253 自愈路径）。"""
    import tree_sitter_analyzer.cache.stable_failures as stable_failures
    from tree_sitter_analyzer.cache.indexer import post_index_backfill

    monkeypatch.setattr(
        stable_failures,
        "converged_except_stable_failures",
        lambda conn, parent=None: False,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.cache.indexer._resolution_is_certified",
        lambda cache, conn: False,
    )
    engine.index_project(workers=0)
    stats: dict = {"indexed": 0}

    post_index_backfill(engine, stats)

    assert "backfill_skipped" not in stats
    assert "backfill_errors" in stats


def test_zero_change_fast_path_hint_points_at_one_force_run():
    """缺记录的零变化运行 → 提示一次 force 即可进入快路径。"""
    from tree_sitter_analyzer.cache.zero_change_hint import (
        zero_change_fast_path_hint,
    )

    hint = zero_change_fast_path_hint({"indexed": 0, "errors": 3})

    assert hint is not None
    assert "--ast-cache-force" in hint
    assert "9.08 s" in hint and "0.72-0.86 s" in hint


def test_zero_change_fast_path_hint_stays_silent_when_it_does_not_apply():
    from tree_sitter_analyzer.cache.zero_change_hint import (
        zero_change_fast_path_hint,
    )

    assert (
        zero_change_fast_path_hint(
            {"indexed": 0, "errors": 3, "backfill_skipped": "CERTIFIED_CONVERGED"}
        ),
        zero_change_fast_path_hint({"indexed": 5, "errors": 3}),
        zero_change_fast_path_hint({"indexed": 0, "errors": 0}),
        zero_change_fast_path_hint(
            {"indexed": 0, "errors": 3, "stable_failures_recorded": 3}
        ),
    ) == (None, None, None, None)


def test_a_ladybug_invalidation_failure_does_not_block_a_full_rebuild(
    engine, monkeypatch
):
    """镜像失效失败只记日志：强制重建照常完成。"""

    def _explode(*args, **kwargs):
        raise RuntimeError("mirror unavailable")

    # 该名字在 runner 内部以局部 import 使用，patch 到 indexer 才是真正生效的位置。
    import tree_sitter_analyzer.cache.indexer as indexer_module

    monkeypatch.setattr(indexer_module, "_invalidate_ladybug", _explode)

    result = engine.index_project(force=True, workers=0)

    assert (result["indexed"], result["errors"]) == (2, 0)


def test_an_unreadable_convergence_record_means_the_backfills_run(engine, monkeypatch):
    """读收敛记录抛异常时按「判断不了」处理：照旧回填，不让异常冒到索引。"""
    import tree_sitter_analyzer.cache.stable_failures as stable_failures
    from tree_sitter_analyzer.cache.indexer import _noop_skip_reason

    def _explode(*args, **kwargs):
        raise RuntimeError("record unreadable")

    monkeypatch.setattr(
        "tree_sitter_analyzer.cache.indexer._resolution_is_certified",
        lambda cache, conn: False,
    )
    monkeypatch.setattr(stable_failures, "converged_except_stable_failures", _explode)

    assert _noop_skip_reason(engine, engine._get_conn()) is None


def test_an_unreadable_call_graph_marker_means_not_certified(engine, monkeypatch):
    """读取调用图标记抛异常 → 视为未认证（照旧回填），不冒泡。"""
    from tree_sitter_analyzer.cache import indexer as indexer_module

    def _explode(*args, **kwargs):
        raise RuntimeError("marker unreadable")

    monkeypatch.setattr(engine, "call_graph_built", _explode)

    assert indexer_module._resolution_is_certified(engine, engine._get_conn()) is False


def _record_db(path):
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ast_cache_metadata (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def test_a_zero_change_generation_inherits_the_parent_record(tmp_path):
    """零变化世代继承父版本记录：内容没变，记录的 (文件,摘要,原因) 仍成立。"""
    from tree_sitter_analyzer.cache import stable_failures

    root = str(tmp_path)
    parent_conn = _record_db(tmp_path / "parent.db")
    assert stable_failures.issue_record(
        parent_conn,
        project_root=root,
        scope="full",
        extractor_version=stable_failures.current_extractor_version(),
        failures=(
            stable_failures.StableFailure(
                "a.lua", "a" * 64, "LUA grammar not installed"
            ),
        ),
    )
    child_conn = _record_db(tmp_path / "child.db")

    inherited = stable_failures.inherit_record(
        child_conn,
        tmp_path / "parent.db",
        project_root=root,
        scope="full",
        extractor_version=stable_failures.current_extractor_version(),
    )

    record = stable_failures.read_record(child_conn)
    assert (len(inherited or ()), record is not None) == (1, True)
    assert [failure.file for failure in record.failures] == ["a.lua"]


def test_inheritance_needs_a_converged_parent_record(tmp_path):
    """父版本没有记录 / 版本不符时绝不继承。"""
    from tree_sitter_analyzer.cache import stable_failures

    root = str(tmp_path)
    empty_parent = _record_db(tmp_path / "empty.db")
    child = _record_db(tmp_path / "child.db")

    inherited = stable_failures.inherit_record(
        child,
        tmp_path / "empty.db",
        project_root=root,
        scope="full",
        extractor_version=stable_failures.current_extractor_version(),
    )

    assert (inherited, stable_failures.read_record(child)) == (None, None)
    assert stable_failures.read_record(empty_parent) is None


def test_only_a_zero_change_run_may_inherit_the_record():
    from tree_sitter_analyzer.cache.index_project_runner import _is_zero_change_run

    assert (
        _is_zero_change_run({"indexed": 0, "removed": 0, "backfill_errors": 0}),
        _is_zero_change_run({"indexed": 1}),
        _is_zero_change_run({"indexed": 0, "removed": 2}),
        _is_zero_change_run({"indexed": 0, "changed_during_run": 1}),
        _is_zero_change_run({"indexed": 0, "backfill_errors": 1}),
    ) == (True, False, False, False, False)
