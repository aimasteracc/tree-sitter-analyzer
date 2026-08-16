"""Exact behavioral tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_fd = requires_posix_snapshot


class TestNonPosixSnapshotContract:
    def test_missing_project_root_precedes_missing_index_classification(self, tmp_path):
        # PR #1253 review 3763600676: invalid configuration is not an empty cache.
        import tree_sitter_analyzer.index_snapshot as owner

        result = owner.read_existing_snapshot(str(tmp_path / "missing"))

        assert (result.completeness, result.reason) == (
            "unknown",
            "MISSING_PROJECT_ROOT",
        )

    def test_non_posix_missing_index_preserves_missing_contract(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(owner.os, "name", "nt")
        result = owner.read_existing_snapshot(str(tmp_path))
        assert result.reason == "MISSING_INDEX"

    def test_non_posix_existing_index_is_explicitly_unsupported(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"")
        monkeypatch.setattr(owner.os, "name", "nt")
        result = owner.read_existing_snapshot(str(tmp_path))
        assert result.completeness == "unknown"
        assert result.reason == "SECURE_FD_SNAPSHOT_UNSUPPORTED"


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

    def test_descriptor_cleanup_continues_after_first_close_error(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 review 3759391278: pinned handles are independent resources.
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        original_close = owner.os.close
        attempted: list[int] = []

        def flaky_close(fd: int) -> None:
            attempted.append(fd)
            if len(attempted) == 1:
                raise OSError("simulated close failure")
            original_close(fd)

        monkeypatch.setattr(owner, "_close_pinned_descriptor", flaky_close)
        result = owner.read_existing_snapshot(str(tmp_path))
        original_close(attempted[0])

        assert result.completeness == "complete"
        assert len(attempted) == 3

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
        assert result["indexed"] is False
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
    async def test_old_schema_explicit_access_evidence_is_unknown(self, tmp_path):
        import sqlite3

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        conn = sqlite3.connect(cache_dir / "index.db")
        conn.execute("CREATE TABLE ast_schema_version(version INTEGER)")
        conn.commit()
        conn.close()

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert {
            key: result[key]
            for key in ("access_state", "access_reason", "source_snapshots")
        } == {
            "access_state": "unknown",
            "access_reason": "INCOMPATIBLE_SCHEMA",
            "source_snapshots": [],
        }

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
        assert result["access_state"] == "available"
        assert result["access_reason"] is None
        assert result["source_snapshots"] == [
            {
                "kind": "index",
                "snapshot_id": result["snapshot_id"],
                "source_generation": result["source_generation"],
            }
        ]
        assert "Use nav/search normally" in result["hint"]

    @pytest.mark.asyncio
    async def test_fts_projection_is_verified_on_private_copy_before_query_only(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3760724568: rank=1 integrity runs once on writable evidence.
        import tree_sitter_analyzer.index_snapshot as owner
        import tree_sitter_analyzer.index_snapshot_stats as stats_owner

        self._certified_cache(tmp_path)
        real_validator = owner.symbol_projection_is_exact
        observed: list[tuple[int, str]] = []

        def recording_validator(conn, *args, **kwargs):
            observed.append(
                (
                    int(conn.execute("PRAGMA query_only").fetchone()[0]),
                    str(conn.execute("PRAGMA database_list").fetchone()[2]),
                )
            )
            return real_validator(conn, *args, **kwargs)

        monkeypatch.setattr(owner, "symbol_projection_is_exact", recording_validator)
        monkeypatch.setattr(
            stats_owner,
            "symbol_projection_is_exact",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("cached projection verdict was not used")
            ),
        )
        monkeypatch.setattr(
            stats_owner,
            "fallback_symbol_counts",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("healthy FTS projection used JSON fallback")
            ),
        )

        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"access_mode": "read_existing", "output_format": "json"}
        )

        assert observed == [(0, "")]
        assert (result["fts5_available"], result["total_symbols"]) == (True, 1)

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


requires_posix_fd = requires_posix_snapshot


@requires_posix_snapshot
class TestSnapshotOpenBoundaries:
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
    @pytest.mark.slow_ok
    def test_512_byte_pages_can_backup_a_100_mib_database(self, tmp_path):
        # PR #1253: intentional 100 MiB I/O can exceed 5 s under macOS xdist load;
        # this is a correctness boundary, not a per-call performance assertion.
        # Backup admission is byte-based, not a fixed page count.
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


class TestReadExistingConsumerRevalidation:
    """RFC-0022 P0.4 after-read revalidation seam for P0.1 consumers."""

    @pytest.fixture(autouse=True)
    def _close_registry(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    @staticmethod
    def _fake_capture(state, generation, fingerprint="fp", reason=None):
        from tree_sitter_analyzer.index_source_snapshot import (
            CurrentSourceSnapshot,
        )

        return CurrentSourceSnapshot(
            frozenset(), fingerprint, generation, state, reason
        )

    def test_verify_skips_capture_without_source_scope(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        captured: list[object] = []

        def fake_capture(root, scope, deadline=None):
            captured.append(scope)
            return self._fake_capture("exact", "gen-1")

        monkeypatch.setattr(owner, "_capture_sources_with_deadline", fake_capture)
        snapshot = owner.IndexSnapshot(
            "s", "fp", "ifp", "gen-1", "complete", None, str(tmp_path.resolve()), 0
        )

        owner.verify_snapshot_source_current(snapshot)

        assert captured == []  # no scope descriptor -> nothing to revalidate

    def test_verify_generation_match_passes(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        scope = object()
        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", "gen-1"
            ),
        )
        snapshot = owner.IndexSnapshot(
            "s",
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=scope,
        )

        owner.verify_snapshot_source_current(snapshot)  # no raise

    def test_verify_generation_mismatch_raises(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", "gen-2"
            ),
        )
        snapshot = owner.IndexSnapshot(
            "s",
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=object(),
        )

        with pytest.raises(ValueError, match="SOURCE_GENERATION_MISMATCH"):
            owner.verify_snapshot_source_current(snapshot)

    def test_verify_fingerprint_fallback_when_generation_absent(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", None, fingerprint="fp-new"
            ),
        )
        snapshot = owner.IndexSnapshot(
            "s",
            "fp-old",
            "ifp",
            None,
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=object(),
        )

        with pytest.raises(ValueError, match="SOURCE_GENERATION_MISMATCH"):
            owner.verify_snapshot_source_current(snapshot)

    def test_verify_non_exact_state_raises(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "unsafe", "gen-1", reason="SOURCE_SCOPE_UNSAFE"
            ),
        )
        snapshot = owner.IndexSnapshot(
            "s",
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=object(),
        )

        with pytest.raises(ValueError, match="SOURCE_SCOPE_UNSAFE"):
            owner.verify_snapshot_source_current(snapshot)

    def test_read_existing_index_scope_recaptures_after_read(
        self, tmp_path, monkeypatch
    ):
        import sqlite3

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_scope import (
            make_source_scope_descriptor,
        )

        scope = make_source_scope_descriptor()
        captured: list[object] = []
        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: (
                captured.append(source_scope) or self._fake_capture("exact", "gen-1")
            ),
        )
        conn = sqlite3.connect(":memory:")
        snapshot = owner.IndexSnapshot(
            None,
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=scope,
        )
        published = owner.REGISTRY.publish(snapshot, conn, 0)

        with owner.read_existing_index_scope(
            published.snapshot_id, str(tmp_path), "gen-1"
        ) as (index, yielded_conn):
            assert index.snapshot_id == published.snapshot_id
            assert yielded_conn is conn

        # Codex P1 (#1299): recapture runs BEFORE the read (at __enter__)
        # AND after it (on normal exit).
        assert captured == [scope, scope]

    def test_read_existing_index_scope_mismatch_before_yield_fails_closed(
        self, tmp_path, monkeypatch
    ):
        import sqlite3

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_scope import (
            make_source_scope_descriptor,
        )

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", "gen-2"
            ),
        )
        conn = sqlite3.connect(":memory:")
        snapshot = owner.IndexSnapshot(
            None,
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=make_source_scope_descriptor(),
        )
        published = owner.REGISTRY.publish(snapshot, conn, 0)

        with pytest.raises(ValueError, match="SOURCE_GENERATION_MISMATCH"):
            with owner.read_existing_index_scope(
                published.snapshot_id, str(tmp_path), "gen-1"
            ):
                pass

    def test_read_existing_index_scope_mismatch_on_exit_fails_closed(
        self, tmp_path, monkeypatch
    ):
        """The after-read recapture (normal exit) still gates the result."""
        import sqlite3

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_scope import (
            make_source_scope_descriptor,
        )

        calls = {"n": 0}

        def sequence_capture(root, source_scope, deadline=None):
            # Pre-read recapture matches; the after-read recapture does not.
            calls["n"] += 1
            return self._fake_capture("exact", "gen-1" if calls["n"] == 1 else "gen-2")

        monkeypatch.setattr(owner, "_capture_sources_with_deadline", sequence_capture)
        conn = sqlite3.connect(":memory:")
        snapshot = owner.IndexSnapshot(
            None,
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=make_source_scope_descriptor(),
        )
        published = owner.REGISTRY.publish(snapshot, conn, 0)

        with pytest.raises(ValueError, match="SOURCE_GENERATION_MISMATCH"):
            with owner.read_existing_index_scope(
                published.snapshot_id, str(tmp_path), "gen-1"
            ):
                pass

    def test_read_existing_index_scope_rejects_incomplete_snapshot(
        self, tmp_path, monkeypatch
    ):
        """A partial capability (CALL_GRAPH_INCOMPLETE) never serves reads."""
        import sqlite3

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_scope import (
            make_source_scope_descriptor,
        )

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", "gen-1"
            ),
        )
        conn = sqlite3.connect(":memory:")
        snapshot = owner.IndexSnapshot(
            None,
            "fp",
            "ifp",
            "gen-1",
            "partial",
            "CALL_GRAPH_INCOMPLETE",
            str(tmp_path.resolve()),
            0,
            source_scope=make_source_scope_descriptor(),
        )
        published = owner.REGISTRY.publish(snapshot, conn, 0)

        with pytest.raises(ValueError, match="INDEX_SNAPSHOT_INCOMPLETE"):
            with owner.read_existing_index_scope(
                published.snapshot_id, str(tmp_path), "gen-1"
            ):
                pass

    def test_read_existing_index_scope_honors_expired_deadline(
        self, tmp_path, monkeypatch
    ):
        """An absolute deadline in the past fails closed at acquisition."""
        import sqlite3
        import time

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_scope import (
            make_source_scope_descriptor,
        )

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", "gen-1"
            ),
        )
        conn = sqlite3.connect(":memory:")
        snapshot = owner.IndexSnapshot(
            None,
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=make_source_scope_descriptor(),
        )
        published = owner.REGISTRY.publish(snapshot, conn, 0)

        # REGISTRY.acquire raises RuntimeError for an expired deadline; the
        # consumer seam classifies both ValueError and RuntimeError.
        with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_DEADLINE"):
            with owner.read_existing_index_scope(
                published.snapshot_id,
                str(tmp_path),
                "gen-1",
                deadline=time.monotonic() - 1,
            ):
                pass

    @pytest.mark.parametrize("bad_root", ["", b"not-a-str"])
    def test_verify_unusable_root_raises_index_snapshot_unknown(
        self, tmp_path, monkeypatch, bad_root
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", "gen-1"
            ),
        )
        snapshot = owner.IndexSnapshot(
            "s",
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            bad_root,
            0,
            source_scope=object(),
        )

        with pytest.raises(ValueError, match="INDEX_SNAPSHOT_UNKNOWN"):
            owner.verify_snapshot_source_current(snapshot)

    def test_verify_absent_generation_and_fingerprint_raises(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", None, fingerprint=None
            ),
        )
        snapshot = owner.IndexSnapshot(
            "s",
            None,
            "ifp",
            None,
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=object(),
        )

        with pytest.raises(ValueError, match="SOURCE_GENERATION_MISMATCH"):
            owner.verify_snapshot_source_current(snapshot)

    def test_verify_fingerprint_match_passes_when_generation_absent(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", None, fingerprint="fp"
            ),
        )
        snapshot = owner.IndexSnapshot(
            "s",
            "fp",
            "ifp",
            None,
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=object(),
        )

        owner.verify_snapshot_source_current(snapshot)  # no raise

    def test_read_existing_index_scope_rejects_constrained_scope(
        self, tmp_path, monkeypatch
    ):
        import sqlite3

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_scope import (
            make_source_scope_descriptor,
        )

        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", "gen-1"
            ),
        )
        conn = sqlite3.connect(":memory:")
        snapshot = owner.IndexSnapshot(
            None,
            "fp",
            "ifp",
            "gen-1",
            "complete",
            None,
            str(tmp_path.resolve()),
            0,
            source_scope=make_source_scope_descriptor(exclude_patterns=("vendor",)),
        )
        published = owner.REGISTRY.publish(snapshot, conn, 0)

        with pytest.raises(ValueError, match="CONSTRAINED_INDEX_SCOPE"):
            with owner.read_existing_index_scope(
                published.snapshot_id, str(tmp_path), "gen-1"
            ):
                pass
