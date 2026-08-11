"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import hashlib
import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


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

        self._certified_cache(tmp_path)
        monkeypatch.setattr(owner.os, "name", "nt")
        result = owner.read_existing_snapshot(str(tmp_path))
        assert result.completeness == "unknown"
        assert result.reason == "SECURE_FD_SNAPSHOT_UNSUPPORTED"

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

    @requires_posix_fd
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
            lambda _root, _scope=None: CurrentSourceSnapshot(
                (), None, None, "unknown", "SOURCE_SCAN_DEADLINE"
            ),
        )
        result = await CodeGraphStatusTool(str(tmp_path)).execute(
            {"output_format": "json"}
        )
        assert result["completeness"] == "unknown"
        assert result["oracle_reason"] == "SOURCE_SCAN_DEADLINE"

    @requires_posix_fd
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

    @requires_posix_fd
    def test_pinned_path_stat_failure_reports_mismatch(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        monkeypatch.setattr(
            owner.os, "stat", lambda *_a, **_k: (_ for _ in ()).throw(OSError())
        )
        assert owner._path_matches_pinned_database(1, 2) is False

    @requires_posix_fd
    def test_missing_project_root_is_distinguished(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        with pytest.raises(FileNotFoundError, match="MISSING_PROJECT_ROOT"):
            owner._open_bound_database(str(tmp_path / "absent"))

    @requires_posix_fd
    def test_missing_index_database_closes_bound_directories(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        (tmp_path / ".ast-cache").mkdir()
        with pytest.raises(FileNotFoundError, match="MISSING_INDEX"):
            owner._open_bound_database(str(tmp_path))

    @requires_posix_fd
    def test_nonregular_index_database_is_rejected(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        (tmp_path / ".ast-cache" / "index.db").mkdir(parents=True)
        with pytest.raises(ValueError, match="INDEX_PATH_UNSAFE"):
            owner._open_bound_database(str(tmp_path))

    @requires_posix_fd
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

    @requires_posix_fd
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

    @requires_posix_fd
    def test_empty_regular_sidecar_is_not_a_concurrent_writer(self, tmp_path):
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

    def test_inventory_rejects_scope_root_escape(self, tmp_path):
        import tree_sitter_analyzer.index_source_snapshot as source

        scope = source.SourceScopeDescriptor(("../escape",), False, (), 20_000)
        with pytest.raises(OSError, match="source root escapes project"):
            source._inventory(str(tmp_path), float("inf"), scope, with_content=True)

    def test_inventory_file_capacity_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_text("x = 1")
        monkeypatch.setattr(source, "_SOURCE_PATH_BUDGET", 0)
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
        original_open = source.os.open

        def fail_source(name, flags, *args, **kwargs):
            if name == "sample.py":
                raise PermissionError
            return original_open(name, flags, *args, **kwargs)

        monkeypatch.setattr(source.os, "open", fail_source)
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
        monkeypatch.setattr(source, "_same_file_metadata", lambda *_args: False)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (len(rows), unsafe) == (1, True)

    @requires_posix_fd
    def test_supported_nonregular_source_is_unsafe(self, tmp_path):
        import tree_sitter_analyzer.index_source_snapshot as source

        fifo = tmp_path / "pipe.py"
        os.mkfifo(fifo)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows[0][1].endswith("|<unsafe>"), unsafe) == (True, True)

    @requires_posix_fd
    def test_nonempty_shm_does_not_block_quiescent_main_database(self, tmp_path):
        # PR #1253: WAL shared memory alone is not uncheckpointed write evidence.
        import tree_sitter_analyzer.index_snapshot as owner

        cache = tmp_path / ".ast-cache"
        cache.mkdir()
        (cache / "index.db-shm").write_bytes(b"shared-memory")
        fd = os.open(cache, os.O_RDONLY)
        try:
            owner._reject_sidecars(fd)
        finally:
            os.close(fd)
        assert (cache / "index.db-shm").read_bytes() == b"shared-memory"

    @requires_posix_fd
    def test_nonempty_wal_still_blocks_immutable_read(self, tmp_path):
        # PR #1253: WAL payload remains authoritative concurrent-write evidence.
        import tree_sitter_analyzer.index_snapshot as owner

        cache = tmp_path / ".ast-cache"
        cache.mkdir()
        (cache / "index.db-wal").write_bytes(b"wal")
        fd = os.open(cache, os.O_RDONLY)
        try:
            with pytest.raises(ValueError, match="CONCURRENT_WRITER"):
                owner._reject_sidecars(fd)
        finally:
            os.close(fd)

    def test_inventory_counts_unsupported_entries_against_absolute_budget(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: unsupported names cannot evade the enumeration budget.
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "notes.txt").write_text("ignored")
        monkeypatch.setattr(source, "_SOURCE_ENTRY_BUDGET", 0)
        with pytest.raises(OverflowError):
            source._inventory(str(tmp_path), float("inf"), with_content=True)

    @requires_posix_fd
    def test_inventory_opens_children_only_relative_to_pinned_descriptors(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: no traversed child may be reopened by workspace path.
        import tree_sitter_analyzer.index_source_snapshot as source

        nested = tmp_path / "pkg"
        nested.mkdir()
        (nested / "sample.py").write_text("x = 1\n")
        original_open = source.os.open
        calls = []

        def recording_open(name, flags, *args, **kwargs):
            calls.append((os.fspath(name), kwargs.get("dir_fd")))
            return original_open(name, flags, *args, **kwargs)

        monkeypatch.setattr(source.os, "open", recording_open)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)

        assert (rows[0][0], unsafe) == ("pkg/sample.py", False)
        assert calls[0] == (str(tmp_path), None)
        assert all("/" not in name and dir_fd is not None for name, dir_fd in calls[1:])

    def test_inventory_normalizes_crlf_split_across_read_chunks(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: CRLF state is preserved between bounded raw-byte chunks.
        import tree_sitter_analyzer.index_source_snapshot as source

        target = tmp_path / "sample.py"
        target.write_bytes(b"\r\n")
        original_read = source.os.read
        chunks = iter((b"\r", b"\n", b""))

        def split_read(fd, size):
            if size == 65536:
                return next(chunks)
            return original_read(fd, size)

        monkeypatch.setattr(source.os, "read", split_read)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        expected = hashlib.sha256(b"\n").hexdigest()
        assert (rows[0][1].split("|")[1], unsafe) == (expected, False)

    def test_portable_inventory_keeps_bounded_selection_semantics(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: non-POSIX platforms retain the same canonical inventory.
        import tree_sitter_analyzer.index_source_snapshot as source

        nested = tmp_path / "pkg"
        nested.mkdir()
        (nested / "sample.py").write_text("x = 1\r\n")
        (nested / "notes.txt").write_text("ignored")
        monkeypatch.setattr(source.os, "name", "nt")

        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)

        assert (rows[0][0], rows[0][2], unsafe) == ("pkg/sample.py", "python", False)

    def test_bounded_sort_emits_multiple_canonical_runs(self, monkeypatch):
        # PR #1253: inventories larger than one run use the heap merge path.
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source, "_SORT_CHUNK_SIZE", 2)
        ordered = tuple(source._bounded_sorted((3, 1, 2), deadline=float("inf")))
        assert ordered == (1, 2, 3)

    def test_bounded_sort_checks_deadline_for_each_merged_row(self, monkeypatch):
        # PR #1253: merge work cannot extend past the advertised scan deadline.
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_source_snapshot as source

        ticks = iter((0.0, 0.0, 2.0))
        monkeypatch.setattr(
            source, "time", SimpleNamespace(monotonic=lambda: next(ticks))
        )
        with pytest.raises(TimeoutError):
            tuple(source._bounded_sorted((1,), deadline=1.0))

    def test_inventory_fingerprint_checks_deadline_inside_each_row(self, monkeypatch):
        # PR #1253: per-value framing remains within the same deadline.
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_source_snapshot as source

        ticks = iter((0.0, 0.0, 0.0, 2.0))
        monkeypatch.setattr(
            source, "time", SimpleNamespace(monotonic=lambda: next(ticks))
        )
        with pytest.raises(TimeoutError):
            source.inventory_fingerprint((("a", "b", "c"),), deadline=1.0)

    def test_source_capture_maps_fingerprint_deadline_to_unknown(self, monkeypatch):
        # PR #1253: canonical hashing shares the source scan deadline.
        import tree_sitter_analyzer.index_source_snapshot as source

        inventories = iter(
            [
                (("a.py", "meta|hash", "python"),),
                (("a.py", "meta", "python"),),
            ]
        )
        monkeypatch.setattr(
            source, "_inventory", lambda *_a, **_k: (next(inventories), False)
        )
        monkeypatch.setattr(
            source,
            "inventory_fingerprint",
            lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
        )
        result = source.capture_current_source_snapshot(".")
        assert (result.state, result.reason) == ("unknown", "SOURCE_SCAN_DEADLINE")

    def test_inventory_rejects_non_directory_root(self, tmp_path, monkeypatch):
        # PR #1253: the pinned root must itself be a directory descriptor.
        import tree_sitter_analyzer.index_source_snapshot as source

        root = tmp_path / "root.py"
        root.write_text("x = 1")
        original_open = source.os.open

        def admit_file(path, flags, *args, **kwargs):
            if os.fspath(path) == str(root):
                flags &= ~getattr(os, "O_DIRECTORY", 0)
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(source.os, "open", admit_file)
        with pytest.raises(OSError, match="source root is not a directory"):
            source._inventory(str(root), float("inf"), with_content=True)

    def test_inventory_opens_declared_scope_root_relative_to_root_fd(self, tmp_path):
        # PR #1253: configured subroots are pinned with openat before traversal.
        import tree_sitter_analyzer.index_source_snapshot as source

        package = tmp_path / "pkg"
        package.mkdir()
        (package / "sample.py").write_text("x = 1")
        scope = source.make_source_scope_descriptor(roots=("pkg",))
        rows, unsafe = source._inventory(
            str(tmp_path), float("inf"), scope, with_content=True
        )
        assert ([row[0] for row in rows], unsafe) == (["pkg/sample.py"], False)

    def test_inventory_scope_root_open_failure_closes_pinned_fd(self, tmp_path):
        # PR #1253: failed openat traversal propagates without retaining descriptors.
        import tree_sitter_analyzer.index_source_snapshot as source

        scope = source.make_source_scope_descriptor(roots=("missing",))
        with pytest.raises(FileNotFoundError):
            source._inventory(str(tmp_path), float("inf"), scope, with_content=True)

    def test_recorded_fingerprint_deadline_is_fail_closed(self, monkeypatch):
        # PR #1253: writer-side canonical inventory hashing has the same deadline.
        import tree_sitter_analyzer.index_snapshot_schema as schema

        monkeypatch.setattr(
            schema,
            "recorded_source_rows",
            lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
        )
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
            schema.source_fingerprint(sqlite3.connect(":memory:"), ".")

    def test_status_rejects_non_read_existing_access_mode(self, tmp_path):
        with pytest.raises(ValueError, match="read_existing"):
            CodeGraphStatusTool(str(tmp_path)).validate_arguments(
                {"access_mode": "write"}
            )

    @requires_posix_fd
    def test_bound_database_disappearing_is_missing(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot as owner

        cache = tmp_path / ".ast-cache"
        cache.mkdir()
        (cache / "index.db").touch()
        monkeypatch.setattr(
            owner,
            "_open_bound_database",
            lambda *_args: (_ for _ in ()).throw(FileNotFoundError("MISSING_INDEX")),
        )
        result = owner.read_existing_snapshot(str(tmp_path))
        assert result.reason == "MISSING_INDEX"

    def test_no_fts_schema_still_creates_ordinary_symbol_rows(self):
        from tree_sitter_analyzer.cache import schema

        conn = sqlite3.connect(":memory:")
        available = schema.init_db(conn, None, lambda _conn: False, [])
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        assert available is False
        assert "ast_symbol_rows" in tables
        assert "ast_symbols_fts" not in tables
