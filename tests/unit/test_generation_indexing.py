"""默认索引版本切换、失败隔离与读取绑定契约。"""

import os
import sqlite3
import time
from pathlib import Path

import pytest


@pytest.fixture
def project_root(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.py").write_text(
        "def hello(): return 1\ndef goodbye(): return hello()\n", encoding="utf-8"
    )
    return str(tmp_path)


class TestDefaultGenerations:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "operation",
        ["index_file", "index_project", "invalidate", "backfill_cross_file_edges"],
    )
    async def test_explicit_mutation_keeps_previous_generation_unchanged(
        self, project_root, operation
    ):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.cache.generation_routing import resolve_index_location
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        build = await CodeGraphFullIndexTool(project_root).execute({"mode": "full"})
        assert build["success"] is True
        before = resolve_index_location(project_root)
        parent = sqlite3.connect(before.path.as_uri() + "?mode=ro", uri=True)
        cache = ASTCache(project_root)
        try:
            previous_rows = tuple(parent.iterdump())
            source = Path(project_root) / "src" / "main.py"
            if operation in {"index_file", "index_project"}:
                source.write_text("def replaced(): return 5\n", encoding="utf-8")
            if operation == "index_file":
                assert cache.index_file(str(source))["status"] == "indexed"
            elif operation == "index_project":
                assert cache.index_project()["errors"] == 0
            elif operation == "invalidate":
                assert cache.invalidate(str(source)) is True
            else:
                cache.backfill_cross_file_edges()
            after = resolve_index_location(project_root)
            assert after.selector != before.selector
            assert tuple(parent.iterdump()) == previous_rows
            assert cache.db_path == str(after.path)
            expected = (
                []
                if operation == "invalidate"
                else (
                    ["replaced"]
                    if operation in {"index_file", "index_project"}
                    else ["goodbye", "hello"]
                )
            )
            assert sorted(row["name"] for row in cache.get_functions()) == expected
        finally:
            cache.close()
            parent.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation", ["sync", "index_project"])
    async def test_old_candidate_is_rejected_through_default_write_api(
        self, project_root, operation
    ):
        # 2026-09-09：默认入口不能给旧候选重新绑定最新父版本的发布权限。
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.cache.generation_store import Superseded
        from tree_sitter_analyzer.incremental_sync import IncrementalSync
        from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool(project_root)
        first = await tool.execute({"mode": "full"})
        assert first["success"] is True
        scope = make_source_scope_descriptor()
        candidate = tool._build_candidate_snapshot(
            scope.certification_max_files, scope.effective_excludes
        )
        second = await tool.execute({"mode": "full"})
        assert second["success"] is True
        cache = ASTCache(project_root)
        try:
            before = tuple(cache.get_conn().iterdump())
            write = (
                IncrementalSync(cache).sync
                if operation == "sync"
                else cache.index_project
            )
            with pytest.raises(Superseded):
                write(
                    candidate_snapshot=candidate,
                    exclude_patterns=scope.effective_excludes,
                    source_scope=scope,
                )
            assert tuple(cache.get_conn().iterdump()) == before
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_full_index_publishes_generation_used_by_default_cache(
        self, project_root
    ):
        # 2026-09-09：正式入口必须同时切换写入与读取，不能只验证独立存储原型。

        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.cache.generation_routing import resolve_index_location
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool(project_root=project_root)
        result = await tool.execute({"mode": "full", "max_files": 10})
        assert result["success"] is True
        assert result["scope_complete"] is True
        location = resolve_index_location(project_root)
        assert location.published is True
        cache = ASTCache(project_root)
        try:
            assert Path(cache.db_path) == location.path
            assert (
                cache.get_conn().execute("SELECT count(*) FROM ast_index").fetchone()[0]
                == 1
            )
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                cache.get_conn().execute("DELETE FROM ast_index")
        finally:
            cache.close()


