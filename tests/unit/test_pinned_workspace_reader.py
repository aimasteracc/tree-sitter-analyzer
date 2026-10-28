"""#1783: scan-scoped Windows batch reader (fake Kernel32 ABI, runs on every OS)."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from types import SimpleNamespace

import pytest

from tests.unit.test_index_snapshot_windows import _Kernel
from tree_sitter_analyzer import index_snapshot_windows as owner


@pytest.fixture
def kernel(monkeypatch):
    """Same fake Kernel32 as test_index_snapshot_windows, for the reader only."""
    fake = _Kernel()
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_k: fake, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: fake.error, raising=False)
    monkeypatch.setattr(
        ctypes, "WinError", lambda code: OSError(code, "native failure"), raising=False
    )
    monkeypatch.setattr(os, "O_BINARY", getattr(os, "O_BINARY", 0), raising=False)
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(open_osfhandle=lambda handle, _flags: handle),
    )
    return fake


def _populate(tmp_path, count):
    package = tmp_path / "pkg"
    package.mkdir()
    for number in range(count):
        (package / f"m{number}.py").write_bytes(f"value = {number}\n".encode())
    return [f"pkg/m{number}.py" for number in range(count)]


def test_batch_reader_opens_each_directory_once_per_scan(tmp_path, kernel):
    # #1783 root cause: the per-file reader reopened and re-verified the whole
    # ancestor chain for every file (2*(depth+2) CreateFileW each).  On Windows
    # with on-access scanning that made a 553-file scan exceed the 5 s budget.
    paths = _populate(tmp_path, 10)

    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        data = [reader.read(path, limit=1024)[0] for path in paths]
        reads = list(kernel.requests)
        reader.verify()

    assert data == [f"value = {number}\n".encode() for number in range(10)]
    directory_opens = [request for request in reads if request[1] == 0x80]
    file_opens = [request for request in reads if request[1] == 0x80000000]
    # root + pkg pinned once for the whole scan; each file opened + reopened once.
    assert len(directory_opens) == 2
    assert len(file_opens) == 2 * len(paths)
    # The per-file reader needs 3x as many opens for the same work.
    kernel.requests.clear()
    for path in paths:
        owner.read_pinned_workspace_file(
            str(tmp_path), path, deadline=time.monotonic() + 5, limit=1024
        )
    assert len(kernel.requests) == 6 * len(paths)


def test_batch_reader_releases_every_directory_handle(tmp_path, kernel):
    paths = _populate(tmp_path, 3)

    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        reader.read(paths[0], limit=1024)

    assert all(directory is False for _p, directory, _i in kernel.handles.values())
    with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
        reader.read(paths[1], limit=1024)


def test_batch_reader_rejects_file_change_during_read(tmp_path, kernel, monkeypatch):
    (source,) = _populate(tmp_path, 1)
    real_read = owner._read_descriptor

    def read_then_change(fd, size):
        data = real_read(fd, size)
        if data:
            (tmp_path / source).write_bytes(b"after-content-is-longer\n")
        return data

    monkeypatch.setattr(owner, "_read_descriptor", read_then_change)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
            reader.read(source, limit=1024)


def test_batch_reader_verify_rejects_replaced_directory(tmp_path, kernel):
    # Directory identities are proven once at the end of the scan; a swapped
    # directory must still fail the whole scan closed.
    paths = _populate(tmp_path, 2)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        reader.read(paths[0], limit=1024)
        (tmp_path / "pkg").rename(tmp_path / "old-pkg")
        (tmp_path / "pkg").mkdir()
        with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
            reader.verify()


def test_batch_reader_enforces_deadline_budget_and_paths(tmp_path, kernel):
    (source,) = _populate(tmp_path, 1)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        with pytest.raises(OverflowError, match="INDEX_SOURCE_CAPACITY"):
            reader.read(source, limit=1)
        with pytest.raises(ValueError, match="^INDEX_PATH_UNSAFE$"):
            reader.read("../escape.py", limit=1024)
        with pytest.raises(FileNotFoundError):
            reader.read("pkg/missing.py", limit=1024)
    with pytest.raises(TimeoutError, match="INDEX_SNAPSHOT_DEADLINE"):
        owner.PinnedWorkspaceReader(str(tmp_path), deadline=0.0)


def test_batch_reader_is_safe_under_concurrent_reads(tmp_path, kernel):
    from concurrent.futures import ThreadPoolExecutor

    paths = _populate(tmp_path, 24)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        with ThreadPoolExecutor(max_workers=8) as pool:
            data = list(pool.map(lambda path: reader.read(path, limit=1024)[0], paths))
        reader.verify()

    assert data == [f"value = {number}\n".encode() for number in range(24)]
    assert len([r for r in kernel.requests if r[1] == 0x80]) == 2 + 2  # pin + verify


@pytest.fixture
def windows_oracle(kernel, monkeypatch):
    from tree_sitter_analyzer import source_oracle

    monkeypatch.setattr(source_oracle, "_supports_nofollow", lambda: False)
    monkeypatch.setattr(
        source_oracle, "os", SimpleNamespace(**{**vars(os), "name": "nt"})
    )
    return source_oracle


def test_source_batch_reader_maps_windows_reader_outcomes(tmp_path, windows_oracle):
    (source,) = _populate(tmp_path, 1)
    oracle = windows_oracle

    with oracle.SourceBatchReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        captured = reader.read(source, limit=1024)
        missing = reader.read("pkg/absent.py", limit=1024)
        with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
            reader.read(source, limit=1)
        reader.verify()

    assert (captured.kind, captured.data) == ("file", b"value = 0\n")
    assert len(captured.metadata) == 3
    assert missing.kind == "missing"


def test_source_batch_reader_verify_maps_directory_drift(tmp_path, windows_oracle):
    (source,) = _populate(tmp_path, 1)
    oracle = windows_oracle
    with oracle.SourceBatchReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        reader.read(source, limit=1024)
        (tmp_path / "pkg").rename(tmp_path / "moved")
        (tmp_path / "pkg").mkdir()
        with pytest.raises(
            oracle.SourceOracleError, match="^DIFF_SNAPSHOT_SOURCE_CHANGED$"
        ):
            reader.verify()


def test_source_batch_reader_maps_construction_failures(
    tmp_path, windows_oracle, kernel
):
    oracle = windows_oracle
    with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_TIMEOUT$"):
        oracle.SourceBatchReader(str(tmp_path), deadline=0.0)
    kernel.fail = "open"
    with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_PATH$"):
        oracle.SourceBatchReader(str(tmp_path), deadline=time.monotonic() + 5)


def test_source_batch_reader_close_failure_surfaces_only_on_success(
    tmp_path, windows_oracle, kernel
):
    oracle = windows_oracle
    reader = oracle.SourceBatchReader(str(tmp_path), deadline=time.monotonic() + 5)
    kernel.fail = "close"
    with pytest.raises(oracle.SourceOracleError, match="^DIFF_SNAPSHOT_UNSAFE_PATH$"):
        with reader:
            pass
    kernel.fail = None
    reader = oracle.SourceBatchReader(str(tmp_path), deadline=time.monotonic() + 5)
    kernel.fail = "close"
    with pytest.raises(KeyError, match="original"):
        with reader:
            raise KeyError("original")


def test_source_batch_reader_rejects_unsupported_platforms(tmp_path, monkeypatch):
    from tree_sitter_analyzer import source_oracle

    monkeypatch.setattr(source_oracle, "_supports_nofollow", lambda: False)
    monkeypatch.setattr(
        source_oracle, "os", SimpleNamespace(**{**vars(os), "name": "java"})
    )
    with pytest.raises(
        source_oracle.SourceOracleError, match="^DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED$"
    ):
        source_oracle.SourceBatchReader(str(tmp_path), deadline=time.monotonic() + 5)


def test_batch_reader_releases_handle_when_identity_fails(tmp_path, kernel):
    paths = _populate(tmp_path, 1)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        kernel.fail = "identifier"
        with pytest.raises(OSError):
            reader.read(paths[0], limit=1024)
        kernel.fail = None
    assert all(directory is False for _p, directory, _i in kernel.handles.values())
    kernel.fail = "identifier"
    with pytest.raises(OSError):
        owner.PinnedWorkspaceReader(str(tmp_path), deadline=time.monotonic() + 5)
    assert all(directory is False for _p, directory, _i in kernel.handles.values())


def test_batch_reader_close_reports_failure_after_releasing_all(tmp_path, kernel):
    paths = _populate(tmp_path, 1)
    reader = owner.PinnedWorkspaceReader(str(tmp_path), deadline=time.monotonic() + 5)
    reader.read(paths[0], limit=1024)
    kernel.fail = "close"
    with pytest.raises(OSError):
        reader.close()
    assert all(directory is False for _p, directory, _i in kernel.handles.values())


def test_batch_reader_verify_maps_reopen_failure(tmp_path, kernel):
    paths = _populate(tmp_path, 1)
    with owner.PinnedWorkspaceReader(
        str(tmp_path), deadline=time.monotonic() + 5
    ) as reader:
        reader.read(paths[0], limit=1024)
        kernel.fail = "open"
        with pytest.raises(ValueError, match="^INDEX_SOURCE_CHANGED$"):
            reader.verify()
        kernel.fail = None
