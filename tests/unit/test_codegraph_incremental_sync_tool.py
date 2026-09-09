"""Tests for codegraph_incremental_sync MCP tool — content-hash diff re-indexing."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from tree_sitter_analyzer.cache.generation_routing import resolve_index_path
from tree_sitter_analyzer.incremental_sync import IncrementalSync, SyncResult
from tree_sitter_analyzer.index_snapshot_capability import strict_call_graph_marker
from tree_sitter_analyzer.indexing_candidate_materialization import (
    release_index_candidate_snapshot,
)
from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool
from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
    CodeGraphIncrementalSyncTool,
    _safe_close_cache,
)


@pytest.fixture
def tool():
    return CodeGraphIncrementalSyncTool()


@pytest.fixture
def tool_with_root(tmp_path):
    (tmp_path / "app.py").write_text("def foo():\n    pass\n")
    return CodeGraphIncrementalSyncTool(str(tmp_path))


class TestToolDefinition:
    def test_tool_name(self, tool):
        assert tool.get_tool_definition()["name"] == "codegraph_incremental_sync"

    def test_description_mentions_no_other(self, tool):
        desc = tool.get_tool_definition()["description"]
        assert "No other tool" in desc

    def test_schema_mode_enum(self, tool):
        mode = tool.get_tool_schema()["properties"]["mode"]
        assert set(mode["enum"]) == {"sync", "changes", "status"}

    def test_annotations_destructive(self, tool):
        hints = tool.get_tool_definition()["annotations"]
        assert hints["destructiveHint"] is True
        assert hints["readOnlyHint"] is False

    def test_schema_requires_positive_max_files(self, tool):
        assert tool.get_tool_schema()["properties"]["max_files"]["minimum"] == 1


class TestValidation:
    def test_valid_sync(self, tool):
        assert tool.validate_arguments({"mode": "sync"}) is True

    def test_valid_changes(self, tool):
        assert tool.validate_arguments({"mode": "changes"}) is True

    def test_valid_status(self, tool):
        assert tool.validate_arguments({"mode": "status"}) is True

    def test_invalid_mode_rejected(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "rebuild"})

    @pytest.mark.parametrize("value", [True, 0, -1])
    def test_invalid_max_files_rejected(self, tool, value):
        with pytest.raises(ValueError, match="max_files must be a positive integer"):
            tool.validate_arguments({"mode": "sync", "max_files": value})

    def test_omitted_max_files_is_normalized(self, tool):
        arguments = {"mode": "sync"}

        assert tool.validate_arguments(arguments) is True
        assert arguments["max_files"] == 20_000


@pytest.mark.asyncio
class TestExecute:
    async def test_status_no_project_root_returns_error(self, tool):
        result = await tool.execute({"mode": "status", "output_format": "json"})
        assert result["success"] is False

    async def test_status_on_empty_project(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "status", "output_format": "json"}
        )
        assert result["success"] is True

    async def test_changes_mode_preview(self, tool_with_root):
        result = await tool_with_root.execute(
            {"mode": "changes", "output_format": "json"}
        )
        assert result["success"] is True


class TestCacheLifecycle:
    def test_sync_uses_limit_for_cold_cache_warmup(self, tool_with_root):
        cache = MagicMock(project_root=tool_with_root.project_root)
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache) as ensure,
            patch.object(IncrementalSync, "sync", return_value=SyncResult()),
        ):
            tool_with_root._sync(7, "json")

        ensure.assert_called_once_with("json", max_files=7)

    def test_sync_closes_cache_after_success(self, tool_with_root):
        cache = MagicMock(project_root=tool_with_root.project_root)
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache),
            patch.object(IncrementalSync, "sync", return_value=SyncResult()),
        ):
            tool_with_root._sync(100, "json")

        cache.close.assert_called_once_with()

    def test_sync_closes_cache_after_exception(self, tool_with_root):
        cache = MagicMock(project_root=tool_with_root.project_root)
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache),
            patch.object(
                IncrementalSync,
                "sync",
                side_effect=RuntimeError("sync failed"),
            ),
        ):
            tool_with_root._sync(100, "json")

        cache.close.assert_called_once_with()

    def test_sync_closes_cache_after_sync_constructor_exception(self, tool_with_root):
        cache = MagicMock(project_root=tool_with_root.project_root)
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache),
            patch(
                "tree_sitter_analyzer.mcp.tools.incremental_sync_tool.IncrementalSync",
                side_effect=RuntimeError("constructor failed"),
            ),
        ):
            tool_with_root._sync(100, "json")

        cache.close.assert_called_once_with()

    def test_changes_closes_cache(self, tool_with_root):
        cache = MagicMock()
        with (
            patch.object(tool_with_root, "_ensure_cache", return_value=cache),
            patch.object(IncrementalSync, "get_changes", return_value={}),
        ):
            tool_with_root._changes("json")

        cache.close.assert_called_once_with()

    def test_status_closes_cache(self, tool_with_root):
        cache = MagicMock()
        cache.get_stats.return_value = {}
        with (
            patch(
                "tree_sitter_analyzer.ast_cache.ASTCache",
                return_value=cache,
            ),
            patch.object(IncrementalSync, "get_changes", return_value={}),
        ):
            tool_with_root._status("json")

        cache.close.assert_called_once_with()


def test_candidate_less_incremental_response_is_not_authoritative_success(
    tool_with_root,
):
    # PR #1253 review 3762603012: public sync has no frozen candidate evidence.
    cache = MagicMock(project_root=tool_with_root.project_root)
    live_walk = SyncResult(scope_complete=False)
    with (
        patch.object(tool_with_root, "_ensure_cache", return_value=cache),
        patch.object(IncrementalSync, "sync", return_value=live_walk),
    ):
        result = tool_with_root._sync(10, "json")

    assert (result["success"], result["verdict"], result["completeness"]) == (
        False,
        "WARN",
        "incomplete",
    )


def test_parse_failure_makes_incremental_response_non_success(tool_with_root):
    # PR #1253 thread 3761514130: missing parsed rows are not MCP success.
    cache = MagicMock(project_root=tool_with_root.project_root)
    parse_failure = SyncResult(errors=1, scope_complete=False)
    with (
        patch.object(tool_with_root, "_ensure_cache", return_value=cache),
        patch.object(IncrementalSync, "sync", return_value=parse_failure),
    ):
        result = tool_with_root._sync(10, "json")

    assert (result["success"], result["verdict"], result["completeness"]) == (
        False,
        "WARN",
        "incomplete",
    )


def test_manifest_stamp_failure_makes_incremental_response_non_success(
    tool_with_root,
):
    # PR #1253 thread 3761514130: failed certification is not MCP success.
    cache = MagicMock(project_root=tool_with_root.project_root)
    stamp_failure = SyncResult(
        scope_complete=False,
        manifest_certification_failed=True,
    )
    with (
        patch.object(tool_with_root, "_ensure_cache", return_value=cache),
        patch.object(IncrementalSync, "sync", return_value=stamp_failure),
    ):
        result = tool_with_root._sync(10, "json")

    assert (
        result["success"],
        result["verdict"],
        result["manifest_certification_failed"],
    ) == (False, "WARN", True)


def test_pipeline_warning_makes_incremental_response_non_success(tool_with_root):
    # PR #1253 review 3757240532: incomplete navigation is not an INFO success.
    cache = MagicMock(project_root=tool_with_root.project_root)
    pipeline_failure = SyncResult(errors=1, backfill_errors=1)
    pipeline_failure.details.append(
        {
            "stage": "cross_file",
            "considered": "backfill",
            "action": "backfill",
            "status": "warning",
            "reason": "BACKFILL_REPORTED_ERRORS",
        }
    )
    with (
        patch.object(tool_with_root, "_ensure_cache", return_value=cache),
        patch.object(IncrementalSync, "sync", return_value=pipeline_failure),
    ):
        result = tool_with_root._sync(10, "json")

    assert (result["success"], result["verdict"], result["backfill_errors"]) == (
        False,
        "WARN",
        1,
    )


@pytest_asyncio.fixture
async def indexed_pair(tmp_path):
    # 2026-09-07：真实无 Git 项目，禁止用伪造快照绕过公开入口。
    (tmp_path / "leaf.py").write_text("def leaf():\n    return 1\n", encoding="utf-8")
    (tmp_path / "service.py").write_text(
        "from leaf import leaf\n\ndef service():\n    return leaf()\n",
        encoding="utf-8",
    )
    assert (tmp_path / ".git").exists() is False
    result = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "incremental", "max_files": 2}
    )
    assert (result["success"], result["scope_complete"]) == (True, True)
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "counts", "paths"),
    [
        ("unchanged", (0, 0, 0, 2), ["leaf.py", "service.py"]),
        ("new", (1, 0, 0, 2), ["extra.py", "leaf.py", "service.py"]),
        ("update", (0, 1, 0, 1), ["leaf.py", "service.py"]),
        ("delete", (0, 1, 1, 0), ["service.py"]),
        ("rename_function", (0, 2, 0, 0), ["leaf.py", "service.py"]),
        ("rename_file", (1, 1, 1, 0), ["moved.py", "service.py"]),
    ],
)
async def test_public_sync_certifies_no_git_lifecycle(
    indexed_pair, operation, counts, paths
):
    # 2026-09-07：full-index 后的真实变更必须由 sync 重新认证。
    root = indexed_pair
    leaf = root / "leaf.py"
    service = root / "service.py"
    if operation == "new":
        (root / "extra.py").write_text("def extra():\n    return 3\n", encoding="utf-8")
    elif operation == "update":
        leaf.write_text("def leaf():\n    return 200\n", encoding="utf-8")
    elif operation == "delete":
        leaf.unlink()
        service.write_text("def service():\n    return 0\n", encoding="utf-8")
    elif operation == "rename_function":
        leaf.write_text("def leaf_v2():\n    return 1\n", encoding="utf-8")
        service.write_text(
            "from leaf import leaf_v2\n\ndef service():\n    return leaf_v2()\n",
            encoding="utf-8",
        )
    elif operation == "rename_file":
        leaf.rename(root / "moved.py")
        service.write_text(
            "from moved import leaf\n\ndef service():\n    return leaf()\n",
            encoding="utf-8",
        )

    result = await CodeGraphIncrementalSyncTool(str(root)).execute(
        {"mode": "sync", "max_files": 3}
    )
    assert (result["success"], result["verdict"], result["completeness"]) == (
        True,
        "INFO",
        "complete",
    )
    assert (
        tuple(
            result[key]
            for key in (
                "new_files",
                "updated_files",
                "deleted_files",
                "unchanged_files",
            )
        )
        == counts
    )
    assert (
        result["errors"],
        result["backfill_errors"],
        result["manifest_certification_failed"],
    ) == (0, 0, False)
    with closing(
        sqlite3.connect(resolve_index_path(root).as_uri() + "?mode=ro", uri=True)
    ) as conn:
        assert conn.execute(
            "SELECT file_path, content_hash FROM ast_index ORDER BY file_path"
        ).fetchall() == [
            (
                path,
                hashlib.sha256(
                    (root / path).read_text(encoding="utf-8").encode("utf-8")
                ).hexdigest(),
            )
            for path in paths
        ]
        assert conn.execute(
            "SELECT file_count FROM ast_index_snapshot_manifest"
        ).fetchall() == [(len(paths),)]
        assert strict_call_graph_marker(conn) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["truncated", "parse", "manifest"])
async def test_public_sync_failure_does_not_certify(indexed_pair, failure):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

    root = indexed_pair
    with closing(
        sqlite3.connect(resolve_index_path(root).as_uri() + "?mode=ro", uri=True)
    ) as conn:
        prior_path = resolve_index_path(root)
        prior_dump = list(conn.iterdump())
        prior_manifest = conn.execute(
            "SELECT * FROM ast_index_snapshot_manifest"
        ).fetchall()
    (root / "leaf.py").write_text("def leaf_v2():\n    return 2\n", encoding="utf-8")
    with (
        patch.object(
            ASTCache, "index_file", autospec=True, side_effect=ASTCache.index_file
        ) as index_file,
        patch(
            "tree_sitter_analyzer.index_snapshot_schema.stamp_full_index_manifest",
            wraps=stamp_full_index_manifest,
        ) as stamp,
    ):
        if failure == "parse":
            index_file.side_effect = RuntimeError("probe parse failure")
        elif failure == "manifest":
            stamp.side_effect = OSError("probe certification failure")
        result = await CodeGraphIncrementalSyncTool(str(root)).execute(
            {"mode": "sync", "max_files": 1 if failure == "truncated" else 2}
        )
    assert (result["success"], result["completeness"]) == (False, "incomplete")
    assert result["truncated_by_max_files"] is (failure == "truncated")
    assert result["manifest_certification_failed"] is (failure == "manifest")
    assert stamp.call_count == (1 if failure == "manifest" else 0)
    with closing(
        sqlite3.connect(resolve_index_path(root).as_uri() + "?mode=ro", uri=True)
    ) as conn:
        # 失败构建不得发布或修改旧版本；源码变化使旧清单失去当前认证。
        assert resolve_index_path(root) == prior_path
        assert list(conn.iterdump()) == prior_dump
        assert (
            conn.execute("SELECT * FROM ast_index_snapshot_manifest").fetchall()
            == prior_manifest
        )
        assert strict_call_graph_marker(conn) is True
    from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

    status = await CodeGraphStatusTool(str(root)).execute(
        {"access_mode": "read_existing"}
    )
    assert status["completeness"] != "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "discovery", "sync"])
async def test_public_sync_releases_real_candidate(indexed_pair, failure):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.indexing_snapshot import build_index_candidate_snapshot

    # 2026-09-07：构建失败必须经过真实入口，不能以提前返回冒充已覆盖清理路径。
    with (
        patch.object(
            ASTCache,
            "close",
            autospec=True,
            side_effect=ASTCache.close,
        ) as close,
        patch(
            "tree_sitter_analyzer.mcp.tools.incremental_sync_tool._safe_close_cache",
            wraps=_safe_close_cache,
        ) as owned_close,
        patch.object(
            CodeGraphFullIndexTool,
            "_build_candidate_snapshot",
            autospec=True,
            side_effect=CodeGraphFullIndexTool._build_candidate_snapshot,
        ) as build,
        patch(
            "tree_sitter_analyzer.mcp.tools.full_index_tool.build_index_candidate_snapshot",
            wraps=build_index_candidate_snapshot,
        ) as discover,
        patch.object(
            IncrementalSync,
            "sync",
            autospec=True,
            side_effect=IncrementalSync.sync,
        ) as sync,
        patch(
            "tree_sitter_analyzer.mcp.tools.incremental_sync_tool.release_index_candidate_snapshot",
            wraps=release_index_candidate_snapshot,
        ) as release,
    ):
        if failure == "discovery":
            discover.side_effect = RuntimeError("probe discovery failure")
        elif failure == "sync":
            sync.side_effect = RuntimeError("probe sync failure")
        result = await CodeGraphIncrementalSyncTool(str(indexed_pair)).execute(
            {"mode": "sync", "max_files": 2}
        )
    assert result["success"] is (failure is None)
    assert build.call_count == 1
    assert discover.call_count == 1
    owned_close.assert_called_once()
    cache = owned_close.call_args.args[0]
    # 旧实例析构也调用 close；只精确核验本次 sync 持有的真实 cache。
    assert sum(args.args[0] is cache for args in close.call_args_list) == 1
    assert cache.project_root == str(indexed_pair.resolve())
    assert release.call_count == (0 if failure == "discovery" else 1)
    if failure == "discovery":
        sync.assert_not_called()
        assert "probe discovery failure" in result["error"]
    if failure != "discovery":
        snapshot = release.call_args.args[0]
        assert snapshot is sync.call_args.kwargs["candidate_snapshot"]
        assert sorted(entry.rel_path for entry in snapshot.selected_entries) == [
            "leaf.py",
            "service.py",
        ]
        assert snapshot.max_files == sync.call_args.kwargs["max_files"] == 2


@pytest.mark.asyncio
async def test_public_sync_uses_full_index_default_exclusions(indexed_pair):
    root = indexed_pair
    corpus = root / "tests/golden/corpus_probe"
    corpus.mkdir(parents=True)
    (corpus / "excluded.py").write_text(
        "def excluded():\n    return 1\n", encoding="utf-8"
    )
    result = await CodeGraphIncrementalSyncTool(str(root)).execute(
        {"mode": "sync", "max_files": 2}
    )
    assert (result["success"], result["completeness"], result["scanned"]) == (
        True,
        "complete",
        2,
    )
    with closing(
        sqlite3.connect(resolve_index_path(root).as_uri() + "?mode=ro", uri=True)
    ) as conn:
        assert conn.execute(
            "SELECT file_path FROM ast_index ORDER BY file_path"
        ).fetchall() == [("leaf.py",), ("service.py",)]
