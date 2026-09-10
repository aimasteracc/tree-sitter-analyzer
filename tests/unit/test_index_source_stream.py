"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import hashlib
import os
import time

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

    def test_stream_non_utf8_matches_writer_detection_across_chunks(
        self, tmp_path, monkeypatch
    ):
        # PR #1405：分块边界不能改变与写入端一致的编码检测结果。
        import tree_sitter_analyzer.index_source_snapshot as source

        target = tmp_path / "sample.py"
        target.write_bytes(b"\xe2\x82\xac\xffX")
        original_read = source.os.read
        monkeypatch.setattr(source.os, "read", lambda fd, _size: original_read(fd, 1))
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        expected = hashlib.sha256("â‚¬ÿX".encode()).hexdigest()
        assert (next(iter(rows))[1].split("|")[1], unsafe) == (expected, False)

    def test_stream_incomplete_utf8_uses_writer_encoding_detection(self, tmp_path):
        # PR #1405：不完整 UTF-8 由统一编码检测解释，不能单独使用替换解码。
        import tree_sitter_analyzer.index_source_snapshot as source

        (tmp_path / "sample.py").write_bytes(b"\xe2\x82\r")
        rows, unsafe = source._inventory(str(tmp_path), float("inf"), with_content=True)
        expected = hashlib.sha256("â‚\n".encode()).hexdigest()
        assert (next(iter(rows))[1].split("|")[1], unsafe) == (expected, False)

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


def test_regular_source_replaced_by_fifo_is_unsafe_without_blocking(tmp_path):
    # PR #1253 review 3755216355: replay must reach its type check immediately.
    from tree_sitter_analyzer.index_source_stream import hash_source_at

    source = tmp_path / "sample.py"
    source.write_text("value = 1")
    admitted = source.stat()
    source.unlink()
    os.mkfifo(source)
    started = time.monotonic()
    marker, digest, clean = hash_source_at(
        None,
        str(source),
        admitted,
        float("inf"),
        {"input": 0, "output": 0},
        100,
        lambda info: str(info.st_mode),
        lambda *_args: True,
    )
    assert (digest, clean) == ("<unsafe>", False)
    assert marker == str(source.stat().st_mode)
    assert time.monotonic() - started < 0.2


def test_in_place_rewrite_with_restored_mtime_is_unsafe(tmp_path, monkeypatch):
    # PR #1253 review 3763562831: ctime closes the same-size/restored-mtime race.
    import tree_sitter_analyzer.index_source_snapshot as snapshot
    import tree_sitter_analyzer.index_source_stream as stream

    target = tmp_path / "sample.py"
    target.write_bytes(b"old = 1\n")
    admitted = target.stat()
    real_read = stream.os.read
    rewritten = False

    def rewrite_after_eof(fd, size):
        nonlocal rewritten
        chunk = real_read(fd, size)
        if not chunk and not rewritten:
            rewritten = True
            target.write_bytes(b"new = 2\n")
            os.utime(target, ns=(admitted.st_atime_ns, admitted.st_mtime_ns))
        return chunk

    monkeypatch.setattr(stream.os, "read", rewrite_after_eof)
    marker, digest, clean = stream.hash_source_at(
        None,
        str(target),
        admitted,
        float("inf"),
        {"input": 0, "output": 0},
        100,
        snapshot._metadata_marker,
        snapshot._same_file_metadata,
    )

    assert (rewritten, marker, digest, clean) == (
        True,
        snapshot._metadata_marker(target.stat()),
        "<unsafe>",
        False,
    )


