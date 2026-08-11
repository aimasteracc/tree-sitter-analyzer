"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
requires_posix_snapshot = requires_posix_fd
pytestmark = requires_posix_fd


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def test_scope_descriptor_constructor_rejects_manifest_oversize():
    # PR #1253: writers cannot construct a descriptor the reader rejects.
    from tree_sitter_analyzer.index_source_snapshot import SourceScopeDescriptor

    with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_TOO_LARGE"):
        SourceScopeDescriptor((".",), False, ("x" * (64 * 1024),), 20_000)


def test_scope_descriptor_canonical_encoder_enforces_shared_budget(monkeypatch):
    from tree_sitter_analyzer import index_source_scope as source

    scope = source.make_source_scope_descriptor()
    monkeypatch.setattr(source, "SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET", 1)

    with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_TOO_LARGE"):
        source.canonical_source_scope_descriptor(scope)


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
        assert (rows, unsafe) == (frozenset(), False)

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
        assert (next(iter(rows))[1].endswith("|<unsafe>"), unsafe) == (True, True)

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
        assert (next(iter(rows))[1].endswith("|<unsafe>"), unsafe) == (True, True)

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

        assert (next(iter(rows))[0], unsafe) == ("pkg/sample.py", False)
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
        assert (next(iter(rows))[1].split("|")[1], unsafe) == (expected, False)

    def test_portable_inventory_keeps_bounded_selection_semantics(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: pathname-only platforms fail closed without traversal.
        import tree_sitter_analyzer.index_source_snapshot as source

        nested = tmp_path / "pkg"
        nested.mkdir()
        (nested / "sample.py").write_text("x = 1\n")
        monkeypatch.setattr(source.os, "name", "nt")
        monkeypatch.setattr(
            source.os, "scandir", lambda *_args: pytest.fail("traversed")
        )

        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)

        assert (rows, unsafe) == (frozenset(), True)

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

    @requires_posix_fd
    def test_supported_suffix_directory_symlink_is_replay_unsafe(self, tmp_path):
        # PR #1253 review thread 3878: replay and writer reject the same alias.
        import tree_sitter_analyzer.index_source_snapshot as source

        target = tmp_path / "vendor"
        target.mkdir()
        (tmp_path / "vendor.py").symlink_to(target, target_is_directory=True)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)

        assert (len(rows), unsafe) == (1, True)

    @requires_posix_fd
    def test_literal_backslash_supported_path_is_replay_unsafe(self, tmp_path):
        # PR #1253 review thread 1266: POSIX names are never slash-normalized.
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "pkg\\sample.py").write_text("value = 1\n")
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)

        assert ({row[0] for row in rows}, unsafe) == ({"pkg\\sample.py"}, True)


def test_fifo_index_database_is_rejected_without_blocking(tmp_path):
    # PR #1253 review 3755216346: untrusted FIFO opens must be nonblocking.
    from tree_sitter_analyzer.index_snapshot_capability import open_bound_database

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    os.mkfifo(cache / "index.db")
    started = time.monotonic()
    with pytest.raises(ValueError, match="INDEX_PATH_UNSAFE"):
        open_bound_database(str(tmp_path))
    assert time.monotonic() - started < 0.2


def test_source_fingerprint_is_order_independent():
    # PR #1255: the set accumulator avoids full-inventory sort copies.
    import tree_sitter_analyzer.index_source_snapshot as source

    rows = (("b.py", "b", "python"), ("a.py", "a", "python"))
    assert source.inventory_fingerprint(rows) == source.inventory_fingerprint(
        reversed(rows)
    )


def test_source_fingerprint_rejects_duplicate_paths():
    # PR #1255: paths are unique inputs to the commutative accumulator.
    import tree_sitter_analyzer.index_source_snapshot as source

    rows = (("a.py", "one", "python"), ("a.py", "two", "python"))
    with pytest.raises(ValueError, match="SOURCE_INVENTORY_DUPLICATE_PATH"):
        source.inventory_fingerprint(rows)


def test_inventory_fingerprint_checks_deadline_inside_each_row(monkeypatch):
    # PR #1253: per-value framing remains within the same deadline.
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_source_snapshot as source

    ticks = iter((0.0, 0.0, 0.0, 2.0))
    monkeypatch.setattr(source, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    with pytest.raises(TimeoutError):
        source.inventory_fingerprint((("a", "b", "c"),), deadline=1.0)


def test_source_capture_maps_fingerprint_deadline_to_unknown(monkeypatch):
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


def test_source_fingerprint_checks_deadline_before_first_row(monkeypatch):
    # PR #1255: the accumulator checks time before retaining each path.
    import tree_sitter_analyzer.index_source_snapshot as source

    monkeypatch.setattr(source.time, "monotonic", lambda: 2.0)
    with pytest.raises(TimeoutError):
        source.inventory_fingerprint((("a.py", "hash", "python"),), deadline=1.0)


def test_recorded_rows_check_deadline_before_materializing(monkeypatch):
    # PR #1255: database inventory materialization shares the deadline.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.execute("INSERT INTO ast_index VALUES ('a.py', 'hash', 'python')")
    monkeypatch.setattr(source.time, "monotonic", lambda: 2.0)
    with pytest.raises(TimeoutError):
        source.recorded_source_rows(conn, deadline=1.0)
    conn.close()


def test_recorded_rows_reject_duplicate_paths():
    # PR #1255: persisted paths must be unique before set comparison.
    import tree_sitter_analyzer.index_source_snapshot as source

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, content_hash, language)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, 'python')",
        (("a.py", "one"), ("a.py", "two")),
    )
    with pytest.raises(ValueError, match="SOURCE_INVENTORY_DUPLICATE_PATH"):
        source.recorded_source_rows(conn)
    conn.close()


def test_recorded_fingerprint_deadline_is_fail_closed(monkeypatch):
    # PR #1253: writer-side canonical inventory hashing has the same deadline.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    monkeypatch.setattr(
        schema,
        "recorded_source_rows",
        lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
        schema.source_fingerprint(sqlite3.connect(":memory:"), ".")
