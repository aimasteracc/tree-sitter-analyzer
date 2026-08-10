"""Integration tests for source identity across filesystems and Git repositories."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
import tree_sitter_analyzer.source_oracle as oracle
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST, make_repo


def _error(call, code: str) -> None:
    with pytest.raises(oracle.SourceOracleError, match=f"^{code}$"):
        call()


def test_canonical_root_rejects_non_directory(tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.touch()
    _error(lambda: oracle.canonical_root(str(target)), "DIFF_SNAPSHOT_ROOT_INVALID")


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_reports_missing_leaf(tmp_path: Path) -> None:
    result = oracle.safe_workspace_path(
        str(tmp_path), "missing.py", deadline=time.monotonic() + 1, limit=10
    )
    assert result.kind == "missing"
    assert result.data is None


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_rejects_oversize_symlink(tmp_path: Path) -> None:
    (tmp_path / "link").symlink_to("long-target")
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "link", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_rejects_special_file(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "fifo")
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "fifo", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_SPECIAL_FILE",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_ignores_close_error(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "x").write_bytes(b"x")
    monkeypatch.setattr(oracle, "_close", lambda fd: (_ for _ in ()).throw(OSError()))
    result = oracle.safe_workspace_path(
        str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
    )
    assert result.data == b"x"


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_detects_post_open_identity_change(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "x").write_bytes(b"x")
    real = oracle._metadata
    calls = [0]

    def metadata(info):
        calls[0] += 1
        return real(info) + (b"changed" if calls[0] == 3 else b"")

    monkeypatch.setattr(oracle, "_metadata", metadata)
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


@pytest.mark.parametrize("changed_call", [3, 4])
@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_detects_file_identity_changes(
    tmp_path: Path, monkeypatch, changed_call: int
) -> None:
    (tmp_path / "x").write_bytes(b"x")
    real = oracle._metadata
    calls = [0]

    def metadata(info):
        calls[0] += 1
        return real(info) + (b"changed" if calls[0] == changed_call else b"")

    monkeypatch.setattr(oracle, "_metadata", metadata)
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_detects_symlink_identity_change(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "x").symlink_to("target")
    real = oracle._metadata
    calls = [0]

    def metadata(info):
        calls[0] += 1
        return real(info) + (b"changed" if calls[0] == 3 else b"")

    monkeypatch.setattr(oracle, "_metadata", metadata)
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=20
        ),
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_returns_symlink_text(tmp_path: Path) -> None:
    (tmp_path / "x").symlink_to("target")
    result = oracle.safe_workspace_path(
        str(tmp_path), "x", deadline=time.monotonic() + 1, limit=20
    )
    assert result == oracle.SafePath(b"target", result.metadata, "symlink")


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_rejects_oversize_file(tmp_path: Path) -> None:
    (tmp_path / "x").write_bytes(b"abc")
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )


@POSIX_SNAPSHOT_TEST
def test_safe_workspace_path_detects_post_read_identity_change(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "x").write_bytes(b"x")
    real = oracle._metadata
    calls = [0]

    def metadata(info):
        calls[0] += 1
        return real(info) + (b"changed" if calls[0] == 5 else b"")

    monkeypatch.setattr(oracle, "_metadata", metadata)
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


class _RecordingDigest:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def update(self, value: bytes) -> None:
        self.frames.append(value)


@POSIX_SNAPSHOT_TEST
def test_frame_workspace_path_records_clean_tracked_disappearance(
    tmp_path: Path,
) -> None:
    digest = _RecordingDigest()

    charge = oracle._frame_workspace_path(
        digest,
        str(tmp_path),
        b"tracked.py",
        deadline=time.monotonic() + 1,
        content_budget=10,
        content_required=False,
        index_entry=b"100644 blob-id 0",
        head_entry=b"100644 blob blob-id",
    )

    assert charge == 0
    assert digest.frames[-6:-4] == [
        b"\x00\x00\x00\rworktree-kind",
        b"\x00\x00\x00\x00\x00\x00\x00\x07missing",
    ]


@POSIX_SNAPSHOT_TEST
def test_safe_absolute_regular_detects_index_change(
    tmp_path: Path, monkeypatch
) -> None:
    index = tmp_path / "index"
    index.write_bytes(b"index")
    real_read = oracle._read
    changed = False

    def mutate_after_read(fd: int, size: int) -> bytes:
        nonlocal changed
        data = real_read(fd, size)
        if data and not changed:
            changed = True
            index.write_bytes(b"other")
        return data

    monkeypatch.setattr(oracle, "_read", mutate_after_read)
    _error(
        lambda: oracle._safe_absolute_regular(
            str(index), deadline=time.monotonic() + 1, limit=64
        ),
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_hashes_workspace_and_nested_path(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "tracked").write_text("old")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True
    )
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "new.py").write_text("value = 1\n")
    generation, identity = oracle.oracle_generation(str(tmp_path))
    assert generation.startswith("sg_")
    assert identity.realpath == str(tmp_path)


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_supports_staged_mode(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "tracked").write_text("old")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True
    )
    (tmp_path / "tracked").write_text("new")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    generation, _ = oracle.oracle_generation(str(tmp_path), "staged")
    assert generation.startswith("sg_")


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_binds_clean_tracked_write_restore(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    target = tmp_path / "clean.py"
    target.write_bytes(b"SAFE\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    before, _ = oracle.oracle_generation(str(tmp_path))

    target.write_bytes(b"TRANSIENT\n")
    target.write_bytes(b"SAFE\n")
    after, _ = oracle.oracle_generation(str(tmp_path))

    assert after != before


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_binds_clean_tracked_atomic_replace(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    target = tmp_path / "clean.py"
    target.write_bytes(b"SAFE\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    before, _ = oracle.oracle_generation(str(tmp_path))

    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"SAFE\n")
    os.replace(replacement, target)
    after, _ = oracle.oracle_generation(str(tmp_path))

    assert after != before


def test_oracle_generation_fails_closed_without_nofollow_workspace_reads(
    tmp_path: Path, monkeypatch
) -> None:
    import tree_sitter_analyzer.source_oracle_git as oracle_git

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.setattr(oracle_git, "_supports_nofollow", lambda: False)

    _error(
        lambda: oracle.oracle_generation(str(tmp_path)),
        "DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED",
    )


@pytest.mark.parametrize(
    ("reader", "expected"),
    [
        ("workspace", "DIFF_SNAPSHOT_SPECIAL_FILE"),
        ("index", "DIFF_SNAPSHOT_GIT_ERROR"),
    ],
)
@POSIX_SNAPSHOT_TEST
def test_regular_leaf_fifo_swap_is_subprocess_bounded(
    tmp_path: Path, reader: str, expected: str
) -> None:
    # Security review 2026-07-01: open must not block before its deadline.
    script = r"""
