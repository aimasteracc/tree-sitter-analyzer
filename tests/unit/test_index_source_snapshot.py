"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import hashlib
import os
import stat

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

    def test_inventory_rejects_excess_roots_before_open(self, tmp_path, monkeypatch):
        # PR #1253 review 3755736553: root-count validation precedes every FD open.
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_source_snapshot as source

        scope = SimpleNamespace(roots=tuple(f"root-{index}" for index in range(65)))
        monkeypatch.setattr(
            source.os,
            "open",
            lambda *_args, **_kwargs: pytest.fail("opened FD before root-count check"),
        )

        with pytest.raises(OverflowError):
            source._inventory(
                str(tmp_path),
                float("inf"),
                scope,
                with_content=True,  # type: ignore[arg-type]
            )

    def test_inventory_later_scope_root_failure_closes_all_prior_fds(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 review 3755736553: later root failure closes prior pinned roots.
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "first").mkdir()
        scope = source.make_source_scope_descriptor(roots=("first", "missing"))
        original_open = source.os.open
        opened_first = []

        def recording_open(path, flags, *args, **kwargs):
            fd = original_open(path, flags, *args, **kwargs)
            if path == "first":
                opened_first.append(fd)
            return fd

        monkeypatch.setattr(source.os, "open", recording_open)
        with pytest.raises(FileNotFoundError):
            source._inventory(str(tmp_path), float("inf"), scope, with_content=True)

        assert (len(opened_first), _fd_is_closed(opened_first[0])) == (1, True)

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

    @requires_posix_fd
    def test_inventory_rejects_root_swapped_for_ordinary_directory(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3760944078: opened root identity must match its lstat.
        import tree_sitter_analyzer.index_source_snapshot as source

        root = tmp_path / "root"
        root.mkdir()
        (root / "old.py").write_text("old = 1\n")
        original_open = source.os.open
        swapped = False

        def swap_root(path, flags, *args, **kwargs):
            nonlocal swapped
            if os.fspath(path) == str(root) and not swapped:
                swapped = True
                root.rename(tmp_path / "old-root")
                root.mkdir()
                (root / "new.py").write_text("new = 1\n")
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(source.os, "open", swap_root)
        rows, unsafe = source._inventory(str(root), float("inf"), with_content=True)

        assert (rows, unsafe) == (frozenset(), True)

    @requires_posix_fd
    def test_capture_revalidates_each_leaf_after_final_inventory(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 review 3763655036: a final-pass leaf may change after its yield.
        import tree_sitter_analyzer.index_source_snapshot as source

        target = tmp_path / "sample.py"
        target.write_text("old = 1\n")
        original_inventory = source._inventory
        calls = 0

        def inventory_then_rewrite(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original_inventory(*args, **kwargs)
            if calls == 2:
                original_mtime = target.stat().st_mtime_ns
                target.write_text("new = 2\n")
                os.utime(target, ns=(original_mtime, original_mtime))
            return result

        monkeypatch.setattr(source, "_inventory", inventory_then_rewrite)
        snapshot = source.capture_current_source_snapshot(str(tmp_path))

        assert (calls, snapshot.state, snapshot.reason) == (
            2,
            "unsafe",
            "SOURCE_SCOPE_UNSAFE",
        )

    @requires_posix_fd
    def test_capture_epoch_rechecks_earlier_leaf_after_later_admission(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3763790622: one exact fd epoch closes post-check mutation.
        import tree_sitter_analyzer.index_source_snapshot as source

        first = tmp_path / "a.py"
        second = tmp_path / "b.py"
        first.write_text("old = 1\n")
        second.write_text("stable = 1\n")
        real_fstat = source.os.fstat
        source_fstats = 0

        def mutate_after_later_admission(fd):
            nonlocal source_fstats
            observed = real_fstat(fd)
            if stat.S_ISREG(observed.st_mode):
                source_fstats += 1
                if source_fstats == 2:
                    first.write_text("new = 2\n")
            return observed

        monkeypatch.setattr(source.os, "fstat", mutate_after_later_admission)
        rows = tuple(
            (path.name, source._metadata_marker(path.stat()), "python")
            for path in (first, second)
        )

        exact = source._revalidate_source_rows(str(tmp_path), rows, float("inf"))

        assert (exact, source_fstats) == (False, 3)

    @requires_posix_fd
    def test_capture_epoch_reauthenticates_ancestor_after_later_admission(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: a stable leaf fd cannot certify a replaced ancestor chain.
        import tree_sitter_analyzer.index_source_snapshot as source

        ancestor = tmp_path / "a"
        ancestor.mkdir()
        nested = ancestor / "x.py"
        later = tmp_path / "b.py"
        nested.write_text("old = 1\n")
        later.write_text("stable = 1\n")
        rows = (
            ("a/x.py", source._metadata_marker(nested.stat()), "python"),
            ("b.py", source._metadata_marker(later.stat()), "python"),
        )
        real_fstat = source.os.fstat
        source_fstats = 0

        def swap_ancestor_during_second_admission(fd):
            nonlocal source_fstats
            observed = real_fstat(fd)
            if stat.S_ISREG(observed.st_mode):
                source_fstats += 1
                if source_fstats == 2:
                    ancestor.rename(tmp_path / "old-a")
                    ancestor.mkdir()
                    (ancestor / "x.py").write_text("replacement = 1\n")
            return observed

        monkeypatch.setattr(source.os, "fstat", swap_ancestor_during_second_admission)

        exact = source._revalidate_source_rows(str(tmp_path), rows, float("inf"))

        assert (exact, source_fstats) == (False, 2)

    @requires_posix_fd
    def test_capture_reopens_root_after_final_inventory(self, tmp_path, monkeypatch):
        # PR #1253 review 3763401191: final inventory cannot authenticate a stale root.
        import tree_sitter_analyzer.index_source_snapshot as source

        root = tmp_path / "root"
        root.mkdir()
        (root / "old.py").write_text("old = 1\n")
        original_inventory = source._inventory
        calls = 0

        def inventory_then_swap(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original_inventory(*args, **kwargs)
            if calls == 2:
                root.rename(tmp_path / "old-root")
                root.mkdir()
                (root / "new.py").write_text("new = 1\n")
            return result

        monkeypatch.setattr(source, "_inventory", inventory_then_swap)
        snapshot = source.capture_current_source_snapshot(str(root))

        assert (calls, snapshot.state, snapshot.reason) == (
            2,
            "unsafe",
            "SOURCE_SCOPE_UNSAFE",
        )

    @requires_posix_fd
    def test_inventory_rejects_child_swapped_for_ordinary_directory(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3760944078: openat must bind the enumerated child identity.
        import tree_sitter_analyzer.index_source_snapshot as source

        child = tmp_path / "pkg"
        child.mkdir()
        (child / "old.py").write_text("old = 1\n")
        original_open = source.os.open
        swapped = False

        def swap_child(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "pkg" and kwargs.get("dir_fd") is not None and not swapped:
                swapped = True
                child.rename(tmp_path / "old-pkg")
                child.mkdir()
                (child / "new.py").write_text("new = 1\n")
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(source.os, "open", swap_child)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)

        assert (rows, unsafe) == (frozenset(), True)

    @requires_posix_fd
    def test_inventory_rejects_declared_scope_swapped_for_ordinary_directory(
        self, tmp_path, monkeypatch
    ):
        # PR #1253 thread 3760944078: configured openat roots retain lstat identity.
        import tree_sitter_analyzer.index_source_snapshot as source

        child = tmp_path / "pkg"
        child.mkdir()
        (child / "old.py").write_text("old = 1\n")
        scope = source.make_source_scope_descriptor(roots=("pkg",))
        original_open = source.os.open
        swapped = False

        def swap_child(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "pkg" and kwargs.get("dir_fd") is not None and not swapped:
                swapped = True
                child.rename(tmp_path / "old-pkg")
                child.mkdir()
                (child / "new.py").write_text("new = 1\n")
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(source.os, "open", swap_child)
        rows, unsafe = source._inventory(
            str(tmp_path), float("inf"), scope, with_content=True
        )

        assert (rows, unsafe) == (frozenset(), True)


def test_revalidate_source_rows_enforces_absolute_deadline(tmp_path):
    from tree_sitter_analyzer.index_source_snapshot import _revalidate_source_rows

    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    with pytest.raises(TimeoutError):
        _revalidate_source_rows(str(tmp_path), (("app.py", "marker", "python"),), -1.0)


@requires_posix_fd
def test_revalidate_source_rows_rejects_root_identity_change(tmp_path, monkeypatch):
    # PR #1253: reopening the root must authenticate the inventoried root identity.
    import tree_sitter_analyzer.index_source_snapshot as source

    monkeypatch.setattr(source, "opened_entry_matches", lambda *_args: False)

    assert source._revalidate_source_rows(str(tmp_path), (), float("inf")) is False


@requires_posix_fd
def test_revalidate_source_rows_rejects_noncanonical_relative_path(tmp_path):
    # PR #1253: replay rejects path components that could escape the pinned root.
    import tree_sitter_analyzer.index_source_snapshot as source

    rows = (("../app.py", "marker", "python"),)

    assert source._revalidate_source_rows(str(tmp_path), rows, float("inf")) is False


@requires_posix_fd
def test_revalidate_source_rows_fails_closed_on_initial_leaf_open_error(
    tmp_path, monkeypatch
):
    # PR #1253: an admission failure cannot retain or authenticate a partial chain.
    import tree_sitter_analyzer.index_source_snapshot as source

    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    rows = ((target.name, source._metadata_marker(target.stat()), "python"),)
    real_stat = source.os.stat
    stat_calls = 0

    def fail_initial_leaf(*args, **kwargs):
        nonlocal stat_calls
        stat_calls += 1
        if stat_calls == 2:
            raise PermissionError("leaf unavailable")
        return real_stat(*args, **kwargs)

    monkeypatch.setattr(source.os, "stat", fail_initial_leaf)

    exact = source._revalidate_source_rows(str(tmp_path), rows, float("inf"))

    assert (exact, stat_calls) == (False, 2)


@requires_posix_fd
def test_revalidate_source_rows_tolerates_absent_cleanup_local(tmp_path, monkeypatch):
    # PR #1253: both short-lived chain phases guard cleanup before consulting fds.
    import tree_sitter_analyzer.index_source_snapshot as source

    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    rows = ((target.name, source._metadata_marker(target.stat()), "python"),)
    real_open = source.os.open
    real_dup = source.os.dup
    real_close = source.os.close
    opened_fds = []

    def recording_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened_fds.append(fd)
        return fd

    def recording_dup(fd):
        duplicate = real_dup(fd)
        opened_fds.append(duplicate)
        return duplicate

    monkeypatch.setattr(source.os, "open", recording_open)
    monkeypatch.setattr(source.os, "dup", recording_dup)
    monkeypatch.setattr(source, "locals", lambda: {}, raising=False)
    try:
        exact = source._revalidate_source_rows(str(tmp_path), rows, float("inf"))
    finally:
        for fd in reversed(opened_fds):
            try:
                real_close(fd)
            except OSError:
                pass

    assert exact is True


@requires_posix_fd
def test_revalidate_source_rows_rejects_changed_pinned_ancestor(tmp_path, monkeypatch):
    # PR #1253: every reuse of a pinned ancestor must retain its admitted identity.
    import tree_sitter_analyzer.index_source_snapshot as source

    package = tmp_path / "pkg"
    package.mkdir()
    first = package / "a.py"
    second = package / "b.py"
    first.write_text("first = 1\n", encoding="utf-8")
    second.write_text("second = 1\n", encoding="utf-8")
    matches = iter((True, True, True, False))
    identity_checks = 0

    def reject_reused_ancestor(*_args):
        nonlocal identity_checks
        identity_checks += 1
        return next(matches)

    monkeypatch.setattr(source, "opened_entry_matches", reject_reused_ancestor)
    rows = tuple(
        (f"pkg/{path.name}", source._metadata_marker(path.stat()), "python")
        for path in (first, second)
    )

    exact = source._revalidate_source_rows(str(tmp_path), rows, float("inf"))

    assert (exact, identity_checks) == (False, 4)


@requires_posix_fd
def test_revalidate_source_rows_enforces_leaf_recheck_deadline(tmp_path, monkeypatch):
    # PR #1253: the post-admission leaf recheck remains inside the deadline.
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_source_snapshot as source

    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    rows = (("app.py", source._metadata_marker(target.stat()), "python"),)
    ticks = iter((0.0, 2.0))
    monkeypatch.setattr(source, "time", SimpleNamespace(monotonic=lambda: next(ticks)))

    with pytest.raises(TimeoutError):
        source._revalidate_source_rows(str(tmp_path), rows, 1.0)


@requires_posix_fd
def test_revalidate_source_rows_enforces_directory_recheck_deadline(
    tmp_path, monkeypatch
):
    # PR #1253: pinned directory metadata rechecks remain inside the deadline.
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_source_snapshot as source

    package = tmp_path / "pkg"
    package.mkdir()
    target = package / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    rows = (("pkg/app.py", source._metadata_marker(target.stat()), "python"),)
    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(source, "time", SimpleNamespace(monotonic=lambda: next(ticks)))

    with pytest.raises(TimeoutError):
        source._revalidate_source_rows(str(tmp_path), rows, 1.0)


@requires_posix_fd
def test_revalidate_source_rows_fails_closed_on_chain_reopen_deadline(
    tmp_path, monkeypatch
):
    # PR #1253: ancestor-chain reauthentication remains inside the deadline.
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_source_snapshot as source

    package = tmp_path / "pkg"
    package.mkdir()
    target = package / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    rows = (("pkg/app.py", source._metadata_marker(target.stat()), "python"),)
    ticks = iter((0.0, 0.0, 0.0, 2.0))
    time_checks = 0

    def monotonic():
        nonlocal time_checks
        time_checks += 1
        return next(ticks)

    monkeypatch.setattr(source, "time", SimpleNamespace(monotonic=monotonic))

    exact = source._revalidate_source_rows(str(tmp_path), rows, 1.0)

    assert (exact, time_checks) == (False, 4)


@requires_posix_fd
def test_revalidate_source_rows_rejects_changed_reopened_ancestor(
    tmp_path, monkeypatch
):
    # PR #1253: a stale pinned ancestor cannot authenticate its replacement path.
    import tree_sitter_analyzer.index_source_snapshot as source

    package = tmp_path / "pkg"
    package.mkdir()
    target = package / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    rows = (("pkg/app.py", source._metadata_marker(target.stat()), "python"),)
    metadata_checks = 0

    def reject_reopened_ancestor(*_args):
        nonlocal metadata_checks
        metadata_checks += 1
        return metadata_checks != 3

    monkeypatch.setattr(source, "_same_file_metadata", reject_reopened_ancestor)

    exact = source._revalidate_source_rows(str(tmp_path), rows, float("inf"))

    assert (exact, metadata_checks) == (False, 3)


@requires_posix_fd
def test_revalidate_source_rows_rejects_unreadable_reopened_chain(
    tmp_path, monkeypatch
):
    # PR #1253: a chain that becomes unreadable during reauthentication fails closed.
    import tree_sitter_analyzer.index_source_snapshot as source

    package = tmp_path / "pkg"
    package.mkdir()
    target = package / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    rows = (("pkg/app.py", source._metadata_marker(target.stat()), "python"),)
    real_stat = source.os.stat
    stat_calls = 0

    def fail_chain_reopen(*args, **kwargs):
        nonlocal stat_calls
        stat_calls += 1
        if stat_calls == 5:
            raise PermissionError("ancestor unavailable")
        return real_stat(*args, **kwargs)

    monkeypatch.setattr(source.os, "stat", fail_chain_reopen)

    exact = source._revalidate_source_rows(str(tmp_path), rows, float("inf"))

    assert (exact, stat_calls) == (False, 5)


@requires_posix_fd
def test_revalidate_source_rows_is_exact_below_rlimit_with_300_files(tmp_path):
    # PR #1253 zero gate B1: O(depth) epoch fds must authenticate a stable repo.
    import resource

    import tree_sitter_analyzer.index_source_snapshot as source

    rows = []
    for index in range(300):
        target = tmp_path / f"source_{index:03d}.py"
        target.write_text(f"value = {index}\n", encoding="utf-8")
        rows.append((target.name, source._metadata_marker(target.stat()), "python"))

    original_limits = resource.getrlimit(resource.RLIMIT_NOFILE)
    lowered_soft = min(256, original_limits[0])
    resource.setrlimit(resource.RLIMIT_NOFILE, (lowered_soft, original_limits[1]))
    try:
        exact = source._revalidate_source_rows(str(tmp_path), tuple(rows), float("inf"))
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, original_limits)

    assert exact is True
