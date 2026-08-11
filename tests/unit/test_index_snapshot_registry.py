"""Registry and capacity tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

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
