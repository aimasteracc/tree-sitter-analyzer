"""Registry and capacity tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_snapshot = requires_posix_fd


class TestIndexSnapshotRegistry:
    @pytest.fixture(autouse=True)
    def _close_registry(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    @staticmethod
    def _snapshot(root):
        from tree_sitter_analyzer.index_snapshot import IndexSnapshot

        return IndexSnapshot(
            None,
            "source",
            "index",
            "generation",
            "complete",
            None,
            str(root.resolve()),
            0,
        )

    def test_registry_capacity_rejects_oversized_snapshot(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(owner, "_MAX_CHARGED_BYTES", 1)
        with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_CAPACITY"):
            owner.REGISTRY.ensure_capacity(2)

    def test_registry_rejects_root_mismatch(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(self._snapshot(tmp_path), conn, 0)
        duplicate = sqlite3.connect(":memory:")
        reused = owner.REGISTRY.publish(self._snapshot(tmp_path), duplicate, 0)
        assert reused.snapshot_id == published.snapshot_id
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            duplicate.execute("SELECT 1")
        with pytest.raises(ValueError, match="INDEX_SNAPSHOT_ROOT_MISMATCH"):
            with owner.acquire_index_snapshot(
                published.snapshot_id, str(tmp_path / "other")
            ):
                pass

    def test_registry_retires_logical_match_when_physical_stats_change(self, tmp_path):
        # PR #1253 thread 3756228871: VACUUM-only changes cannot reuse metrics.
        from dataclasses import replace

        import tree_sitter_analyzer.index_snapshot as owner

        first_conn = sqlite3.connect(":memory:")
        first = replace(
            self._snapshot(tmp_path), physical_storage_identity=(4096, 1, 4096, 0, 0, 0)
        )
        published = owner.REGISTRY.publish(first, first_conn, 0)
        second_conn = sqlite3.connect(":memory:")
        second = replace(first, physical_storage_identity=(8192, 2, 4096, 1, 4096, 2))
        replacement = owner.REGISTRY.publish(second, second_conn, 0)

        assert replacement.snapshot_id != published.snapshot_id
        assert tuple(owner.REGISTRY._entries) == (replacement.snapshot_id,)
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            first_conn.execute("SELECT 1")

    def test_registry_marks_pinned_physical_identity_stale(self, tmp_path):
        # PR #1253 thread 3756228871: pinned stale metrics close on release.
        from dataclasses import replace

        import tree_sitter_analyzer.index_snapshot as owner

        first = replace(
            self._snapshot(tmp_path), physical_storage_identity=(4096, 1, 4096, 0, 0, 0)
        )
        first_conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(first, first_conn, 0)
        entry = owner.REGISTRY._entries[published.snapshot_id]
        entry.readers = 1
        second = replace(first, physical_storage_identity=(8192, 2, 4096, 1, 4096, 2))
        replacement = owner.REGISTRY.publish(second, sqlite3.connect(":memory:"), 0)

        assert replacement.snapshot_id != published.snapshot_id
        assert entry.expires_at == float("-inf")
        entry.readers = 0
        owner.REGISTRY.ensure_capacity(0)
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            first_conn.execute("SELECT 1")

    def test_registry_rejects_generation_mismatch(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(self._snapshot(tmp_path), conn, 0)
        with pytest.raises(ValueError, match="SOURCE_GENERATION_MISMATCH"):
            with owner.acquire_index_snapshot(
                published.snapshot_id, str(tmp_path), "forged"
            ):
                pass

    def test_registry_purges_expired_unacquired_snapshot(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(self._snapshot(tmp_path), conn, 0)
        monkeypatch.setattr(owner, "_clock", lambda: 1000.0)
        entry = owner.REGISTRY._entries[published.snapshot_id]
        entry.readers = 1
        monkeypatch.setattr(owner, "_MAX_SNAPSHOTS", 1)
        with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_CAPACITY"):
            owner.REGISTRY.ensure_capacity(0)
        entry.readers = 0
        owner.REGISTRY.ensure_capacity(0)
        assert published.snapshot_id not in owner.REGISTRY._entries
        expiring = owner.REGISTRY.publish(
            self._snapshot(tmp_path), sqlite3.connect(":memory:"), 0
        )
        owner.REGISTRY._entries[expiring.snapshot_id].expires_at = 1.0
        owner.REGISTRY.ensure_capacity(0)
        assert expiring.snapshot_id not in owner.REGISTRY._entries

    def test_reuse_refreshes_absolute_capture_deadline_after_ten_seconds(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3758377125: TTL reuse must not retain an expired budget.
        import tree_sitter_analyzer.index_snapshot as owner

        now = [0.0]
        monkeypatch.setattr(owner, "_clock", lambda: now[0])
        first = owner.REGISTRY.publish(
            self._snapshot(tmp_path), sqlite3.connect(":memory:"), 0, 10.0
        )
        now[0] = 11.0
        reused = owner.REGISTRY.publish(
            self._snapshot(tmp_path),
            sqlite3.connect(":memory:"),
            0,
            21.0,
            pin=True,
        )

        assert reused.snapshot_id == first.snapshot_id
        assert owner.REGISTRY.capture_deadline(first.snapshot_id) == 21.0
        assert owner.REGISTRY._entries[first.snapshot_id].readers == 1
        owner.REGISTRY.release_pin(first.snapshot_id)

    def test_release_rejects_unknown_or_unpinned_capability(self):
        import tree_sitter_analyzer.index_snapshot as owner

        with pytest.raises(ValueError, match="INDEX_SNAPSHOT_UNKNOWN"):
            owner.REGISTRY.release_pin("idxsnap_unknown")

    def test_published_pin_prevents_capacity_eviction_until_release(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3758212523: publication and reader pin are atomic.
        from dataclasses import replace

        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(owner, "_MAX_SNAPSHOTS", 1)
        first = owner.REGISTRY.publish(
            self._snapshot(tmp_path), sqlite3.connect(":memory:"), 0, pin=True
        )
        different = replace(self._snapshot(tmp_path), source_fingerprint="other")
        with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_CAPACITY"):
            owner.REGISTRY.publish(different, sqlite3.connect(":memory:"), 0)
        owner.REGISTRY.release_pin(first.snapshot_id)
        second = owner.REGISTRY.publish(different, sqlite3.connect(":memory:"), 0)

        assert second.snapshot_id != first.snapshot_id


def test_symbol_projection_verdict_rejects_unknown_snapshot():
    # PR #1253: projection evidence is available only for registered snapshots.
    from tree_sitter_analyzer.index_snapshot import REGISTRY

    with pytest.raises(ValueError, match="^INDEX_SNAPSHOT_UNKNOWN$"):
        REGISTRY.symbol_projection_exact("idxsnap_unknown")


# Additional authoritative snapshot transitions retained in the established module.
_requires_posix_snapshot = requires_posix_snapshot


@_requires_posix_snapshot
class TestAuthoritativeSnapshotTransitions:
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

        # PR #1253: post-backup source recapture requires an exact scope.
        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "SOURCE_SCOPE_UNSAFE"

    @pytest.mark.asyncio
    async def test_source_change_during_backup_is_not_published(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3759852190: the post-backup epoch must match capture.
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        source = tmp_path / "sample.py"
        real_capture = owner._capture_sources_with_deadline
        calls = 0

        def capture_then_change(root, scope, deadline):
            nonlocal calls
            captured = real_capture(root, scope, deadline)
            calls += 1
            if calls == 1:
                source.write_text("def answer():\n    return 99\n")
            return captured

        monkeypatch.setattr(
            owner, "_capture_sources_with_deadline", capture_then_change
        )
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert (calls, result["completeness"], result["oracle_reason"]) == (
            2,
            "unknown",
            "CONCURRENT_SOURCE",
        )

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
        assert (
            result["total_files"],
            result["completeness"],
            result["indexed"],
            result["verdict"],
        ) == (0, "complete", True, "INFO")
        assert result["hint"].startswith("Index is complete.")

    @pytest.mark.asyncio
    async def test_empty_partial_snapshot_remains_unindexed(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        await CodeGraphFullIndexTool(str(tmp_path)).execute(
            {"mode": "full", "output_format": "json"}
        )
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        conn.execute("DELETE FROM ast_call_graph_state")
        conn.commit()
        conn.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert (result["total_files"], result["completeness"], result["indexed"]) == (
            0,
            "partial",
            False,
        )

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


# ---------------------------------------------------------------------------
# REQ-U-105: _WalEntry rename + TTL + WAL overhead constant
# ---------------------------------------------------------------------------

class TestWalEntryRename:
    """REQ-U-105: _WalEntry exists, _Entry is absent or aliased, TTL ≤ 35 s."""

    def test_wal_entry_class_exists(self):
        """_WalEntry is the canonical registry entry class."""
        from tree_sitter_analyzer.index_snapshot_registry import _WalEntry
        assert _WalEntry is not None

    def test_entry_class_absent_or_aliased(self):
        """_Entry is either absent or an alias for _WalEntry (no separate class)."""
        import tree_sitter_analyzer.index_snapshot_registry as reg
        if hasattr(reg, "_Entry"):
            assert reg._Entry is reg._WalEntry, "_Entry must alias _WalEntry"

    def test_wal_connection_overhead_bytes_constant(self):
        """_WAL_CONNECTION_OVERHEAD_BYTES is exactly 2 MB."""
        from tree_sitter_analyzer.index_snapshot_registry import (
            _WAL_CONNECTION_OVERHEAD_BYTES,
        )
        assert _WAL_CONNECTION_OVERHEAD_BYTES == 2 * 1024 * 1024

    def test_published_entry_is_wal_entry_type(self, tmp_path):
        """Registry entries use _WalEntry instances after publish."""
        import sqlite3

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_snapshot_registry import _WalEntry

        snapshot = _snapshot_fixture(tmp_path)
        conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(snapshot, conn, 0)
        entry = owner.REGISTRY._entries[published.snapshot_id]
        assert isinstance(entry, _WalEntry)
        owner.REGISTRY.close_all()

    def test_ttl_at_most_35_seconds(self, tmp_path):
        """Entries expire within 35 s: expires_at - creation_time ≤ 35."""
        import sqlite3
        import time

        import tree_sitter_analyzer.index_snapshot as owner

        snapshot = _snapshot_fixture(tmp_path)
        before = time.time()
        conn = sqlite3.connect(":memory:")
        published = owner.REGISTRY.publish(snapshot, conn, 0)
        entry = owner.REGISTRY._entries[published.snapshot_id]
        assert entry.expires_at - before <= 35.0 + 0.5  # 0.5 s clock tolerance
        owner.REGISTRY.close_all()


def _snapshot_fixture(tmp_path):
    """Return a minimal IndexSnapshot for tmp_path."""
    from tree_sitter_analyzer.index_snapshot import IndexSnapshot

    return IndexSnapshot(
        None,
        "source",
        "index",
        "generation",
        "complete",
        None,
        str(tmp_path.resolve()),
        0,
    )