@pytest.mark.asyncio
async def test_status_path_remains_bound_when_new_generation_is_published(
    tmp_path, monkeypatch
):
    # 2026-09-09：组装响应期间发布新版本，不得把旧快照标成新路径。
    from tree_sitter_analyzer import index_status_response as response
    from tree_sitter_analyzer.cache.generation_indexing import project_store
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "a.py").write_text("def saved(): return 1\n", encoding="utf-8")
    assert (await CodeGraphFullIndexTool(str(tmp_path)).execute({"mode": "full"}))[
        "published"
    ] is True
    previous = resolve_index_path(str(tmp_path))
    original = response.index_snapshot.read_snapshot_stats

    def publish_after_read(*args, **kwargs):
        stats = original(*args, **kwargs)
        project_store(str(tmp_path), make_source_scope_descriptor()).sync()
        return stats

    monkeypatch.setattr(
        response.index_snapshot, "read_snapshot_stats", publish_after_read
    )
    result = response.build_index_status_response(
        str(tmp_path), "json", include_lag=False
    )
    assert result["cache_path"] == str(previous)
    assert resolve_index_path(str(tmp_path)) != previous
    assert result["completeness"] == "complete"
    assert result["total_files"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["begin", "publish"])
async def test_publication_failure_preserves_parent_and_returns_error(
    project_root, monkeypatch, phase
):
    # 2026-09-09：构建前后失败都必须保留父版本，不能报告已发布。
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
    from tree_sitter_analyzer.cache.generation_store import GenerationStore
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    tool = CodeGraphFullIndexTool(project_root)
    assert (await tool.execute({"mode": "full"}))["published"] is True
    parent = resolve_index_path(project_root)
    before = parent.read_bytes()

    def fail(*args):
        raise OSError("publication failed")

    monkeypatch.setattr(GenerationStore, phase, fail)
    result = await tool.execute({"mode": "full"})
    assert (result["success"], result["published"], result["phase"]) == (
        False,
        False,
        "generation_publication",
    )
    assert result["error"] == "OSError: publication failed"
    assert resolve_index_path(project_root) == parent
    assert parent.read_bytes() == before


