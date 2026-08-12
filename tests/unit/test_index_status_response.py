"""Exact behavioral tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


@requires_posix_snapshot
class TestAuthoritativeSnapshotOracle:
    @pytest.fixture(autouse=True)
    def _close_snapshot_capabilities(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    @staticmethod
    def _certified_cache(root):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = root / "sample.py"
        source.write_text("def answer():\n    return 42\n")
        cache = ASTCache(str(root))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(root))
        cache.close()

    def test_collect_final_stats_can_stamp_exact_manifest(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        source = tmp_path / "sample.py"
        source.write_text("x = 1\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        cache.close()

        result = CodeGraphFullIndexTool(str(tmp_path))._collect_final_stats(
            stamp_manifest=True
        )

        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        count = conn.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
        conn.close()
        assert (result["total_files"], count) == (1, 1)

    def test_collect_final_stats_without_stamp_leaves_manifest_empty(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        cache = ASTCache(str(tmp_path))
        cache.close()
        result = CodeGraphFullIndexTool(str(tmp_path))._collect_final_stats()

        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        count = conn.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
        conn.close()
        assert (result["total_files"], count) == (0, 0)

    @pytest.mark.parametrize(
        "source_bytes",
        [
            b"def answer():\n    return 42\n",
            b"def answer():\r\n    return 42\r\n",
            b"def answer():\r    return 42\r",
        ],
    )
    @pytest.mark.asyncio
    async def test_source_hash_matches_indexer_text_read_semantics(
        self, tmp_path, source_bytes
    ):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = tmp_path / "sample.py"
        source.write_bytes(source_bytes)
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
        cache.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["completeness"] == "complete"

    @pytest.mark.asyncio
    async def test_invalid_utf8_source_is_immediately_certified(self, tmp_path):
        # PR #1253 review 3754914627: replay matches writer errors="replace".
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = tmp_path / "sample.py"
        source.write_bytes(b"value = '\xff'\r\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
        cache.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert (result["completeness"], result["oracle_reason"]) == (
            "complete",
            None,
        )

    @pytest.mark.asyncio
    async def test_quiescent_wal_connection_with_nonempty_shm_allows_immutable_read(
        self, tmp_path
    ):
        # PR #1253: a persistent reader's SHM file is compatible with a pinned read.
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        source = tmp_path / "sample.py"
        source.write_text("value = 1\n")
        indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {"mode": "full", "resolve_synapse": False, "output_format": "json"}
        )
        assert indexed["success"] is True
        cache = ASTCache(str(tmp_path))
        cache.get_conn().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        shm = tmp_path / ".ast-cache" / "index.db-shm"
        if not shm.exists() or shm.stat().st_size == 0:
            cache.close()
            pytest.skip("GH-1253: SQLite did not retain WAL shared memory")

        try:
            result = await CodeGraphStatusTool(str(tmp_path)).execute(
                {"output_format": "json"}
            )
        finally:
            cache.close()

        assert (result["completeness"], result["oracle_reason"]) == (
            "complete",
            None,
        )

    @pytest.mark.asyncio
    async def test_manifest_stamp_failure_reports_warn_and_uncertified(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot_schema as schema
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        (tmp_path / "sample.py").write_text("value = 1\n")
        monkeypatch.setattr(
            schema,
            "stamp_full_index_manifest",
            lambda *_args: (_ for _ in ()).throw(
                RuntimeError("INDEX_FINGERPRINT_DEADLINE")
            ),
        )
        result = await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {
                "mode": "full",
                "exclude_patterns": [],
                "no_default_excludes": True,
                "output_format": "json",
            }
        )

        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        marker = conn.execute(
            "SELECT building FROM ast_build_state WHERE id=1"
        ).fetchone()[0]
        manifest_count = conn.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
        conn.close()
        assert (
            result["success"],
            result["verdict"],
            result["total_files"],
            result["manifest_warning"],
            result["certification_errors"],
            result["scope_complete"],
            manifest_count,
            marker,
        ) == (
            False,
            "WARN",
            1,
            "INDEX_MANIFEST_CERTIFICATION_FAILED",
            1,
            False,
            0,
            0,
        )

    @pytest.mark.asyncio
    async def test_missing_call_graph_marker_makes_snapshot_partial(self, tmp_path):
        self._certified_cache(tmp_path)
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        conn.execute("DELETE FROM ast_call_graph_state")
        conn.commit()
        conn.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert (result["completeness"], result["oracle_reason"]) == (
            "partial",
            "CALL_GRAPH_INCOMPLETE",
        )

    @pytest.mark.asyncio
    async def test_incomplete_call_graph_sentinel_makes_snapshot_partial(
        self, tmp_path
    ):
        self._certified_cache(tmp_path)
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        conn.execute(
            "INSERT INTO ast_call_graph_state (id, built, built_at) VALUES (2, 0, 0)"
        )
        conn.commit()
        conn.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert (result["completeness"], result["oracle_reason"]) == (
            "partial",
            "CALL_GRAPH_INCOMPLETE",
        )

    @pytest.mark.asyncio
    async def test_marker_write_failure_reports_incomplete_and_uncertified(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.cache.indexer as indexer
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        (tmp_path / "sample.py").write_text("value = 1\n")
        failure = lambda *_args: (_ for _ in ()).throw(  # noqa: E731
            sqlite3.OperationalError("disk I/O")
        )
        monkeypatch.setattr(indexer, "_mark_call_graph_built_strict", failure)
        import tree_sitter_analyzer._ast_cache_index_mixin as index_mixin

        monkeypatch.setattr(index_mixin, "_mark_call_graph_built_strict", failure)
        import tree_sitter_analyzer.cache.callgraph_state as callgraph_state

        monkeypatch.setattr(callgraph_state, "mark_call_graph_built_strict", failure)
        result = await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {
                "mode": "full",
                "exclude_patterns": [],
                "no_default_excludes": True,
                "output_format": "json",
            }
        )

        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        manifest_count = conn.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT id, built FROM ast_call_graph_state ORDER BY id"
        ).fetchall()
        conn.close()
        status = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )
        assert (
            result["success"],
            result["verdict"],
            result["phases"]["incremental_sync"]["backfill_errors"],
            result["phases"]["incremental_sync"]["completeness"],
            manifest_count,
            rows,
        ) == (False, "WARN", 1, "incomplete", 0, [(1, 0), (2, 0)])
        assert (status["completeness"], status["oracle_reason"]) == (
            "partial",
            "CALL_GRAPH_INCOMPLETE",
        )


def test_storage_fields_ignore_missing_and_null_values():
    from tree_sitter_analyzer.index_status_response import _storage_fields

    result = _storage_fields({"db_size_bytes": 4096, "db_page_size": None})

    assert result == {"db_size_bytes": 4096}


def test_status_lag_scans_snapshot_canonical_root(monkeypatch):
    # PR #1253 review 3763600670: O_NOFOLLOW requires the owner-resolved root.
    from contextlib import contextmanager

    from tree_sitter_analyzer import index_status_response as response
    from tree_sitter_analyzer.index_snapshot_registry import IndexSnapshot

    snapshot = IndexSnapshot(
        "idxsnap_test",
        "sha256:source",
        "sha256:index",
        "idxsrc-v3:source",
        "complete",
        None,
        "/canonical/project",
        1,
    )

    @contextmanager
    def lease(_project_root):
        yield snapshot

    monkeypatch.setattr(response.index_snapshot, "lease_existing_snapshot", lease)
    monkeypatch.setattr(
        response.index_snapshot,
        "read_snapshot_stats",
        lambda *_args: {
            "snapshot_id": snapshot.snapshot_id,
            "source_generation": snapshot.source_generation,
            "source_fingerprint": snapshot.source_fingerprint,
            "index_fingerprint": snapshot.index_fingerprint,
            "total_files": 1,
        },
    )
    observed = []
    monkeypatch.setattr(
        response.index_lag,
        "compute_qualitative_lag",
        lambda root, cache: observed.append((root, cache)) or 3.0,
    )

    result = response.build_index_status_response(
        "/logical/project", "json", include_lag=True
    )

    assert observed == [
        ("/canonical/project", "/canonical/project/.ast-cache/index.db")
    ]
    assert result["lag_seconds"] == 3.0
