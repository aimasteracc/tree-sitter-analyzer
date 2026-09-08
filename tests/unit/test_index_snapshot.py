"""Exact behavioral tests for the index snapshot owner."""

from __future__ import annotations

import errno
import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_fd = requires_posix_snapshot


class TestNonPosixSnapshotContract:
    def test_unsupported_capture_preserves_ordinary_index_update_and_query(
        self, tmp_path, monkeypatch
    ):
        """PR #1350：WAL 捕获未获资格时，普通创建、更新与图查询仍须可用。"""
        import tree_sitter_analyzer.index_snapshot as owner
        import tree_sitter_analyzer.index_snapshot_capability as capability
        from tree_sitter_analyzer.ast_cache import ASTCache

        monkeypatch.setattr(capability, "_WAL_FD_COPY_SUPPORTED", False)
        source = tmp_path / "app.py"
        source.write_text(
            "def helper(): return 1\ndef run(): return helper()\n", encoding="utf-8"
        )
        cache = ASTCache(str(tmp_path))
        try:
            assert cache.index_file(str(source))["status"] == "indexed"
            assert [
                (edge["callee_name"], edge["callee_resolved_file"])
                for edge in cache.query_callees("run", "app.py")
            ] == [("helper", "app.py")]
            snapshot = owner._capture_wal_snapshot(
                str(tmp_path.resolve()),
                str(tmp_path / ".ast-cache" / "index.db"),
                deadline=owner._clock() + 10,
            )
            assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
                None,
                "unknown",
                "WAL_PRIVATE_SNAPSHOT_UNSUPPORTED",
            )
            source.write_text(
                "def updated(): return 42\ndef run(): return updated()\n",
                encoding="utf-8",
            )
            assert cache.index_file(str(source))["status"] == "indexed"
            assert [
                (edge["callee_name"], edge["callee_resolved_file"])
                for edge in cache.query_callees("run", "app.py")
            ] == [("updated", "app.py")]
            assert cache.query_callers("helper", "app.py") == []
        finally:
            cache.close()

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

    def test_non_posix_existing_index_uses_wal_path(self, tmp_path, monkeypatch):
        """无安全 fd 复制能力的平台必须拒绝，而非用源 SQLite 连接降级。"""
        import tree_sitter_analyzer.index_snapshot as owner
        import tree_sitter_analyzer.index_snapshot_capability as capability

        monkeypatch.setattr(capability, "_WINDOWS_WAL_SUPPORTED", False)

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"")
        monkeypatch.setattr(owner.os, "name", "nt")
        result = owner.read_existing_snapshot(str(tmp_path))
        assert (result.completeness, result.reason) == (
            "unknown",
            "WAL_PRIVATE_SNAPSHOT_UNSUPPORTED",
        )


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

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ("source_edit", "CONCURRENT_SOURCE"),
            ("source_delete", "CONCURRENT_SOURCE"),
            ("source_symlink", "SOURCE_SCOPE_UNSAFE"),
            ("database_replace", "CONCURRENT_WRITER"),
            ("database_delete", "CONCURRENT_WRITER"),
        ],
    )
    def test_wal_capture_race_rejects_token_and_closes_connections(
        self, tmp_path, monkeypatch, change, reason
    ):
        # PR #1350：在真实复制后改变文件；不得发布旧认证，且源连接与副本都须关闭。
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        db = tmp_path / ".ast-cache" / "index.db"
        source = tmp_path / "sample.py"
        writer = sqlite3.connect(db)
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("INSERT INTO ast_cache_metadata VALUES ('race_test', 'active')")
        writer.commit()
        copy_evidence = owner._copy_projection_evidence
        connections = []
        registered = set(owner.REGISTRY._entries)

        def mutate_after_copy(conn, deadline):
            evidence, exact = copy_evidence(conn, deadline)
            connections.extend([conn, evidence])
            if change == "source_edit":
                source.write_text("def answer():\n    return 43\n", encoding="utf-8")
            elif change == "source_delete":
                source.unlink()
            elif change == "source_symlink":
                source.unlink()
                source.symlink_to(tmp_path / "missing.txt")
            elif change == "database_replace":
                db.rename(db.with_name("original.db"))
                db.write_bytes(b"replacement database")
            else:
                db.unlink()
            return evidence, exact

        monkeypatch.setattr(owner, "_copy_projection_evidence", mutate_after_copy)
        try:
            snapshot = owner._capture_wal_snapshot(
                str(tmp_path.resolve()), str(db), deadline=owner._clock() + 10
            )
            assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
                None,
                "unknown",
                reason,
            )
            assert set(owner.REGISTRY._entries) == registered
            assert len(connections) == 2
            for conn in connections:
                with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                    conn.execute("SELECT 1")
        finally:
            writer.close()

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ("marker", "CALL_GRAPH_INCOMPLETE"),
            ("manifest_missing", "SOURCE_SCOPE_DESCRIPTOR_MISSING"),
            ("scope_invalid", "SOURCE_SCOPE_DESCRIPTOR_INVALID"),
            ("source_changed", "SOURCE_INDEX_MISMATCH"),
            ("manifest_mismatch", "NO_EXACT_FULL_INDEX_MANIFEST"),
        ],
    )
    def test_wal_uncertified_states_reject_consumer(self, tmp_path, change, reason):
        # PR #1350：真实持久状态损坏不得被 WAL 路径的成功投影核验覆盖。
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        db = tmp_path / ".ast-cache" / "index.db"
        with sqlite3.connect(db) as conn:
            if change == "marker":
                conn.execute("DELETE FROM ast_call_graph_state")
            elif change == "manifest_missing":
                conn.execute("DELETE FROM ast_index_snapshot_manifest")
            elif change == "scope_invalid":
                conn.execute(
                    "UPDATE ast_index_snapshot_manifest SET source_scope_descriptor='not-json'"
                )
            elif change == "manifest_mismatch":
                conn.execute(
                    "UPDATE ast_index_snapshot_manifest SET index_fingerprint=?",
                    ("sha256:" + "0" * 64,),
                )
            else:
                (tmp_path / "sample.py").write_text(
                    "def changed(): return 22\n", encoding="utf-8"
                )
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()), str(db), deadline=owner._clock() + 10
        )
        assert (snapshot.completeness, snapshot.reason) == ("partial", reason)
        with pytest.raises(ValueError, match="^INDEX_SNAPSHOT_INCOMPLETE$"):
            with owner.read_existing_index_scope(
                snapshot.snapshot_id, str(tmp_path), snapshot.source_generation
            ):
                pytest.fail("未认证状态不能到达 consumer")

    def test_wal_missing_database_is_unknown(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        snapshot = owner._capture_wal_snapshot(
            str(tmp_path), str(tmp_path / "missing.db"), deadline=owner._clock() + 10
        )
        assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
            None,
            "unknown",
            "MISSING_INDEX",
        )

    def test_wal_rejects_a_foreign_database_path(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        other = tmp_path / "other.db"
        other.write_bytes(b"not the project cache")
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()), str(other), deadline=owner._clock() + 10
        )
        assert (snapshot.snapshot_id, snapshot.reason) == (None, "INDEX_PATH_UNSAFE")

    def test_projection_backup_has_its_own_byte_admission(self, monkeypatch):
        # PR #1350：共享 SQLite 复制函数也必须独立检查逻辑页预算。
        import tree_sitter_analyzer.index_snapshot as owner

        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE TABLE payload(value INTEGER)")
            monkeypatch.setattr(owner, "_BACKUP_BYTE_BUDGET", 0)
            with pytest.raises(RuntimeError, match="^INDEX_BACKUP_BUDGET$"):
                owner._copy_projection_evidence(conn, owner._clock() + 10)
        finally:
            conn.close()

    def test_wal_database_disappears_after_open(self, tmp_path, monkeypatch):
        # PR #1350：连接刚打开主库就消失，必须关闭该连接且不发布 token。
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        db = tmp_path / ".ast-cache" / "index.db"
        connect = sqlite3.connect
        opened = []

        def open_then_unlink(database, *args, **kwargs):
            conn = connect(database, *args, **kwargs)
            if str(database).startswith("file:"):
                opened.append(conn)
                db.unlink()
            return conn

        monkeypatch.setattr(owner.sqlite3, "connect", open_then_unlink)
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()), str(db), deadline=owner._clock() + 10
        )
        assert (snapshot.snapshot_id, snapshot.reason) == (None, "CONCURRENT_WRITER")
        assert len(opened) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            opened[0].execute("SELECT 1")

    def test_wal_build_in_progress_is_unknown(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.cache.build_state import mark_build_in_progress

        self._certified_cache(tmp_path)
        db = tmp_path / ".ast-cache" / "index.db"
        with sqlite3.connect(db) as conn:
            mark_build_in_progress(conn)
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()), str(db), deadline=owner._clock() + 10
        )
        assert (snapshot.snapshot_id, snapshot.reason) == (None, "CONCURRENT_WRITER")

    def test_wal_source_budget_remains_unknown(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner
        import tree_sitter_analyzer.index_source_snapshot as source_owner

        self._certified_cache(tmp_path)
        monkeypatch.setattr(source_owner, "_SOURCE_ENTRY_BUDGET", 0)
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()),
            str(tmp_path / ".ast-cache" / "index.db"),
            deadline=owner._clock() + 10,
        )
        assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
            None,
            "unknown",
            "SOURCE_SCOPE_UNBOUNDED",
        )

    @pytest.mark.parametrize(
        "error_number", [errno.ENOENT, errno.EACCES, errno.ENOTDIR, errno.ELOOP]
    )
    def test_wal_open_os_failure_is_classified(
        self, tmp_path, monkeypatch, error_number
    ):
        # PR #1350：仅在数据库打开边界注入 OS 故障，不替换快照业务结果。
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        fault = OSError(error_number, "open denied")
        connect = sqlite3.connect

        def fail_open(database, *args, **kwargs):
            if str(database).startswith("file:"):
                raise fault
            return connect(database, *args, **kwargs)

        monkeypatch.setattr(owner.sqlite3, "connect", fail_open)
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()),
            str(tmp_path / ".ast-cache" / "index.db"),
            deadline=owner._clock() + 10,
        )
        reason = (
            "INDEX_PATH_SYMLINK"
            if error_number in (errno.ELOOP, errno.ENOTDIR)
            else str(fault)
        )
        assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
            None,
            "unknown",
            reason,
        )


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

        with pytest.raises(ValueError, match="SOURCE_GENERATION_MISMATCH") as exc_info:
            with owner.read_existing_index_scope(
                published.snapshot_id, str(tmp_path), "gen-1"
            ):
                pass
        # Codex P2 (#1299): pre-yield failures still cite the acquired
        # capability identity.
        assert getattr(exc_info.value, "_read_existing_identity", None) == (
            published.snapshot_id,
            "gen-1",
        )

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

        with pytest.raises(ValueError, match="INDEX_SNAPSHOT_INCOMPLETE") as exc_info:
            with owner.read_existing_index_scope(
                published.snapshot_id, str(tmp_path), "gen-1"
            ):
                pass
        assert getattr(exc_info.value, "_read_existing_identity", None) == (
            published.snapshot_id,
            "gen-1",
        )

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

    def _deadline_scope_fixture(self, tmp_path, monkeypatch):
        import sqlite3
        import time

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_scope import (
            make_source_scope_descriptor,
        )

        clock = {"now": time.monotonic()}
        monkeypatch.setattr(owner, "_clock", lambda: clock["now"])
        monkeypatch.setattr(
            owner,
            "_capture_sources_with_deadline",
            lambda root, source_scope, deadline=None: self._fake_capture(
                "exact", "gen-1"
            ),
        )
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE t (x INTEGER)")
        # Enough rows that the reader's query exceeds the progress-handler
        # step (1000 VM opcodes) and the handler itself fires.
        conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(50_000)])
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
        return owner, published, clock

    def test_read_existing_index_scope_reader_sql_aborts_on_deadline(
        self, tmp_path, monkeypatch
    ):
        """The progress handler aborts reader SQL past the deadline.

        Codex P2 (#1299): the LIKE scan guarantees the handler fires
        (count(*) is too optimized to reach the 1000-opcode step); the
        abort surfaces as ``sqlite3.OperationalError: interrupted``, which
        the consumer seam classifies as INDEX_SNAPSHOT_DEADLINE.
        """
        import sqlite3

        owner, published, clock = self._deadline_scope_fixture(tmp_path, monkeypatch)

        with pytest.raises(sqlite3.OperationalError, match="interrupted"):
            with owner.read_existing_index_scope(
                published.snapshot_id, str(tmp_path), "gen-1"
            ) as (index, scope_conn):
                # The reader's SQL runs after the deadline has passed.
                clock["now"] += 100.0
                scope_conn.execute("SELECT x FROM t WHERE x LIKE '%7%'").fetchall()

    def test_read_existing_index_scope_post_read_deadline_check(
        self, tmp_path, monkeypatch
    ):
        """The post-yield re-check fires even when a reader swallows aborts.

        Codex P2 (#1299): a reader that absorbs the interrupt and returns a
        payload still cannot outlive the absolute deadline — the scope's own
        re-check raises INDEX_SNAPSHOT_DEADLINE after the yield.
        """
        import sqlite3

        owner, published, clock = self._deadline_scope_fixture(tmp_path, monkeypatch)

        with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_DEADLINE"):
            with owner.read_existing_index_scope(
                published.snapshot_id, str(tmp_path), "gen-1"
            ) as (index, scope_conn):
                clock["now"] += 100.0
                try:
                    scope_conn.execute("SELECT x FROM t WHERE x LIKE '%7%'").fetchall()
                except sqlite3.OperationalError:
                    pass  # reader swallows the abort

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


