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

    @pytest.mark.asyncio
    async def test_public_facade_defaults_to_read_existing_without_creation(
        self, tmp_path
    ):
        from tree_sitter_analyzer.mcp.tools.index_facade import build_index_facade

        result = await build_index_facade(str(tmp_path)).execute(
            {"action": "status", "output_format": "json"}
        )

        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "MISSING_INDEX"
        assert (tmp_path / ".ast-cache").exists() is False

    @pytest.mark.asyncio
    async def test_old_schema_returns_stable_unknown_without_migration(self, tmp_path):
        import sqlite3

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        db_path = cache_dir / "index.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE ast_schema_version(version INTEGER)")
        conn.commit()
        conn.close()
        before = db_path.read_bytes()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert result["oracle_reason"] == "INCOMPATIBLE_SCHEMA"
        assert db_path.read_bytes() == before

    @pytest.mark.asyncio
    async def test_corrupt_index_returns_stable_unknown(self, tmp_path):
        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"not sqlite")

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "CORRUPT_INDEX"

    @pytest.mark.asyncio
    async def test_exact_manifest_returns_owner_issued_snapshot(self, tmp_path):
        self._certified_cache(tmp_path)

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert result["completeness"] == "complete"
        assert result["snapshot_id"].startswith("idxsnap_")
        assert result["source_fingerprint"].startswith("sha256:")
        assert result["index_fingerprint"].startswith("sha256:")
        assert result["action_version"] == "index.status/v1"
        assert "Use nav/search normally" in result["hint"]

    @pytest.mark.asyncio
    async def test_successful_full_index_writes_exact_authoritative_manifest(
        self, tmp_path
    ):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        (tmp_path / "sample.py").write_text("def answer():\n    return 42\n")
        await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {
                "mode": "full",
                "exclude_patterns": [],
                "no_default_excludes": True,
                "output_format": "json",
            }
        )

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert result["completeness"] == "complete"

    @pytest.mark.asyncio
    async def test_changed_index_rows_make_old_manifest_partial(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache

        self._certified_cache(tmp_path)
        source = tmp_path / "sample.py"
        source.write_text("def answer():\n    return 43\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        cache.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert result["completeness"] == "partial"
        assert result["oracle_reason"] == "NO_EXACT_FULL_INDEX_MANIFEST"

    def test_graph_reader_rejects_caller_forged_snapshot_id(self, tmp_path):
        from tree_sitter_analyzer.index_snapshot import run_graph_snapshot_read

        with pytest.raises(ValueError, match="INDEX_SNAPSHOT_UNKNOWN"):
            run_graph_snapshot_read(
                "idxsnap_caller-controlled",
                str(tmp_path),
                "idxsrc-v1:caller-controlled",
                lambda conn: {"count": 0},
            )

    @pytest.mark.asyncio
    async def test_graph_reader_echoes_tokens_from_acquired_capability(self, tmp_path):
        from tree_sitter_analyzer.index_snapshot import run_graph_snapshot_read

        self._certified_cache(tmp_path)
        status = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        result = run_graph_snapshot_read(
            status["snapshot_id"],
            str(tmp_path),
            status["source_generation"],
            lambda conn: {
                "files": int(
                    conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()[0]
                ),
                "snapshot_id": "caller-forged",
            },
        )

        assert result["snapshot_id"] == status["snapshot_id"]
        assert result["source_generation"] == status["source_generation"]

    @pytest.mark.asyncio
    async def test_symlinked_cache_is_rejected_without_following_target(self, tmp_path):
        outside = tmp_path.parent / f"{tmp_path.name}-outside"
        outside.mkdir()
        (outside / "index.db").write_bytes(b"not followed")
        (tmp_path / ".ast-cache").symlink_to(outside, target_is_directory=True)

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "INDEX_PATH_SYMLINK"

    @pytest.mark.asyncio
    async def test_added_source_makes_certified_snapshot_partial(self, tmp_path):
        self._certified_cache(tmp_path)
        before = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        (tmp_path / "added.py").write_text("value = 1\n")

        after = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert before["completeness"] == "complete"
        assert after["completeness"] == "partial"
        assert after["oracle_reason"] == "SOURCE_INDEX_MISMATCH"
        assert after["source_generation"] != before["source_generation"]

    @pytest.mark.asyncio
    async def test_modified_source_makes_certified_snapshot_partial(self, tmp_path):
        self._certified_cache(tmp_path)
        before = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        (tmp_path / "sample.py").write_text("def answer():\n    return 99\n")

        after = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert before["completeness"] == "complete"
        assert after["completeness"] == "partial"
        assert after["oracle_reason"] == "SOURCE_INDEX_MISMATCH"
        assert after["source_generation"] != before["source_generation"]

    @pytest.mark.asyncio
    async def test_deleted_source_makes_certified_snapshot_partial(self, tmp_path):
        self._certified_cache(tmp_path)
        (tmp_path / "sample.py").unlink()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert result["completeness"] == "partial"
        assert result["oracle_reason"] == "SOURCE_INDEX_MISMATCH"

    @pytest.mark.asyncio
    async def test_supported_fifo_is_partial_without_blocking(self, tmp_path):
        self._certified_cache(tmp_path)
        os.mkfifo(tmp_path / "unsafe.py")

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert result["completeness"] == "partial"
        assert result["oracle_reason"] == "SOURCE_SCOPE_UNSAFE"

    @pytest.mark.asyncio
    async def test_nonempty_wal_is_rejected_before_read(self, tmp_path):
        self._certified_cache(tmp_path)
        (tmp_path / ".ast-cache" / "index.db-wal").write_bytes(b"writer")

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "CONCURRENT_WRITER"

    @pytest.mark.asyncio
    async def test_fts_delete_changes_graph_fingerprint_and_completeness(
        self, tmp_path
    ):
        self._certified_cache(tmp_path)
        before = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        conn.execute(
            "INSERT INTO ast_symbols_fts(ast_symbols_fts) VALUES('delete-all')"
        )
        conn.commit()
        conn.close()

        after = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert before["completeness"] == "complete"
        assert after["completeness"] == "partial"
        assert after["index_fingerprint"] != before["index_fingerprint"]

    @pytest.mark.asyncio
    async def test_empty_successful_full_index_can_be_complete(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        build = await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {"mode": "full", "output_format": "json"}
        )
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert build["verdict"] == "INFO"
        assert result["total_files"] == 0
        assert result["completeness"] == "complete"

    @pytest.mark.asyncio
    async def test_path_swap_after_fd_pin_reads_original_inode(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        real_connect = owner.sqlite3.connect
        calls = 0

        def swapping_connect(database, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                replacement = tmp_path / ".ast-cache" / "replacement.db"
                replacement.write_bytes(b"attacker replacement")
                os.replace(replacement, tmp_path / ".ast-cache" / "index.db")
            return real_connect(database, *args, **kwargs)

        monkeypatch.setattr(owner.sqlite3, "connect", swapping_connect)
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "CONCURRENT_WRITER"

    @pytest.mark.asyncio
    async def test_status_rejects_forged_graph_token_echo(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        real_reader = owner.run_graph_snapshot_read

        def forged(snapshot_id, project_root, source_generation, reader):
            result = real_reader(snapshot_id, project_root, source_generation, reader)
            result["index_fingerprint"] = "caller-forged"
            return result

        monkeypatch.setattr(owner, "run_graph_snapshot_read", forged)
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "SNAPSHOT_READ_FAILED"

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
    async def test_invalid_utf8_source_is_not_certified(self, tmp_path):
        # PR #1253: the source oracle validates UTF-8 strictly while streaming.
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
            "partial",
            "SOURCE_SCOPE_UNSAFE",
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
            "NO_EXACT_FULL_INDEX_MANIFEST",
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
    async def test_no_fts_snapshot_uses_json_symbol_fallback(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = tmp_path / "sample.py"
        source.write_text("def answer():\n    return 42\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        conn = cache.get_conn()
        conn.execute("DROP TABLE ast_symbols_fts")
        conn.commit()
        stamp_full_index_manifest(conn, str(tmp_path))
        cache.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["fts5_available"] is False
        assert result["total_symbols"] == 1
        assert result["symbols_by_kind"] == {"function": 1}
        assert result["symbols_by_language"] == {"python": 1}
        assert result["db_auto_vacuum_mode"] == 0

    @pytest.mark.asyncio
    async def test_legacy_v13_without_symbol_table_is_readable(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = tmp_path / "sample.py"
        source.write_text("def answer():\n    return 42\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        conn = cache.get_conn()
        conn.execute("DROP TABLE ast_symbols_fts")
        conn.execute("DROP TABLE ast_symbol_rows")
        conn.commit()
        stamp_full_index_manifest(conn, str(tmp_path))
        cache.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["completeness"] == "complete"
        assert result["fts5_available"] is False
        assert result["total_symbols"] == 1
