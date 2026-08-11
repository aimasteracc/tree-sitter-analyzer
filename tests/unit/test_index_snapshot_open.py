"""Exact behavioral tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_fd = requires_posix_snapshot


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

    @requires_posix_fd
    @pytest.mark.asyncio
    async def test_database_size_limit_is_checked_before_read(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        monkeypatch.setattr(owner, "_MAX_CHARGED_BYTES", 1)
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "INDEX_SNAPSHOT_CAPACITY"

    @requires_posix_fd
    def test_512_byte_pages_can_backup_a_100_mib_database(self, tmp_path):
        # PR #1253: backup admission is byte-based, not a fixed page count.
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import read_existing_snapshot
        from tree_sitter_analyzer.index_snapshot_schema import (
            stamp_full_index_manifest,
        )

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        conn = sqlite3.connect(cache_dir / "index.db")
        conn.execute("PRAGMA page_size=512")
        conn.execute("VACUUM")
        conn.close()
        source = tmp_path / "sample.py"
        source.write_text("value = 1\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        conn = cache.get_conn()
        conn.execute(
            "INSERT INTO ast_cache_metadata (key, value) VALUES ('padding', zeroblob(?))",
            (100 * 1024 * 1024,),
        )
        stamp_full_index_manifest(conn, str(tmp_path))
        assert int(conn.execute("PRAGMA page_size").fetchone()[0]) == 512
        cache.close()

        snapshot = read_existing_snapshot(str(tmp_path))

        assert (snapshot.completeness, snapshot.reason) == ("complete", None)

    @requires_posix_fd
    @pytest.mark.asyncio
    async def test_backup_byte_budget_fails_closed(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        monkeypatch.setattr(owner, "_BACKUP_BYTE_BUDGET", 0)
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "INDEX_BACKUP_BUDGET"

    @requires_posix_fd
    @pytest.mark.asyncio
    async def test_backup_deadline_fails_closed(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        monkeypatch.setattr(owner, "_CAPTURE_DEADLINE_SECONDS", -1.0)

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )

        assert result["oracle_reason"] == "INDEX_SNAPSHOT_DEADLINE"

    @requires_posix_fd
    def test_graph_reader_requires_mapping_payload(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        snapshot = owner.read_existing_snapshot(str(tmp_path))
        with pytest.raises(TypeError, match="must return a mapping"):
            owner.run_graph_snapshot_read(
                snapshot.snapshot_id,
                str(tmp_path),
                snapshot.source_generation,
                lambda _conn: [],
            )


@requires_posix_fd
def test_capture_phases_share_one_absolute_deadline(tmp_path, monkeypatch):
    # PR #1253 review 3757950772: phase budgets accumulate instead of resetting.
    import tree_sitter_analyzer.index_snapshot as owner
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("def sample(): pass\n")
    cache = ASTCache(str(tmp_path))
    cache.index_project(workers=0)
    cache.close()

    now = [0.0]
    phases: list[str] = []

    def validate(_connection, *, deadline):
        phases.append("schema")
        assert deadline == 10.0
        now[0] += 6.0

    def fingerprint(_connection, _root, *, deadline):
        phases.append("fingerprint")
        assert deadline == 10.0
        now[0] += 5.0
        return "sha256:" + "0" * 64

    monkeypatch.setattr(owner, "_clock", lambda: now[0])
    monkeypatch.setattr(owner, "validate_snapshot_schema", validate)
    monkeypatch.setattr(owner, "index_fingerprint", fingerprint)
    monkeypatch.setattr(
        owner,
        "recorded_source_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("post-deadline phase ran")
        ),
    )

    snapshot = owner.read_existing_snapshot(str(tmp_path))

    assert phases == ["schema", "fingerprint"]
    assert snapshot.reason == "INDEX_SNAPSHOT_DEADLINE"


@requires_posix_fd
def test_hierarchy_cache_open_error_releases_temporary_root_fd(tmp_path, monkeypatch):
    import tree_sitter_analyzer.index_snapshot_capability as capability

    root = tmp_path / "root"
    (root / ".ast-cache").mkdir(parents=True)
    (root / ".ast-cache" / "index.db").touch()
    canonical, root_fd, cache_fd, db_fd = capability.open_bound_database(str(root))
    temporary: list[int] = []
    real_open = capability.os.open

    def fail_cache_open(path, flags, *args, **kwargs):
        if kwargs.get("dir_fd") is not None:
            raise OSError("cache reopen failed")
        fd = real_open(path, flags, *args, **kwargs)
        temporary.append(fd)
        return fd

    monkeypatch.setattr(capability.os, "open", fail_cache_open)
    try:
        matches = capability.hierarchy_matches_pinned_database(
            canonical, root_fd, cache_fd, db_fd
        )
        released = []
        for fd in temporary:
            try:
                os.fstat(fd)
            except OSError:
                released.append(fd)
    finally:
        for fd in (db_fd, cache_fd, root_fd):
            os.close(fd)

    assert (matches, released) == (False, temporary)