class TestWalSnapshotPath:
    """Phase B-1 回帰テスト: WAL read-only 接続によるスナップショット取得。"""

    @pytest.fixture(autouse=True)
    def _close_registry(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    @requires_posix_snapshot
    @pytest.mark.parametrize("sidecars", ["present", "absent"])
    async def test_wal_snapshot_does_not_change_source_directory(
        self, tmp_path, wal_project, sidecars
    ):
        # PR #1350：mode=ro 也可能创建 sidecar；必须对整个源缓存目录取证。
        import hashlib

        import tree_sitter_analyzer.index_snapshot as owner

        conn = wal_project
        db = tmp_path / ".ast-cache" / "index.db"
        conn.execute("PRAGMA wal_autocheckpoint=0")
        main_before = db.read_bytes()
        conn.execute("CREATE TABLE wal_only(value TEXT)")
        conn.execute("INSERT INTO wal_only VALUES ('committed')")
        owner.stamp_full_index_manifest(conn, str(tmp_path))
        assert db.read_bytes() == main_before
        if sidecars == "absent":
            # 让 SQLite 正常 checkpoint/关闭，不手工删除 sidecar。
            conn.close()

        def source_state():
            return {
                path.name: (
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                    path.stat().st_ctime_ns,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in db.parent.iterdir()
            }

        before = source_state()
        assert set(before) == (
            {"index.db", "index.db-wal", "index.db-shm"}
            if sidecars == "present"
            else {"index.db"}
        )
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()), str(db), deadline=owner._clock() + 10
        )
        after = source_state()
        assert set(after) == set(before), (
            f"source before={sorted(before)} after={sorted(after)}"
        )
        assert after == before
        assert (
            snapshot.completeness,
            snapshot.symbol_projection_exact,
            snapshot.reason,
        ) == ("complete", True, None)
        with owner.read_existing_index_scope(
            snapshot.snapshot_id, str(tmp_path), snapshot.source_generation
        ) as (_, reader):
            assert [r[0] for r in reader.execute("SELECT value FROM wal_only")] == [
                "committed"
            ]

    @requires_posix_snapshot
    @pytest.mark.parametrize("corrupt", [False, True])
    async def test_detached_wal_without_shm_recovers_or_rejects_all_frames(
        self, tmp_path, wal_project, corrupt
    ):
        # PR #1350：从真实已提交 WAL 建立无 SHM 的源缓存，不能回退到旧主库的完整状态。
        import tree_sitter_analyzer.index_snapshot as owner

        target = tmp_path / "detached"
        target.mkdir()
        (target / "sample.py").write_bytes((tmp_path / "sample.py").read_bytes())
        conn = wal_project
        conn.execute("PRAGMA wal_autocheckpoint=0")
        owner.stamp_full_index_manifest(conn, str(target))
        source_db = tmp_path / ".ast-cache" / "index.db"
        source_wal = source_db.with_name("index.db-wal")
        previous_size = source_wal.stat().st_size
        conn.execute("CREATE TABLE wal_only(value TEXT)")
        conn.execute("INSERT INTO wal_only VALUES ('committed')")
        owner.stamp_full_index_manifest(conn, str(target))
        cache_dir = target / ".ast-cache"
        cache_dir.mkdir()
        db = cache_dir / "index.db"
        wal = cache_dir / "index.db-wal"
        db.write_bytes(source_db.read_bytes())
        payload = bytearray(source_wal.read_bytes())
        if corrupt:
            payload[previous_size + 24] ^= 1
        wal.write_bytes(payload)
        before = {p.name: p.read_bytes() for p in cache_dir.iterdir()}
        snapshot = owner.read_existing_snapshot(str(target))
        assert {p.name: p.read_bytes() for p in cache_dir.iterdir()} == before
        if corrupt:
            assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
                None,
                "unknown",
                "CONCURRENT_WRITER",
            )
        else:
            assert (snapshot.completeness, snapshot.reason) == ("complete", None)
            with owner.read_existing_index_scope(
                snapshot.snapshot_id, str(target), snapshot.source_generation
            ) as (_, reader):
                assert [r[0] for r in reader.execute("SELECT value FROM wal_only")] == [
                    "committed"
                ]

    @requires_posix_snapshot
    async def test_wal_commit_during_file_copy_is_unknown_and_retryable(
        self, tmp_path, wal_project, monkeypatch
    ):
        # PR #1350：复制主库时真实提交 WAL，不能拼接两代文件后发布 token。
        import tree_sitter_analyzer.index_snapshot as owner
        import tree_sitter_analyzer.index_snapshot_capability as capability

        conn = wal_project
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("CREATE TABLE wal_only(value TEXT)")
        conn.execute("INSERT INTO wal_only VALUES ('before')")
        owner.stamp_full_index_manifest(conn, str(tmp_path))
        db = tmp_path / ".ast-cache" / "index.db"
        inode = db.stat().st_ino
        read = os.read
        fired = []

        def read_with_commit(fd, size):
            if not fired and os.fstat(fd).st_ino == inode:
                fired.append(True)
                conn.execute("INSERT INTO wal_only VALUES ('during')")
                owner.stamp_full_index_manifest(conn, str(tmp_path))
            return read(fd, size)

        monkeypatch.setattr(capability.os, "read", read_with_commit)
        snapshot = owner.read_existing_snapshot(str(tmp_path))
        assert fired == [True]
        assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
            None,
            "unknown",
            "CONCURRENT_WRITER",
        )
        retry = owner.read_existing_snapshot(str(tmp_path))
        assert (retry.completeness, retry.reason) == ("complete", None)
        with owner.read_existing_index_scope(
            retry.snapshot_id, str(tmp_path), retry.source_generation
        ) as (_, reader):
            assert [
                r[0]
                for r in reader.execute("SELECT value FROM wal_only ORDER BY value")
            ] == ["before", "during"]

    @pytest.fixture
    def wal_source(self):
        return "def answer():\n    return 42\n"

    @pytest.fixture
    async def wal_project(self, tmp_path, wal_source):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        if wal_source is not None:
            (tmp_path / "sample.py").write_text(wal_source, encoding="utf-8")
        build = await CodeGraphFullIndexTool(str(tmp_path)).execute({"mode": "full"})
        assert (build["success"], build["verdict"]) == (True, "INFO")
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        try:
            assert conn.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
            # PR #1350：保持真实非空 WAL 与写端连接，核验不能依赖已 checkpoint 的主库。
            conn.execute("INSERT INTO ast_cache_metadata VALUES ('wal_test', 'active')")
            conn.commit()
            assert (tmp_path / ".ast-cache" / "index.db-wal").read_bytes()[:4] in {
                b"\x37\x7f\x06\x82",
                b"\x37\x7f\x06\x83",
            }
            yield conn
        finally:
            conn.close()

    @requires_posix_snapshot
    @pytest.mark.parametrize(
        ("wal_source", "expected_names"),
        [
            ("def answer():\n    return 42\n", ["answer"]),
            ("# no symbols\n", []),
            (None, []),
        ],
    )
    async def test_wal_projection_certifies_readonly_ordinary_consumer(
        self, tmp_path, wal_project, expected_names, monkeypatch
    ):
        # PR #1350：完整与零符号项目都需真实核验；控制写入只允许在私有内存副本。
        import tree_sitter_analyzer.index_snapshot as owner

        observed = []
        validator = owner.symbol_projection_is_exact

        def record_validation(conn, **kwargs):
            observed.append(
                (
                    conn.execute("PRAGMA query_only").fetchone()[0],
                    conn.execute("PRAGMA database_list").fetchone()[2],
                    kwargs["require_fts"],
                )
            )
            return validator(conn, **kwargs)

        monkeypatch.setattr(owner, "symbol_projection_is_exact", record_validation)
        root = str(tmp_path.resolve())
        db = tmp_path / ".ast-cache" / "index.db"
        wal = db.with_name("index.db-wal")
        before = (db.read_bytes(), wal.read_bytes())
        snapshot = owner._capture_wal_snapshot(
            root, str(db), deadline=owner._clock() + 10
        )
        assert (
            snapshot.completeness,
            snapshot.symbol_projection_exact,
            snapshot.reason,
        ) == ("complete", True, None)
        with owner.read_existing_index_scope(
            snapshot.snapshot_id, root, snapshot.source_generation
        ) as (_, reader):
            assert [
                row[0]
                for row in reader.execute(
                    "SELECT name FROM ast_symbol_rows ORDER BY name"
                )
            ] == expected_names
            assert reader.execute("PRAGMA query_only").fetchone()[0] == 1
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                reader.execute("DELETE FROM ast_symbol_rows")
        assert observed == [(0, "", True)]
        assert (db.read_bytes(), wal.read_bytes()) == before

    @requires_posix_snapshot
    @pytest.mark.parametrize(
        "corruption", ["missing_rows", "changed_payload", "stale_fts_terms"]
    )
    async def test_wal_restamped_manifest_cannot_certify_corrupt_projection(
        self, tmp_path, wal_project, corruption
    ):
        # PR #1350：重签 manifest 只绑定索引字节，不能替代 ordinary/FTS 投影认证。
        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_symbol_projection import (
            upsert_symbol_projection_state,
        )

        conn = wal_project
        assert conn.execute("SELECT name FROM ast_symbol_rows").fetchall() == [
            ("answer",)
        ]
        if corruption == "missing_rows":
            conn.execute("DELETE FROM ast_symbol_rows")
        else:
            conn.execute("UPDATE ast_symbol_rows SET name='wrong'")
            if corruption == "stale_fts_terms":
                upsert_symbol_projection_state(conn, "sample.py")
                assert conn.execute(
                    "SELECT COUNT(*) FROM ast_symbols_fts_docsize"
                ).fetchone() == (1,)
        conn.commit()
        root = str(tmp_path.resolve())
        owner.stamp_full_index_manifest(conn, root)
        snapshot = owner._capture_wal_snapshot(
            root,
            str(tmp_path / ".ast-cache" / "index.db"),
            deadline=owner._clock() + 10,
        )
        with pytest.raises(ValueError, match="^INDEX_SNAPSHOT_INCOMPLETE$"):
            with owner.read_existing_index_scope(
                snapshot.snapshot_id, root, snapshot.source_generation
            ):
                pytest.fail("损坏投影不应到达 consumer")
        assert (
            snapshot.completeness,
            snapshot.symbol_projection_exact,
            snapshot.reason,
        ) == ("partial", False, "SYMBOL_PROJECTION_INCOMPLETE")

    @requires_posix_snapshot
    async def test_wal_projection_copy_obeys_byte_budget(
        self, tmp_path, wal_project, monkeypatch
    ):
        # PR #1350：只读核验也必须在分配内存副本前执行既有字节预算。
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(owner, "_BACKUP_BYTE_BUDGET", 0)
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()),
            str(tmp_path / ".ast-cache" / "index.db"),
            deadline=owner._clock() + 10,
        )
        assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
            None,
            "unknown",
            "INDEX_BACKUP_BUDGET",
        )

    @requires_posix_snapshot
    async def test_wal_projection_failure_closes_private_copy(
        self, tmp_path, wal_project, monkeypatch
    ):
        # PR #1350：核验异常不能发布能力，也不能泄漏私有数据库连接。
        import tree_sitter_analyzer.index_snapshot as owner

        copies = []

        def fail_validation(conn, **kwargs):
            copies.append(conn)
            raise RuntimeError("projection verification failed")

        monkeypatch.setattr(owner, "symbol_projection_is_exact", fail_validation)
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()),
            str(tmp_path / ".ast-cache" / "index.db"),
            deadline=owner._clock() + 10,
        )
        assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
            None,
            "unknown",
            "projection verification failed",
        )
        assert len(copies) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            copies[0].execute("SELECT 1")

    @requires_posix_snapshot
    async def test_wal_projection_lock_contention_fails_closed(
        self, tmp_path, wal_project, monkeypatch
    ):
        # PR #1350：等待内存核验锁超时，不得跳过核验或释放其他捕获者的锁。
        from unittest.mock import Mock

        import tree_sitter_analyzer.index_snapshot as owner

        lock = Mock()
        lock.acquire.return_value = False
        monkeypatch.setattr(owner, "_CAPTURE_LOCK", lock)
        snapshot = owner._capture_wal_snapshot(
            str(tmp_path.resolve()),
            str(tmp_path / ".ast-cache" / "index.db"),
            deadline=owner._clock() + 10,
        )
        assert (snapshot.snapshot_id, snapshot.completeness, snapshot.reason) == (
            None,
            "unknown",
            "INDEX_SNAPSHOT_DEADLINE",
        )
        assert lock.acquire.call_count == 1
        lock.release.assert_not_called()

    @pytest.mark.parametrize("deny_capture", [False, True])
    def test_wal_path_requires_supported_capture(
        self, tmp_path, monkeypatch, deny_capture
    ):
        """PR #1350：未获资格时不读库；支持的平台必须实际诊断损坏索引。"""
        import tree_sitter_analyzer.index_snapshot as owner
        import tree_sitter_analyzer.index_snapshot_capability as capability

        cache_dir = tmp_path / ".ast-cache"
        cache_dir.mkdir()
        # 缺失 schema 表的 SQLite 错误由快照打开边界归类。
        (cache_dir / "index.db").write_bytes(b"")
        if deny_capture:
            monkeypatch.setattr(capability, "_WAL_FD_COPY_SUPPORTED", False)
        supported = capability._WAL_FD_COPY_SUPPORTED and (
            (os.name == "posix" and hasattr(os, "O_NOFOLLOW"))
            or (os.name == "nt" and capability._WINDOWS_WAL_SUPPORTED)
        )
        if not supported:
            monkeypatch.setattr(
                capability,
                "open_bound_database",
                lambda *_a, **_k: pytest.fail("unsupported capture opened source"),
            )
            monkeypatch.setattr(
                owner.sqlite3,
                "connect",
                lambda *_a, **_k: pytest.fail("unsupported capture opened SQLite"),
            )
        result = owner._capture_wal_snapshot(
            str(tmp_path.resolve()),
            str(cache_dir / "index.db"),
            deadline=owner._clock() + 10,
        )
        assert (result.snapshot_id, result.completeness, result.reason) == (
            None,
            "unknown",
            "CORRUPT_INDEX" if supported else "WAL_PRIVATE_SNAPSHOT_UNSUPPORTED",
        )

    def test_capture_snapshot_on_windows_no_longer_unknown_unsupported(
        self, tmp_path, monkeypatch
    ):
        """即使数据库有效，未支持的 Windows 私有捕获也只能返回 unknown。"""
        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.ast_cache import ASTCache

        # 有効な SQLite DB を作成しておく (WAL 接続が成功するため)
        source = tmp_path / "sample.py"
        source.write_text("x = 1\n", encoding="utf-8")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        cache.close()

        # 非 POSIX 環境をシミュレート
        monkeypatch.setattr(owner.os, "name", "nt")
        monkeypatch.setattr(owner.os.path, "exists", lambda path: path != "/dev/fd")

        result = owner.read_existing_snapshot(str(tmp_path))
        # PR #1350：不得为了保留旧成功结果而连接源库创建 sidecar。
        assert (result.completeness, result.reason) == (
            "unknown",
            "WAL_PRIVATE_SNAPSHOT_UNSUPPORTED",
        )

    def test_wal_readonly_connection_consistent_view(self, tmp_path):
        """WAL mode DB に concurrent write 中でも read-only 接続が一貫ビューを返す統合テスト。
        Phase B-1 の WAL snapshot isolation を検証する。"""
        import sqlite3

        db_path = tmp_path / "test.db"

        # WAL mode DB を作成
        writer_conn = sqlite3.connect(str(db_path))
        writer_conn.execute("PRAGMA journal_mode=WAL")
        writer_conn.execute("CREATE TABLE t (v INTEGER)")
        writer_conn.execute("INSERT INTO t VALUES (1)")
        writer_conn.commit()

        # read-only 接続で BEGIN (WAL reader slot)
        uri = f"file:{db_path.as_uri().replace('file://', '')}?mode=ro"
        reader_conn = sqlite3.connect(uri, uri=True, isolation_level=None)
        reader_conn.execute("BEGIN")

        snapshot_val = reader_conn.execute("SELECT v FROM t").fetchone()[0]

        # concurrent writer が INSERT
        writer_conn.execute("INSERT INTO t VALUES (2)")
        writer_conn.commit()
        writer_conn.close()

        # reader は BEGIN 時点のビューを保持している (v=1 のみ)
        val_after_write = reader_conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        reader_conn.close()

        # WAL reader は BEGIN 時点の snapshot を見る → COUNT は 1
        assert snapshot_val == 1
        assert val_after_write == 1

    @pytest.mark.parametrize("deny_capture", [False, True])
    def test_wal_snapshot_stat_mismatch_falls_back_to_concurrent_writer(
        self, tmp_path, monkeypatch, deny_capture
    ):
        """PR #1350：支持时验证真实身份漂移；未获资格时禁止尝试读取。"""
        import tree_sitter_analyzer.index_snapshot as owner
        import tree_sitter_analyzer.index_snapshot_capability as capability
        from tree_sitter_analyzer.ast_cache import ASTCache

        # 准备真实索引，平台资格只约束新增只读捕获，不约束普通索引创建。
        source = tmp_path / "sample.py"
        source.write_text("x = 1\n", encoding="utf-8")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        cache.close()

        if deny_capture:
            monkeypatch.setattr(capability, "_WAL_FD_COPY_SUPPORTED", False)
        supported = capability._WAL_FD_COPY_SUPPORTED and (
            (os.name == "posix" and hasattr(os, "O_NOFOLLOW"))
            or (os.name == "nt" and capability._WINDOWS_WAL_SUPPORTED)
        )
        db = tmp_path / ".ast-cache" / "index.db"
        before = db.stat()
        read = os.read
        changed = []

        def read_with_mtime_change(fd, size):
            assert supported, "unsupported capture attempted source read"
            if not changed:
                changed.append(True)
                os.utime(
                    db, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000)
                )
            return read(fd, size)

        monkeypatch.setattr(capability.os, "read", read_with_mtime_change)
        result = owner._capture_wal_snapshot(
            str(tmp_path.resolve()), str(db), deadline=owner._clock() + 10
        )
        assert changed == ([True] if supported else [])
        assert (result.snapshot_id, result.completeness, result.reason) == (
            None,
            "unknown",
            "CONCURRENT_WRITER" if supported else "WAL_PRIVATE_SNAPSHOT_UNSUPPORTED",
        )

    def test_wal_without_descriptor_identity_support_never_opens_sqlite(
        self, tmp_path, monkeypatch
    ):
        """不具备身份绑定能力时，连 SQLite 打开都不允许发生。"""
        import tree_sitter_analyzer.index_snapshot as owner
        import tree_sitter_analyzer.index_snapshot_capability as capability
        from tree_sitter_analyzer.ast_cache import ASTCache

        # 有効な SQLite DB を作成
        source = tmp_path / "sample.py"
        source.write_text("x = 1\n", encoding="utf-8")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        cache.close()

        opened = []

        def forbidden_open(*args, **kwargs):
            opened.append(args)
            pytest.fail("不支持的平台不能打开 SQLite")

        monkeypatch.setattr(capability, "_WAL_FD_COPY_SUPPORTED", False)
        monkeypatch.setattr(owner.sqlite3, "connect", forbidden_open)
        result = owner._capture_wal_snapshot(
            str(tmp_path.resolve()),
            str(tmp_path / ".ast-cache" / "index.db"),
            deadline=owner._clock() + 10,
        )
        assert (result.completeness, result.reason) == (
            "unknown",
            "WAL_PRIVATE_SNAPSHOT_UNSUPPORTED",
        )
        assert opened == []
