"""Behavioral tests for fail-closed source identity and workspace reads."""

from __future__ import annotations

import io
import os
import stat
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.source_oracle as oracle


def _error(call, code: str) -> None:
    with pytest.raises(oracle.SourceOracleError, match=f"^{code}$"):
        call()


@pytest.mark.parametrize("value", ["", "/absolute", "../escape", "a/../b", "bad\0name"])
def test_normalize_repo_path_rejects_unsafe_paths(value: str) -> None:
    _error(lambda: oracle.normalize_repo_path(value), "DIFF_SNAPSHOT_INVALID_PATH")


def test_remaining_rejects_expired_deadline(monkeypatch) -> None:
    monkeypatch.setattr(oracle.time, "monotonic", lambda: 10.0)
    _error(lambda: oracle._remaining(10.0), "DIFF_SNAPSHOT_TIMEOUT")


def test_canonical_root_translates_stat_error(monkeypatch) -> None:
    monkeypatch.setattr(
        oracle.os, "stat", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(lambda: oracle.canonical_root("missing"), "DIFF_SNAPSHOT_ROOT_INVALID")


def test_canonical_root_rejects_non_directory(tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.touch()
    _error(lambda: oracle.canonical_root(str(target)), "DIFF_SNAPSHOT_ROOT_INVALID")


class _Proc:
    def __init__(self, out=b"", err=b"", returncode=0, wait_error=None):
        self.stdout = io.BytesIO(out)
        self.stderr = io.BytesIO(err)
        self.returncode = returncode
        self.wait_error = wait_error
        self.killed = False

    def wait(self, timeout=None):
        if self.wait_error and timeout is not None:
            raise self.wait_error
        return self.returncode

    def kill(self):
        self.killed = True


def test_git_output_translates_spawn_error(monkeypatch) -> None:
    monkeypatch.setattr(
        oracle.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_git_output_rejects_negative_limit() -> None:
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=-1),
        "DIFF_SNAPSHOT_CAPACITY",
    )


def test_git_output_kills_timed_out_process(monkeypatch) -> None:
    proc = _Proc(wait_error=subprocess.TimeoutExpired("git", 1))
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_TIMEOUT",
    )
    assert proc.killed is True


def test_git_output_rejects_nonzero_exit(monkeypatch) -> None:
    proc = _Proc(returncode=3)
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_git_output_rejects_oversize_stdout(monkeypatch) -> None:
    proc = _Proc(out=b"ab")
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_CAPACITY",
    )
    assert proc.killed is True


def test_git_output_translates_stream_read_error(monkeypatch) -> None:
    class Broken(io.BytesIO):
        def read(self, size=-1):
            raise OSError

    proc = _Proc()
    proc.stdout = Broken()
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_safe_workspace_path_reports_missing_leaf(tmp_path: Path) -> None:
    result = oracle.safe_workspace_path(
        str(tmp_path), "missing.py", deadline=time.monotonic() + 1, limit=10
    )
    assert result.kind == "missing"
    assert result.data is None


def test_safe_workspace_path_rejects_unsupported_platform(monkeypatch) -> None:
    monkeypatch.delattr(oracle.os, "O_NOFOLLOW", raising=False)
    _error(
        lambda: oracle.safe_workspace_path(
            ".", "a", deadline=time.monotonic() + 1, limit=1
        ),
        "DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED",
    )


def test_safe_workspace_path_rejects_oversize_symlink(tmp_path: Path) -> None:
    (tmp_path / "link").symlink_to("long-target")
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "link", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )


def test_safe_workspace_path_rejects_special_file(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "fifo")
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "fifo", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_SPECIAL_FILE",
    )


def test_safe_workspace_path_translates_open_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        oracle.os, "open", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


