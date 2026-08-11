"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import hashlib
import os

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
pytestmark = requires_posix_fd


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


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

    def test_stream_opened_nonregular_is_unsafe(self, tmp_path):
        # PR #1253: a file replaced by a directory after admission is rejected.
        from tree_sitter_analyzer.index_source_stream import hash_source_at

        admitted = tmp_path / "admitted.py"
        admitted.write_text("x = 1")
        before = admitted.stat()
        admitted.unlink()
        admitted.mkdir()
        result = hash_source_at(
            None,
            str(admitted),
            before,
            float("inf"),
            {"input": 0, "output": 0},
            100,
            lambda info: str(info.st_mode),
            lambda *_args: True,
        )
        assert result == (str(admitted.stat().st_mode), "<unsafe>", False)

    def test_stream_pending_cr_before_non_lf_normalizes_once(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: a cross-chunk bare CR does not consume the following byte.
        import tree_sitter_analyzer.index_source_snapshot as source

        target = tmp_path / "sample.py"
        target.write_bytes(b"\rX")
        chunks = iter((b"\r", b"X", b""))
        monkeypatch.setattr(source.os, "read", lambda _fd, _size: next(chunks))
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        expected = hashlib.sha256(b"\nX").hexdigest()
        assert (next(iter(rows))[1].split("|")[1], unsafe) == (expected, False)

    def test_stream_output_deadline_and_budget_are_enforced(self):
        # PR #1253: normalized output owns both a deadline and byte budget.
        from tree_sitter_analyzer.index_source_stream import _hash_output

        with pytest.raises(TimeoutError):
            _hash_output(hashlib.sha256(), b"x", 0.0, {"output": 0}, 1)
        with pytest.raises(OverflowError):
            _hash_output(hashlib.sha256(), b"xx", float("inf"), {"output": 0}, 1)

    def test_portable_scope_escape_is_rejected(self, tmp_path, monkeypatch):
        # PR #1253: portable source certification is unsupported and never traverses.
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source.os, "name", "nt")
        monkeypatch.setattr(
            source.os, "scandir", lambda *_args: pytest.fail("traversed")
        )
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows, unsafe) == (frozenset(), True)

    def test_portable_enumeration_deadline_and_budget_are_enforced(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: portable source certification is unsupported and never traverses.
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source.os, "name", "nt")
        monkeypatch.setattr(
            source.os, "scandir", lambda *_args: pytest.fail("traversed")
        )
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows, unsafe) == (frozenset(), True)

    def test_portable_supported_path_budget_is_enforced(self, tmp_path, monkeypatch):
        # PR #1253: portable source certification is unsupported and never traverses.
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source.os, "name", "nt")
        monkeypatch.setattr(
            source.os, "scandir", lambda *_args: pytest.fail("traversed")
        )
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows, unsafe) == (frozenset(), True)

    def test_portable_excluded_nonregular_and_metadata_only_policies(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: portable source certification is unsupported and never traverses.
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source.os, "name", "nt")
        monkeypatch.setattr(
            source.os, "scandir", lambda *_args: pytest.fail("traversed")
        )
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows, unsafe) == (frozenset(), True)

    @requires_posix_fd
    def test_nonregular_shm_sidecar_is_rejected(self, tmp_path):
        # PR #1253: SHM tolerance applies only to ordinary files.
        import tree_sitter_analyzer.index_snapshot as owner

        cache = tmp_path / ".ast-cache"
        cache.mkdir()
        (cache / "index.db-shm").mkdir()
        fd = os.open(cache, os.O_RDONLY)
        try:
            with pytest.raises(ValueError, match="CONCURRENT_WRITER"):
                owner._reject_sidecars(fd)
        finally:
            os.close(fd)

    def test_stream_invalid_utf8_remains_unsafe_across_later_chunks(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: strict validation remains failed after the offending chunk.
        import tree_sitter_analyzer.index_source_snapshot as source

        target = tmp_path / "sample.py"
        target.write_bytes(b"\xffX")
        chunks = iter((b"\xff", b"X", b""))
        monkeypatch.setattr(source.os, "read", lambda _fd, _size: next(chunks))
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (next(iter(rows))[1].endswith("|<unsafe>"), unsafe) == (True, True)

    def test_stream_incomplete_final_utf8_sequence_is_unsafe(self, tmp_path):
        # PR #1253: final incremental decoder state is validated strictly.
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_bytes(b"\xe2\x82")
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (next(iter(rows))[1].endswith("|<unsafe>"), unsafe) == (True, True)

    def test_portable_enumeration_deadline_is_enforced(self, tmp_path, monkeypatch):
        # PR #1253: portable source certification is unsupported and never traverses.
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source.os, "name", "nt")
        monkeypatch.setattr(
            source.os, "scandir", lambda *_args: pytest.fail("traversed")
        )
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows, unsafe) == (frozenset(), True)

    @requires_posix_fd
    def test_child_directory_open_race_marks_inventory_unsafe(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: a child replaced before openat cannot be followed by path.
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "pkg").mkdir()
        original_open = source.os.open

        def fail_child(name, flags, *args, **kwargs):
            if name == "pkg":
                raise FileNotFoundError
            return original_open(name, flags, *args, **kwargs)

        monkeypatch.setattr(source.os, "open", fail_child)
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows, unsafe) == (frozenset(), True)

    @requires_posix_fd
    def test_child_directory_type_race_marks_inventory_unsafe(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: opened child descriptors are revalidated as directories.
        import tree_sitter_analyzer.index_source_snapshot as source

        package = tmp_path / "pkg"
        package.mkdir()
        sample = tmp_path / "notes.txt"
        sample.write_text("not source")
        original_open = source.os.open
        original_fstat = source.os.fstat
        child_fds = set()

        def record_child(name, flags, *args, **kwargs):
            fd = original_open(name, flags, *args, **kwargs)
            if name == "pkg":
                child_fds.add(fd)
            return fd

        monkeypatch.setattr(source.os, "open", record_child)
        monkeypatch.setattr(
            source.os,
            "fstat",
            lambda fd: sample.stat() if fd in child_fds else original_fstat(fd),
        )
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert (rows, unsafe) == (frozenset(), True)

    @requires_posix_fd
    def test_child_directory_revalidation_error_closes_descriptor(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: failed child fstat propagates only after descriptor cleanup.
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "pkg").mkdir()
        original_open = source.os.open
        original_fstat = source.os.fstat
        child_fds = set()

        def record_child(name, flags, *args, **kwargs):
            fd = original_open(name, flags, *args, **kwargs)
            if name == "pkg":
                child_fds.add(fd)
            return fd

        monkeypatch.setattr(source.os, "open", record_child)

        def fail_child(fd):
            if fd in child_fds:
                raise OSError("child changed")
            return original_fstat(fd)

        monkeypatch.setattr(source.os, "fstat", fail_child)
        with pytest.raises(OSError, match="child changed"):
            source._inventory(str(tmp_path), float("inf"), with_content=True)
        assert all(_fd_is_closed(fd) for fd in child_fds)

    @requires_posix_fd
    def test_failed_second_scope_root_closes_first_pinned_root(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: partially opened scope-root sets are cleaned on openat failure.
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "pkg").mkdir()
        original_open = source.os.open
        scope_fds = set()

        def record_scope(name, flags, *args, **kwargs):
            fd = original_open(name, flags, *args, **kwargs)
            if name == "pkg":
                scope_fds.add(fd)
            return fd

        monkeypatch.setattr(source.os, "open", record_scope)
        original_close = source.os.close

        def close_then_report(fd):
            original_close(fd)
            if fd in scope_fds:
                raise OSError("close reported failure")

        monkeypatch.setattr(source.os, "close", close_then_report)
        scope = source.make_source_scope_descriptor(roots=("pkg", "missing"))
        with pytest.raises(FileNotFoundError):
            source._inventory(str(tmp_path), float("inf"), scope, with_content=True)
        assert all(_fd_is_closed(fd) for fd in scope_fds)

    @requires_posix_fd
    def test_stack_cleanup_tolerates_close_error(self, tmp_path, monkeypatch):
        # PR #1253: cleanup still closes the root after a child close reports failure.
        import tree_sitter_analyzer.index_source_snapshot as source

        original_dup = source.os.dup
        original_close = source.os.close
        duplicated = set()

        def record_dup(fd):
            result = original_dup(fd)
            duplicated.add(result)
            return result

        def fail_duplicate_close(fd):
            if fd in duplicated:
                raise OSError("close failed")
            return original_close(fd)

        monkeypatch.setattr(source.os, "dup", record_dup)
        monkeypatch.setattr(source.os, "close", fail_duplicate_close)
        with pytest.raises(OSError, match="close failed"):
            source._inventory(str(tmp_path), float("inf"), with_content=True)
        for fd in duplicated:
            original_close(fd)

    @requires_posix_fd
    def test_directory_enumerator_checks_deadline_per_entry(
        self, tmp_path, monkeypatch
    ):
        # PR #1253: scandir cannot consume entries after the source deadline.
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "notes.txt").write_text("ignored")
        fd = os.open(tmp_path, os.O_RDONLY)
        monkeypatch.setattr(source, "time", SimpleNamespace(monotonic=lambda: 2.0))
        try:
            with pytest.raises(TimeoutError):
                tuple(
                    source._enumerate_directory(
                        fd,
                        "",
                        1.0,
                        {"entries": 0, "path_bytes": 0},
                    )
                )
        finally:
            os.close(fd)

    def test_stream_read_checks_deadline_after_each_chunk(self, tmp_path):
        # PR #1253: admitted input cannot be read beyond the source deadline.
        from tree_sitter_analyzer.index_source_stream import hash_source_at

        target = tmp_path / "sample.py"
        target.write_text("x = 1")
        with pytest.raises(TimeoutError):
            hash_source_at(
                None,
                str(target),
                target.stat(),
                0.0,
                {"input": 0, "output": 0},
                100,
                lambda info: str(info.st_mode),
                lambda *_args: True,
            )

    def test_portable_source_capture_reports_unsupported_without_traversal(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source.os, "name", "nt")
        monkeypatch.setattr(
            source.os, "scandir", lambda *_args: pytest.fail("traversed")
        )
        current = source.capture_current_source_snapshot(str(tmp_path))

        assert (current.state, current.reason, current.rows) == (
            "unsafe",
            "SOURCE_SCOPE_UNSUPPORTED",
            frozenset(),
        )