import os, pathlib, sys, time
import tree_sitter_analyzer.source_oracle as oracle
root = pathlib.Path(sys.argv[1])
target = root / "leaf"
target.write_bytes(b"regular")
real_stat = oracle._stat
swapped = False
def racing_stat(path, *args, **kwargs):
    global swapped
    result = real_stat(path, *args, **kwargs)
    if not swapped and os.fsdecode(path) == "leaf":
        swapped = True
        target.unlink()
        os.mkfifo(target)
    return result
oracle._stat = racing_stat
try:
    if sys.argv[2] == "workspace":
        oracle.safe_workspace_path(str(root), "leaf", deadline=time.monotonic() + .2, limit=64)
    else:
        oracle._safe_absolute_regular(str(target), deadline=time.monotonic() + .2, limit=64)
except oracle.SourceOracleError as exc:
    print(exc)
"""
    completed = subprocess.run(
        [os.sys.executable, "-c", script, str(tmp_path), reader],
        check=True,
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert completed.stdout.strip() == expected


@pytest.mark.parametrize(
    ("reader", "expected"),
    [
        ("workspace", "DIFF_SNAPSHOT_SPECIAL_FILE"),
        ("index", "DIFF_SNAPSHOT_GIT_ERROR"),
    ],
)
@POSIX_SNAPSHOT_TEST
def test_regular_leaf_fifo_swap_fails_closed_in_process(
    tmp_path: Path, monkeypatch, reader: str, expected: str
) -> None:
    target = tmp_path / "leaf"
    target.write_bytes(b"regular")
    real_stat = oracle._stat
    swapped = False

    def racing_stat(path, *args, **kwargs):
        nonlocal swapped
        result = real_stat(path, *args, **kwargs)
        if not swapped and os.fsdecode(path) == "leaf":
            swapped = True
            target.unlink()
            os.mkfifo(target)
        return result

    monkeypatch.setattr(oracle, "_stat", racing_stat)

    def read_raced_leaf():
        if reader == "workspace":
            return oracle.safe_workspace_path(
                str(tmp_path), "leaf", deadline=time.monotonic() + 0.2, limit=64
            )
        return oracle._safe_absolute_regular(
            str(target), deadline=time.monotonic() + 0.2, limit=64
        )

    _error(read_raced_leaf, expected)


@POSIX_SNAPSHOT_TEST
def test_removed_tracked_directory_frames_nested_paths_as_missing(
    tmp_path: Path,
) -> None:
    # PR #1252 review thread 3748259963.
    root = make_repo(tmp_path)
    nested = root / "gone" / "nested.py"
    nested.parent.mkdir()
    nested.write_text("value = 1\n")
    subprocess.run(
        ["git", "add", "gone/nested.py"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "directory baseline"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    import shutil

    shutil.rmtree(root / "gone")
    registry = snapshots.DiffSnapshotRegistry()

    created = registry.create(str(root), "diff", [])

    assert created["success"] is True
    assert [(item["path"], item["status"]) for item in created["changed_records"]] == [
        ("gone/nested.py", "D")
    ]