def test_safe_workspace_path_translates_read_error(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "x"
    target.write_bytes(b"x")
    monkeypatch.setattr(
        oracle.os, "read", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_UNSAFE_PATH",
    )


def test_safe_workspace_path_ignores_close_error(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "x").write_bytes(b"x")
    monkeypatch.setattr(oracle.os, "close", lambda fd: (_ for _ in ()).throw(OSError()))
    result = oracle.safe_workspace_path(
        str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
    )
    assert result.data == b"x"


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


def test_oracle_generation_translates_index_lstat_error(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        oracle,
        "canonical_root",
        lambda root: (str(tmp_path), oracle.RootIdentity(str(tmp_path), 1, 2)),
    )
    monkeypatch.setattr(
        oracle,
        "git_output",
        lambda root, args, **k: b".git\n" if "--git-dir" in args else b"head",
    )
    monkeypatch.setattr(
        oracle.os, "stat", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")


def test_oracle_generation_rejects_nonregular_index(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        oracle,
        "canonical_root",
        lambda root: (str(tmp_path), oracle.RootIdentity(str(tmp_path), 1, 2)),
    )
    monkeypatch.setattr(
        oracle,
        "git_output",
        lambda root, args, **k: b".git\n" if "--git-dir" in args else b"head",
    )
    monkeypatch.setattr(
        oracle.os, "stat", lambda *a, **k: SimpleNamespace(st_mode=stat.S_IFDIR)
    )
    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_GIT_ERROR")


def test_capture_consistent_reports_generation_change(monkeypatch) -> None:
    values = iter([("before", None), ("after", None)])
    monkeypatch.setattr(oracle, "oracle_generation", lambda root: next(values))
    generation, value = oracle.capture_consistent(".", lambda: 7)
    assert generation is None
    assert value == 7


def test_source_generation_returns_oracle_value(monkeypatch) -> None:
    monkeypatch.setattr(
        oracle, "oracle_generation", lambda root, mode: ("sg_test", None)
    )
    assert oracle.source_generation(".", "staged") == "sg_test"


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


@pytest.mark.parametrize("changed_call", [3, 4])
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


def test_normalize_repo_path_strips_each_dot_prefix() -> None:
    assert oracle.normalize_repo_path("././file.py") == "file.py"


def test_git_output_rejects_missing_stdout(monkeypatch) -> None:
    proc = _Proc()
    proc.stdout = None
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_GIT_ERROR",
    )


def test_git_output_preserves_capacity_error_when_kill_fails(monkeypatch) -> None:
    proc = _Proc(out=b"ab")
    proc.kill = lambda: (_ for _ in ()).throw(OSError())
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_CAPACITY",
    )


def test_git_output_rejects_drain_thread_past_deadline(monkeypatch) -> None:
    proc = _Proc()

    class Thread:
        def __init__(self, **kwargs):
            self.target = kwargs["target"]

        def start(self):
            pass

        def join(self, timeout=None):
            pass

        def is_alive(self):
            return True

    monkeypatch.setattr(oracle.threading, "Thread", Thread)
    monkeypatch.setattr(oracle.subprocess, "Popen", lambda *a, **k: proc)
    _error(
        lambda: oracle.git_output(".", [], deadline=time.monotonic() + 1, limit=1),
        "DIFF_SNAPSHOT_TIMEOUT",
    )
    assert proc.killed is True


def test_safe_workspace_path_returns_symlink_text(tmp_path: Path) -> None:
    (tmp_path / "x").symlink_to("target")
    result = oracle.safe_workspace_path(
        str(tmp_path), "x", deadline=time.monotonic() + 1, limit=20
    )
    assert result == oracle.SafePath(b"target", result.metadata, "symlink")


def test_safe_workspace_path_rejects_oversize_file(tmp_path: Path) -> None:
    (tmp_path / "x").write_bytes(b"abc")
    _error(
        lambda: oracle.safe_workspace_path(
            str(tmp_path), "x", deadline=time.monotonic() + 1, limit=2
        ),
        "DIFF_SNAPSHOT_CAPACITY",
    )


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


def test_oracle_generation_detects_index_change(tmp_path: Path, monkeypatch) -> None:
    index = tmp_path / "index"
    index.write_bytes(b"index")
    identity = oracle.RootIdentity(str(tmp_path), 1, 2)
    monkeypatch.setattr(
        oracle, "canonical_root", lambda root: (str(tmp_path), identity)
    )
    monkeypatch.setattr(
        oracle,
        "git_output",
        lambda root, args, **k: b".\n" if "--git-dir" in args else b"",
    )
    real = oracle._metadata
    calls = [0]

    def metadata(info):
        calls[0] += 1
        return real(info) + (b"changed" if calls[0] == 2 else b"")

    monkeypatch.setattr(oracle, "_metadata", metadata)
    _error(
        lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_SOURCE_CHANGED"
    )


def test_oracle_generation_rejects_oversize_index(tmp_path: Path, monkeypatch) -> None:
    index = tmp_path / "index"
    index.write_bytes(b"index")
    identity = oracle.RootIdentity(str(tmp_path), 1, 2)
    monkeypatch.setattr(
        oracle, "canonical_root", lambda root: (str(tmp_path), identity)
    )
    monkeypatch.setattr(
        oracle,
        "git_output",
        lambda root, args, **k: b".\n" if "--git-dir" in args else b"",
    )

    class Huge:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return b"x" * (64 * 1024 * 1024 + 1)

    monkeypatch.setattr("builtins.open", lambda *a, **k: Huge())
    _error(lambda: oracle.oracle_generation(str(tmp_path)), "DIFF_SNAPSHOT_CAPACITY")


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