class TestStaleSnapshotRecovery:
    """#1364/#1373：后续路径稳定不能洗白一次读取的一致性检查失败。"""

    @pytest.mark.parametrize(
        "case",
        [
            "windows_ctime",
            "posix_ctime",
            "path_size",
            "path_mtime",
            "path_attributes",
            "path_inode",
            "read_ctime",
            "read_size",
            "read_mtime",
        ],
    )
    def test_descriptor_baseline_preserves_read_and_path_guards(
        self, tmp_path, monkeypatch, case
    ):
        # #1356：真实 Windows 3.13 日志表明 lstat/句柄 ctime 不同，句柄自身前后相等。
        from types import SimpleNamespace

        from tree_sitter_analyzer import index_source_stream as stream
        from tree_sitter_analyzer.portable_source_snapshot import _marker, _same

        target = tmp_path / "sample.py"
        content = b"value = 1\n"
        target.write_bytes(content)
        fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
            "st_file_attributes",
        )
        values = {field: getattr(target.stat(), field, 0) for field in fields}
        before = SimpleNamespace(**values)
        opened = SimpleNamespace(
            **{**values, "st_ctime_ns": values["st_ctime_ns"] + 100}
        )
        after = SimpleNamespace(**vars(opened))
        path_fields = {
            "path_size": "st_size",
            "path_mtime": "st_mtime_ns",
            "path_attributes": "st_file_attributes",
            "path_inode": "st_ino",
        }
        if case in path_fields:
            field = path_fields[case]
            setattr(before, field, getattr(before, field) + 1)
        if case == "read_ctime":
            after.st_ctime_ns = before.st_ctime_ns
        elif case == "read_size":
            after.st_size += 1
        elif case == "read_mtime":
            after.st_mtime_ns += 1
        original_os = stream.os
        observations = iter((opened, after))

        class ObservedOS:
            name = "posix" if case == "posix_ctime" else "nt"

            def __getattr__(self, name):
                return getattr(original_os, name)

            def fstat(self, fd):
                original_os.fstat(fd)
                return next(observations)

        monkeypatch.setattr(stream, "os", ObservedOS())
        _, digest, clean = stream.hash_source_at(
            None,
            str(target),
            before,
            float("inf"),
            {"input": 0, "output": 0},
            100,
            _marker,
            _same,
        )
        assert (digest, clean) == (
            (hashlib.sha256(content).hexdigest(), True)
            if case == "windows_ctime"
            else ("<unsafe>", False)
        )

    def test_读取不一致时不能用后续路径比较恢复clean(self, tmp_path):
        from tree_sitter_analyzer.index_source_stream import hash_source_at
        from tree_sitter_analyzer.portable_source_snapshot import _marker

        target = tmp_path / "fresh.py"
        target.write_text("value = 1\n", encoding="utf-8")
        import os as _os

        before = _os.lstat(target)
        calls = []

        def first_dirty_then_clean(a, b):
            calls.append(1)
            # 只有读取绑定的第一次比较有意义；后续路径比较不能证明摘要有效。
            return len(calls) > 1

        _marker_fn, digest, clean = hash_source_at(
            None,
            str(target),
            before,
            float("inf"),
            {"input": 0, "output": 0},
            10 * 1024 * 1024,
            _marker,
            first_dirty_then_clean,
        )
        assert clean is False
        assert digest == "<unsafe>"
        assert len(calls) == 1

    @requires_posix_fd
    def test_dir_fd读取不能退回当前目录的同名文件(self, tmp_path, monkeypatch):
        # #1364：相对名称绑定目录描述符，不得以工作目录中的同名路径替换证据。
        import tree_sitter_analyzer.index_source_stream as stream

        project = tmp_path / "project"
        project.mkdir()
        target = project / "sample.py"
        target.write_text("value = 1\n", encoding="utf-8")
        (tmp_path / "sample.py").write_text("unrelated = 2\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        before = target.stat()
        fd = os.open(project, os.O_RDONLY)
        try:
            with monkeypatch.context() as context:
                context.setattr(
                    stream.os,
                    "lstat",
                    lambda *_args, **_kwargs: pytest.fail("读取证据不得退回路径重查"),
                )
                _, digest, clean = stream.hash_source_at(
                    fd,
                    "sample.py",
                    before,
                    float("inf"),
                    {"input": 0, "output": 0},
                    100,
                    lambda info: str(info.st_ino),
                    lambda *_args: False,
                )
        finally:
            os.close(fd)
        assert (digest, clean) == ("<unsafe>", False)

    def test_持续不一致_维持unsafe(self, tmp_path):
        from tree_sitter_analyzer.index_source_stream import hash_source_at
        from tree_sitter_analyzer.portable_source_snapshot import _marker

        target = tmp_path / "hot.py"
        target.write_text("a" * 100, encoding="utf-8")
        import os as _os

        before = _os.lstat(target)

        def always_dirty(a, b):
            return False

        _marker_fn, digest, clean = hash_source_at(
            None,
            str(target),
            before,
            float("inf"),
            {"input": 0, "output": 0},
            10 * 1024 * 1024,
            _marker,
            always_dirty,
        )
        assert clean is False
        assert digest == "<unsafe>"


@pytest.mark.parametrize(
    "budget", ["deadline", "total_bytes", "file_bytes", "decode_deadline"]
)
def test_encoding_fallback_preserves_resource_limits(tmp_path, monkeypatch, budget):
    """#1405：非 UTF-8 回退不得绕过期限、累计输入和单文件预算。"""
    import tree_sitter_analyzer.index_source_stream as stream
    import tree_sitter_analyzer.indexing_snapshot as snapshot

    path = tmp_path / "app.py"
    path.write_bytes(b"\xe9\xe9")
    if budget == "file_bytes":
        monkeypatch.setattr(snapshot, "_INDEX_SOURCE_BYTE_LIMIT", 1)
    if budget == "decode_deadline":

        def decode(_data):
            monkeypatch.setattr(stream.time, "monotonic", lambda: 2.0)
            return ""

        monkeypatch.setattr(snapshot, "decode_index_source", decode)
        monkeypatch.setattr(stream.time, "monotonic", lambda: 0.0)
    deadline = (
        -1.0
        if budget == "deadline"
        else (1.0 if budget == "decode_deadline" else float("inf"))
    )
    error = TimeoutError if "deadline" in budget else OverflowError
    fd = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(error):
            stream._hash_detected_source(
                fd,
                deadline,
                {"input": 0, "output": 0},
                1 if budget == "total_bytes" else 100,
            )
    finally:
        os.close(fd)
