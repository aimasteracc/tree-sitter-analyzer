"""Exact behavioral tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_fd = requires_posix_snapshot


class TestNonPosixSnapshotContract:
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

        assert result["oracle_reason"] == "INDEX_BACKUP_BUDGET"

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


def test_manifest_preflight_rejects_huge_control_cell_before_fetch():
    # PR #1253 thread 3756001898: control rows are size-checked inside SQLite.
    from tree_sitter_analyzer.index_snapshot import _read_bounded_manifest

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index_snapshot_manifest("
        "singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version)"
    )
    conn.execute(
        "INSERT INTO ast_index_snapshot_manifest VALUES "
        "(1, zeroblob(2097152), 'source', 'index', 0, '{}', 2)"
    )

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        _read_bounded_manifest(conn, float("inf"))

    conn.close()


def test_manifest_preflight_rejects_duplicate_singleton_rows():
    # PR #1253 thread 3756001898: malformed control tables remain bounded.
    from tree_sitter_analyzer.index_snapshot import _read_bounded_manifest

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index_snapshot_manifest("
        "singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version)"
    )
    conn.executemany(
        "INSERT INTO ast_index_snapshot_manifest VALUES (1, ?, 's', 'i', 0, '{}', 2)",
        [("first",), ("second",)],
    )
    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        _read_bounded_manifest(conn, float("inf"))
    conn.close()


def test_manifest_preflight_enforces_total_budget(monkeypatch):
    # PR #1253 thread 3756001898: aggregate scalar bytes are bounded before fetch.
    import tree_sitter_analyzer.index_snapshot as snapshot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index_snapshot_manifest("
        "singleton, canonical_root, source_fingerprint, index_fingerprint, "
        "file_count, source_scope_descriptor, manifest_version)"
    )
    conn.execute(
        "INSERT INTO ast_index_snapshot_manifest VALUES "
        "(1, zeroblob(10), zeroblob(10), zeroblob(10), 0, '{}', 2)"
    )
    monkeypatch.setattr(snapshot, "_MANIFEST_TOTAL_BYTE_BUDGET", 20)
    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(conn, float("inf"))
    conn.close()


def test_manifest_materialization_disappearance_fails_closed():
    # PR #1253 thread 3756001898: a preflight/fetch race cannot look absent.
    import tree_sitter_analyzer.index_snapshot as snapshot

    class EmptyCursor:
        def fetchone(self):
            return None

    class RacedConnection:
        def __init__(self):
            self.calls = 0

        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query):
            self.calls += 1
            if self.calls == 1:
                return iter([(1,)])
            if self.calls == 2:
                return iter([(1, 1, 1, 1, 2, 1)])
            return EmptyCursor()

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(RacedConnection(), float("inf"))  # type: ignore[arg-type]


def test_manifest_duplicate_count_rejects_before_length_preflight():
    # PR #1253 review 3756101926: ambiguity is rejected before any cell fetch.
    import tree_sitter_analyzer.index_snapshot as snapshot

    class DuplicateCountConnection:
        def __init__(self):
            self.queries = []

        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, query):
            self.queries.append(query)
            if query.startswith("SELECT COUNT(*)"):
                return iter([(2,)])
            raise AssertionError("length preflight reached")

    conn = DuplicateCountConnection()
    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(conn, float("inf"))  # type: ignore[arg-type]
    assert len(conn.queries) == 1


@pytest.mark.parametrize("rows", [[], [()], [("1",)], [(1,), (1,)]])
def test_manifest_count_scalar_shape_is_strict(rows):
    # PR #1253: the bounded aggregate must return exactly one integer scalar.
    import tree_sitter_analyzer.index_snapshot as snapshot

    class CountConnection:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query):
            return iter(rows)

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(  # type: ignore[arg-type]
            CountConnection(), float("inf")
        )


def test_manifest_missing_length_row_is_invalid():
    # PR #1253 review 3756101926: admitted singleton loss cannot look absent.
    import tree_sitter_analyzer.index_snapshot as snapshot

    class MissingLengthConnection:
        def __init__(self):
            self.calls = 0

        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, _query):
            self.calls += 1
            return iter([(1,)]) if self.calls == 1 else iter(())

    with pytest.raises(ValueError, match="INDEX_MANIFEST_INVALID"):
        snapshot._read_bounded_manifest(  # type: ignore[arg-type]
            MissingLengthConnection(), float("inf")
        )
