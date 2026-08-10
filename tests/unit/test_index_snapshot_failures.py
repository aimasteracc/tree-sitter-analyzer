"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool


class TestSnapshotFailureContracts:
    @staticmethod
    def _certified_cache(root):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = root / "sample.py"
        source.write_text("value = 1\n")
        cache = ASTCache(str(root))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(root))
        cache.close()

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
        with pytest.raises(ValueError, match="INDEX_SNAPSHOT_ROOT_MISMATCH"):
            with owner.acquire_index_snapshot(
                published.snapshot_id, str(tmp_path / "other")
            ):
                pass

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
        monkeypatch.setattr(owner.time, "monotonic", lambda: 1000.0)
        owner.REGISTRY._entries[published.snapshot_id].expires_at = 1.0
        owner.REGISTRY.ensure_capacity(0)
        assert published.snapshot_id not in owner.REGISTRY._entries

    def test_non_posix_secure_snapshot_is_explicitly_unsupported(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(owner.os, "name", "nt")
        result = owner.read_existing_snapshot(str(tmp_path))
        assert result.completeness == "unknown"
        assert result.reason == "SECURE_FD_SNAPSHOT_UNSUPPORTED"

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

    @pytest.mark.asyncio
    async def test_persisted_build_marker_is_concurrent_writer(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.cache.build_state import mark_build_in_progress

        self._certified_cache(tmp_path)
        cache = ASTCache(str(tmp_path))
        mark_build_in_progress(cache.get_conn())
        cache.close()
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "CONCURRENT_WRITER"

    @pytest.mark.asyncio
    async def test_unknown_source_scope_never_returns_complete(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_snapshot import CurrentSourceSnapshot

        self._certified_cache(tmp_path)
        monkeypatch.setattr(
            owner,
            "capture_current_source_snapshot",
            lambda _root: CurrentSourceSnapshot(
                (), None, None, "unknown", "SOURCE_SCAN_DEADLINE"
            ),
        )
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "SOURCE_SCAN_DEADLINE"

    @pytest.mark.asyncio
    async def test_backup_page_budget_fails_closed(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        self._certified_cache(tmp_path)
        monkeypatch.setattr(owner, "_BACKUP_PAGE_BUDGET", -1)
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "INDEX_BACKUP_BUDGET"

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

    def test_schema_validation_rejects_missing_tables(self):
        from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_schema_version(version INTEGER)")
        conn.execute("INSERT INTO ast_schema_version VALUES(13)")
        with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
            validate_snapshot_schema(conn)
        conn.close()

    def test_schema_validation_rejects_missing_columns(self):
        from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_schema_version(version INTEGER)")
        conn.execute("INSERT INTO ast_schema_version VALUES(13)")
        for table in (
            "ast_index",
            "ast_symbol_rows",
            "ast_imports",
            "edges",
            "ast_index_snapshot_manifest",
        ):
            conn.execute(f'CREATE TABLE "{table}"(wrong INTEGER)')
        with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
            validate_snapshot_schema(conn)
        conn.close()

    def test_fingerprint_row_budget_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_schema as schema

        self._certified_cache(tmp_path)
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        monkeypatch.setattr(schema, "_FINGERPRINT_ROW_BUDGET", -1)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema.index_fingerprint(conn, str(tmp_path.resolve()))
        conn.close()

    def test_fingerprint_byte_budget_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_schema as schema

        self._certified_cache(tmp_path)
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        monkeypatch.setattr(schema, "_FINGERPRINT_BYTE_BUDGET", -1)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema.index_fingerprint(conn, str(tmp_path.resolve()))
        conn.close()

    def test_snapshot_migration_ignores_unsupported_database(self):
        from tree_sitter_analyzer.index_snapshot_schema import apply_snapshot_migration

        class Broken:
            def executescript(self, _sql):
                raise sqlite3.OperationalError("unsupported")

        apply_snapshot_migration(Broken(), lambda *_args: None)

    def test_missing_project_root_is_distinguished(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        with pytest.raises(FileNotFoundError, match="MISSING_PROJECT_ROOT"):
            owner._open_bound_database(str(tmp_path / "absent"))

    def test_missing_index_database_closes_bound_directories(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        (tmp_path / ".ast-cache").mkdir()
        with pytest.raises(FileNotFoundError, match="MISSING_INDEX"):
            owner._open_bound_database(str(tmp_path))

    def test_nonregular_index_database_is_rejected(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        (tmp_path / ".ast-cache" / "index.db").mkdir(parents=True)
        with pytest.raises(ValueError, match="INDEX_PATH_UNSAFE"):
            owner._open_bound_database(str(tmp_path))

    def test_cache_open_error_closes_root_handle(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        original_open = owner.os.open

        def fail_cache(path, flags, *args, **kwargs):
            if path == ".ast-cache":
                raise PermissionError("cache denied")
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(owner.os, "open", fail_cache)
        with pytest.raises(PermissionError, match="cache denied"):
            owner._open_bound_database(str(tmp_path))

    def test_database_open_error_closes_directory_handles(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        (tmp_path / ".ast-cache").mkdir()
        original_open = owner.os.open

        def fail_database(path, flags, *args, **kwargs):
            if path == "index.db":
                raise PermissionError("database denied")
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(owner.os, "open", fail_database)
        with pytest.raises(PermissionError, match="database denied"):
            owner._open_bound_database(str(tmp_path))

    def test_empty_regular_sidecar_is_not_a_concurrent_writer(self, tmp_path):
        import os

        import tree_sitter_analyzer.index_snapshot as owner

        cache = tmp_path / ".ast-cache"
        cache.mkdir()
        (cache / "index.db-wal").touch()
        fd = os.open(cache, os.O_RDONLY)
        try:
            owner._reject_sidecars(fd)
        finally:
            os.close(fd)
        assert (cache / "index.db-wal").stat().st_size == 0

    def test_index_fingerprint_deadline_is_enforced(self, monkeypatch):
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_snapshot_schema as schema

        monkeypatch.setattr(schema, "time", SimpleNamespace(monotonic=lambda: 2.0))
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
            schema._check_deadline(1.0)

    def test_source_capture_maps_scan_deadline_to_unknown(self, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(
            source,
            "_inventory",
            lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
        )
        result = source.capture_current_source_snapshot(".")
        assert result.reason == "SOURCE_SCAN_DEADLINE"

    def test_source_capture_maps_capacity_to_unbounded(self, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(
            source,
            "_inventory",
            lambda *_a, **_k: (_ for _ in ()).throw(OverflowError()),
        )
        result = source.capture_current_source_snapshot(".")
        assert result.reason == "SOURCE_SCOPE_UNBOUNDED"

    def test_source_capture_maps_io_error_to_unreadable(self, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(
            source, "_inventory", lambda *_a, **_k: (_ for _ in ()).throw(OSError())
        )
        result = source.capture_current_source_snapshot(".")
        assert result.reason == "SOURCE_SCOPE_UNREADABLE"

    def test_duplicate_source_scope_is_unsafe(self, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        inventories = iter(
            [
                (("a.py", "meta|hash", "python"), ("a.py", "meta|hash", "python")),
                (("a.py", "meta", "python"),),
            ]
        )
        monkeypatch.setattr(
            source, "_inventory", lambda *_a, **_k: (next(inventories), False)
        )
        result = source.capture_current_source_snapshot(".")
        assert result.state == "unsafe"

    def test_inventory_deadline_before_scan(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source.time, "monotonic", lambda: 2.0)
        with pytest.raises(TimeoutError):
            source._inventory(str(tmp_path), 1.0, with_content=True)

    def test_inventory_deadline_before_entry(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_text("x = 1")
        from types import SimpleNamespace

        ticks = iter((0.0, 2.0))
        monkeypatch.setattr(
            source, "time", SimpleNamespace(monotonic=lambda: next(ticks))
        )
        with pytest.raises(TimeoutError):
            source._inventory(str(tmp_path), 1.0, with_content=True)

    def test_inventory_descends_into_supported_nested_scope(self, tmp_path):
        import tree_sitter_analyzer.index_source_snapshot as source

        nested = tmp_path / "pkg"
        nested.mkdir()
        (nested / "sample.py").write_text("x = 1")
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert ([row[0] for row in rows], unsafe) == (["pkg/sample.py"], False)

    def test_inventory_omits_unsupported_files(self, tmp_path):
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "notes.txt").write_text("ignored")
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows, unsafe) == ((), False)

    def test_inventory_file_capacity_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_text("x = 1")
        monkeypatch.setattr(source, "DEFAULT_INDEX_MAX_FILES", 0)
        with pytest.raises(OverflowError):
            source._inventory(str(tmp_path), float("inf"), with_content=True)

    def test_inventory_byte_capacity_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_text("x = 1")
        monkeypatch.setattr(source, "_SOURCE_BYTE_BUDGET", 0)
        with pytest.raises(OverflowError):
            source._inventory(str(tmp_path), float("inf"), with_content=True)

    def test_inventory_open_error_marks_source_unsafe(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_text("x = 1")
        monkeypatch.setattr(
            source.os,
            "open",
            lambda *_a, **_k: (_ for _ in ()).throw(PermissionError()),
        )
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows[0][1].endswith("|<unsafe>"), unsafe) == (True, True)

    def test_inventory_read_deadline_closes_file(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_text("x = 1")
        from types import SimpleNamespace

        ticks = iter((0.0, 0.0, 2.0))
        monkeypatch.setattr(
            source, "time", SimpleNamespace(monotonic=lambda: next(ticks))
        )
        with pytest.raises(TimeoutError):
            source._inventory(str(tmp_path), 1.0, with_content=True)

    def test_inventory_metadata_change_marks_hash_unsafe(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_text("x = 1")
        original = source._metadata_marker
        calls = 0

        def changed_marker(info):
            nonlocal calls
            calls += 1
            return original(info) + (":changed" if calls == 2 else "")

        monkeypatch.setattr(source, "_metadata_marker", changed_marker)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (len(rows), unsafe) == (1, True)

    def test_supported_nonregular_source_is_unsafe(self, tmp_path):
        import os

        import tree_sitter_analyzer.index_source_snapshot as source

        fifo = tmp_path / "pipe.py"
        os.mkfifo(fifo)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows[0][1].endswith("|<unsafe>"), unsafe) == (True, True)

    def test_status_rejects_non_read_existing_access_mode(self, tmp_path):
        with pytest.raises(ValueError, match="read_existing"):
            CodeGraphStatusTool(str(tmp_path)).validate_arguments(
                {"access_mode": "write"}
            )