@pytest.mark.asyncio
async def test_failed_explicit_write_discards_private_changes(project_root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache.generation_indexing import mutate_published_cache
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    assert (await CodeGraphFullIndexTool(project_root).execute({"mode": "full"}))[
        "published"
    ] is True
    cache = ASTCache(project_root)
    try:
        previous = cache.db_path
        before = tuple(cache.get_conn().iterdump())

        def partial(writable):
            writable.get_conn().execute("DELETE FROM ast_index")
            writable.get_conn().commit()
            return {"errors": 1}

        assert mutate_published_cache(cache, partial) == {"errors": 1}
        assert cache.db_path == previous
        assert tuple(cache.get_conn().iterdump()) == before
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_direct_sync_owns_candidate_and_publishes_new_version(project_root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    assert (await CodeGraphFullIndexTool(project_root).execute({"mode": "full"}))[
        "published"
    ] is True
    cache = ASTCache(project_root)
    try:
        before = cache.db_path
        source = Path(project_root) / "src/main.py"
        source.write_text("def changed(): return 1\n", encoding="utf-8")
        scope = make_source_scope_descriptor()
        result = IncrementalSync(cache).sync(
            source_scope=scope, exclude_patterns=scope.effective_excludes
        )
        assert result.updated_files == 1
        assert result.scope_complete is True
        assert cache.db_path != before
        assert [row["name"] for row in cache.get_functions()] == ["changed"]
    finally:
        cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("part", ["storage", "generation", "selector"])
async def test_invalid_published_path_cannot_be_read_or_rebuilt(project_root, part):
    from tree_sitter_analyzer.cache.generation_routing import (
        generation_storage_path,
        resolve_index_path,
    )
    from tree_sitter_analyzer.cache.generation_selector import InvalidGenerationSelector
    from tree_sitter_analyzer.index_snapshot import _capture_existing_snapshot
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    tool = CodeGraphFullIndexTool(project_root)
    assert (await tool.execute({"mode": "full"}))["published"] is True
    database = resolve_index_path(project_root)
    storage = generation_storage_path(project_root)
    target = {
        "storage": storage,
        "generation": database.parent,
        "selector": storage / "active.json",
    }[part]
    target.rename(target.with_name(target.name + ".displaced"))
    target.write_text("invalid", encoding="utf-8")
    assert (
        _capture_existing_snapshot(project_root).reason
        == "INDEX_GENERATION_SELECTOR_INVALID"
    )
    with pytest.raises((InvalidGenerationSelector, OSError)):
        resolve_index_path(project_root)
    result = await tool.execute({"mode": "full"})
    assert result["success"] is False
    assert result["published"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["pinned", "wal"])
async def test_snapshot_capture_rejects_publication_at_final_binding(
    project_root, monkeypatch, backend
):
    # 2026-09-09：读取期间选择器切换必须拒绝混合身份，即使源码没有变化。
    from tree_sitter_analyzer import index_snapshot as owner
    from tree_sitter_analyzer.cache.generation_indexing import project_store
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    assert (await CodeGraphFullIndexTool(project_root).execute({"mode": "full"}))[
        "published"
    ] is True
    previous = resolve_index_path(project_root)
    store = project_store(project_root, make_source_scope_descriptor())
    prepared = store.prepare(store.capture())
    if backend == "pinned":
        if os.name != "posix":
            pytest.skip("tracked: pinned descriptor backend requires POSIX")
        # 密封库的空 WAL 可被 SQLite 清理；此处显式进入无 WAL 的句柄路径。
        wal = previous.with_name("index.db-wal")
        if wal.exists():
            assert wal.read_bytes() == b""
            wal.unlink()
        original = owner._open_bound_database

        def open_then_publish(*args):
            handles = original(*args)
            store.publish(prepared)
            return handles

        monkeypatch.setattr(owner, "_open_bound_database", open_then_publish)
        result = owner._capture_existing_snapshot(project_root)
    else:
        original = owner.REGISTRY.ensure_capacity
        calls = []

        def capacity_then_publish(*args):
            result = original(*args)
            calls.append(True)
            if len(calls) == 2:
                store.publish(prepared)
            return result

        monkeypatch.setattr(owner.REGISTRY, "ensure_capacity", capacity_then_publish)
        result = owner._capture_wal_snapshot(
            project_root, str(previous), pin=False, deadline=time.monotonic() + 10
        )
    assert result.completeness == "unknown"
    assert result.reason == "CONCURRENT_WRITER"


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["completed", "unreadable"])
async def test_post_publication_error_reports_actual_visibility(
    project_root, monkeypatch, damage
):
    from tree_sitter_analyzer.cache.generation_store import GenerationStore
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    original = GenerationStore.publish

    def publish_then_fail(store, prepared):
        original(store, prepared)
        if damage == "unreadable":
            store.selector_path.write_bytes(b"invalid")
        raise OSError("post-publication fault")

    monkeypatch.setattr(GenerationStore, "publish", publish_then_fail)
    result = await CodeGraphFullIndexTool(project_root).execute({"mode": "full"})
    assert result["success"] is False
    assert result["published"] is (True if damage == "completed" else None)
    assert result["phase"] == "generation_publication"


def test_derived_mutation_rejects_nondefault_legacy_path(project_root):
    from tree_sitter_analyzer.cache.generation_indexing import mutate_index_path

    path = Path(project_root) / "unrelated.db"
    with pytest.raises(ValueError, match="INDEX_GENERATION_PATH_MISMATCH"):
        mutate_index_path(project_root, path, lambda _: pytest.fail("不得运行写入"))
    assert path.exists() is False
