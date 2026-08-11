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
    async def test_manifest_stamp_failure_keeps_index_successful_and_uncertified(
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
        assert result["success"] is True
        assert result["total_files"] == 1
        assert result["manifest_warning"] == "INDEX_MANIFEST_CERTIFICATION_FAILED"
        assert manifest_count == 0
        assert marker == 0

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
    async def test_marker_write_failure_keeps_index_successful_and_uncertified(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.cache.indexer as indexer
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        (tmp_path / "sample.py").write_text("value = 1\n")
        monkeypatch.setattr(
            indexer,
            "_mark_call_graph_built_strict",
            lambda *_args: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O")),
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
        assert result["success"] is True
        assert (manifest_count, rows) == (0, [(1, 0), (2, 0)])
        assert (status["completeness"], status["oracle_reason"]) == (
            "partial",
            "CALL_GRAPH_INCOMPLETE",
        )

    def test_exact_paths_without_strict_marker_clear_manifest(
        self, tmp_path, monkeypatch
    ):
        from types import SimpleNamespace

        import tree_sitter_analyzer.cache.indexer as indexer
        import tree_sitter_analyzer.index_snapshot_schema as schema
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_source_snapshot import (
            make_source_scope_descriptor,
        )

        source = tmp_path / "sample.py"
        source.write_text("value = 1\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        conn = cache.get_conn()
        conn.execute("DELETE FROM ast_call_graph_state")
        conn.execute(
            "INSERT INTO ast_index_snapshot_manifest VALUES "
            "(1, 'root', 'source', 'index', 1, '{}', 2)"
        )
        conn.commit()
        candidate = SimpleNamespace(
            selected_entries=(SimpleNamespace(rel_path="sample.py"),),
            limited=0,
            errors=0,
        )
        stats = {"errors": 0, "changed_during_run": 0, "backfill_errors": 0}
        monkeypatch.setattr(
            schema,
            "stamp_full_index_manifest",
            lambda *_args: pytest.fail("strict-marker stamp was called"),
        )

        indexer._update_authoritative_manifest(
            cache, candidate, stats, make_source_scope_descriptor()
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
        cache.close()

        assert (stats["manifest_warning"], count) == ("CALL_GRAPH_INCOMPLETE", 0)

    def test_portable_full_index_succeeds_without_manifest(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.cache.indexer as indexer
        from tree_sitter_analyzer.ast_cache import ASTCache

        real_os = indexer.os

        class PortableOS:
            name = "nt"
            path = real_os.path

            def __getattr__(self, name):
                return getattr(real_os, name)

        source = tmp_path / "sample.py"
        source.write_text("value = 1\n")
        monkeypatch.setattr(indexer, "os", PortableOS())
        cache = ASTCache(str(tmp_path))
        try:
            result = cache.index_project(workers=0)
            count = int(
                cache.get_conn()
                .execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest")
                .fetchone()[0]
            )
        finally:
            cache.close()

        assert result["errors"] == 0
        assert result["manifest_warning"] == "SOURCE_SCOPE_UNSUPPORTED"
        assert count == 0

    def test_manifest_stamp_rejects_unsupported_source_scope(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot_schema as schema
        from tree_sitter_analyzer.ast_cache import ASTCache

        cache = ASTCache(str(tmp_path))
        try:

            class UnsupportedOS:
                name = "nt"
                path = schema.os.path

            monkeypatch.setattr(schema, "os", UnsupportedOS())
            with pytest.raises(
                sqlite3.OperationalError, match="^SOURCE_SCOPE_UNSUPPORTED$"
            ):
                schema.stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
            count = int(
                cache.get_conn()
                .execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest")
                .fetchone()[0]
            )
        finally:
            cache.close()

        assert count == 0

    def test_manifest_stamp_rejects_missing_call_graph_marker(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot_schema as schema
        from tree_sitter_analyzer.ast_cache import ASTCache

        cache = ASTCache(str(tmp_path))
        try:
            with pytest.raises(
                sqlite3.OperationalError, match="^CALL_GRAPH_INCOMPLETE$"
            ):
                schema.stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
            count = int(
                cache.get_conn()
                .execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest")
                .fetchone()[0]
            )
        finally:
            cache.close()

        assert count == 0


@requires_posix_snapshot
@pytest.mark.asyncio
async def test_final_pinned_path_identity_mismatch_is_concurrent_writer(
    tmp_path, monkeypatch
):
    import tree_sitter_analyzer.index_snapshot as owner
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    owner.stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    cache.close()
    matches = iter((True, False))
    monkeypatch.setattr(
        owner, "_path_matches_pinned_database", lambda *_args: next(matches)
    )

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})
    assert result["oracle_reason"] == "CONCURRENT_WRITER"
    assert result["hint"].endswith("Do NOT start another index operation.")
    assert result["agent_summary"]["next_step"] == result["hint"]


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_bounded_stats_runtime_failure_returns_stable_envelope(
    tmp_path, monkeypatch
):
    # PR #1253: bounded fallback exhaustion must not escape the MCP handler.
    import tree_sitter_analyzer.index_snapshot as owner

    snapshot = owner.IndexSnapshot(
        "idxsnap_test",
        "source",
        "index",
        "generation",
        "complete",
        None,
        str(tmp_path),
        1,
    )
    monkeypatch.setattr(owner, "read_existing_snapshot", lambda _root: snapshot)
    monkeypatch.setattr(
        owner,
        "read_snapshot_stats",
        lambda *_args: (_ for _ in ()).throw(
            RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
        ),
    )

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "unknown",
        "SNAPSHOT_READ_FAILED",
    )
