from __future__ import annotations

import io
import os
import subprocess
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
import tree_sitter_analyzer.source_oracle_git as oracle
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST, make_repo


def _error(call, code: str) -> None:
    with pytest.raises(oracle.SourceOracleError, match=f"^{code}$"):
        call()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


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


def test_strip_one_record_terminator_preserves_path_newline() -> None:
    assert oracle._strip_one_record_terminator(b"repo\n\r\n") == b"repo\n"


@POSIX_SNAPSHOT_TEST
def test_git_output_timeout_kills_hostile_descendant(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3747224316.
    marker = tmp_path / "survived"
    fake_git = tmp_path / "git"
    fake_git.write_text(
        f"#!/bin/sh\n( trap '' TERM; sleep 0.3; echo survived > {marker!s} ) &\nwait\n"
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])

    _error(
        lambda: oracle.git_output(
            str(tmp_path), [], deadline=time.monotonic() + 0.05, limit=4096
        ),
        "DIFF_SNAPSHOT_TIMEOUT",
    )
    time.sleep(0.4)

    assert marker.exists() is False


@POSIX_SNAPSHOT_TEST
def test_snapshot_disables_external_fsmonitor_hook(tmp_path: Path) -> None:
    # PR #1252 review thread 3747224316.
    root = _repo(tmp_path)
    marker = root / "fsmonitor-invoked"
    hook = root / "hostile-fsmonitor"
    hook.write_text(f"#!/bin/sh\necho invoked > {marker!s}\nsleep 30\n")
    hook.chmod(0o755)
    _git(root, "config", "core.fsmonitor", str(hook))
    (root / "old.py").write_text("value = 2\n")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert result["success"] is True
    assert marker.exists() is False


@POSIX_SNAPSHOT_TEST
def test_oracle_generation_ignores_inherited_git_routing(
    tmp_path: Path, monkeypatch
) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "wrong-tree"))

    generation, _ = oracle.oracle_generation(str(tmp_path))

    assert generation[:3] == "sg_"
