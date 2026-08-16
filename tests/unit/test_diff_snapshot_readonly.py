"""RFC-0022 P0.4 zero-write oracle differential contract.

The read-only oracle (``diff_snapshot_readonly``) must produce the exact
same source-generation token as the frozen oracle
(``source_oracle_git``) on identical source state — otherwise task routes
comparing impact tokens against the index oracle would diverge. These
tests prove byte-equality across clean/dirty/untracked/staged states and
assert the read-only invocation set never materializes a temporary index.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST
from tree_sitter_analyzer.diff_snapshot_readonly import (
    _live_index_output,
    oracle_generation_readonly,
)
from tree_sitter_analyzer.source_oracle_git import GitEpoch, oracle_generation


@pytest.fixture()
def git_repo(tmp_path) -> str:
    root = str(tmp_path)
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"], check=True)
    (tmp_path / "base.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("keep = True\n", encoding="utf-8")
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "init"], check=True)
    return root


def _epochs(root: str, mode: str) -> tuple[GitEpoch, GitEpoch]:
    frozen_epochs: list[GitEpoch] = []
    readonly_epochs: list[GitEpoch] = []
    frozen_gen, _ = oracle_generation(root, mode, epoch_out=frozen_epochs)
    readonly_gen, _ = oracle_generation_readonly(root, mode, epoch_out=readonly_epochs)
    assert frozen_gen == readonly_gen
    return frozen_epochs[0], readonly_epochs[0]


@POSIX_SNAPSHOT_TEST
def test_clean_repo_generations_match(git_repo: str) -> None:
    for mode in ("diff", "staged"):
        frozen_epoch, readonly_epoch = _epochs(git_repo, mode)
        assert frozen_epoch.tracked_paths == readonly_epoch.tracked_paths
        assert frozen_epoch.dirty_paths == readonly_epoch.dirty_paths
        assert frozen_epoch.untracked_paths == readonly_epoch.untracked_paths


@POSIX_SNAPSHOT_TEST
def test_dirty_and_untracked_generations_match(git_repo: str) -> None:
    import pathlib

    root = pathlib.Path(git_repo)
    (root / "base.py").write_text("value = 2\n", encoding="utf-8")
    (root / "new_file.py").write_text("brand = 'new'\n", encoding="utf-8")
    (root / "ignored.log").write_text("noise\n", encoding="utf-8")
    (root / ".gitignore").write_text("*.log\n", encoding="utf-8")

    frozen_epoch, readonly_epoch = _epochs(git_repo, "diff")
    # The frozen oracle's stat-invalidation framing conservatively reports
    # every tracked path dirty; the P0.4 oracle replicates it exactly.
    assert frozen_epoch.dirty_paths == (b"base.py", b"keep.py")
    assert frozen_epoch.untracked_paths == (b".gitignore", b"new_file.py")
    assert readonly_epoch.dirty_paths == frozen_epoch.dirty_paths
    assert readonly_epoch.untracked_paths == frozen_epoch.untracked_paths

    # Staged mode ignores the worktree dirt but includes the staged change.
    subprocess.run(["git", "-C", git_repo, "add", "base.py"], check=True)
    frozen_epoch, readonly_epoch = _epochs(git_repo, "staged")
    assert readonly_epoch.dirty_paths == frozen_epoch.dirty_paths
    assert readonly_epoch.untracked_paths == frozen_epoch.untracked_paths


@POSIX_SNAPSHOT_TEST
def test_generation_changes_when_source_changes(git_repo: str) -> None:
    import pathlib

    before = oracle_generation_readonly(git_repo, "diff")[0]
    pathlib.Path(git_repo, "base.py").write_text("value = 3\n", encoding="utf-8")
    after = oracle_generation_readonly(git_repo, "diff")[0]
    assert before != after
    # Deterministic for the same state.
    assert after == oracle_generation_readonly(git_repo, "diff")[0]


@POSIX_SNAPSHOT_TEST
def test_readonly_never_materializes_temporary_index(git_repo: str) -> None:
    import tempfile

    mkstemp_calls: list[str] = []

    def spy_mkstemp(*args, **kwargs):
        mkstemp_calls.append("mkstemp")
        return tempfile.mkstemp(*args, **kwargs)

    # The read-only oracle must never invoke the temp-index machinery.
    frozen_epochs: list[GitEpoch] = []
    oracle_generation_readonly(git_repo, "diff", epoch_out=frozen_epochs)
    assert mkstemp_calls == []


@POSIX_SNAPSHOT_TEST
def test_live_index_output_is_readonly_invocation(git_repo: str) -> None:
    """GIT_OPTIONAL_LOCKS=0 is set and no GIT_INDEX_FILE is injected."""
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    seen_env: dict[str, str] = {}

    def spy(root, args, *, deadline, limit, env=None, input_=None):
        seen_env.update(dict(env or {}))
        return b""

    original = module._run_git_readonly_bounded
    module._run_git_readonly_bounded = spy
    try:
        import time as _time

        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=_time.monotonic() + 35.0,
            limit=1024,
        )
    finally:
        module._run_git_readonly_bounded = original
    assert seen_env.get("GIT_OPTIONAL_LOCKS") == "0"
    assert "GIT_INDEX_FILE" not in seen_env


def test_workspace_unsupported_fails_closed(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    monkeypatch.setattr(module, "_supports_nofollow", lambda: False)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED"):
        oracle_generation_readonly(git_repo, "diff")


def test_root_mismatch_fails_closed(git_repo: str) -> None:
    import os

    subdir = os.path.join(git_repo, "sub")
    os.mkdir(subdir)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_ROOT_MISMATCH"):
        oracle_generation_readonly(subdir, "diff")


def test_gitlink_generations_match(git_repo: str) -> None:
    import pathlib

    # A local-path submodule produces a 160000 gitlink entry; both oracles
    # frame it identically (dirty marker + index identity).
    sub_repo = pathlib.Path(git_repo, "vendor")
    sub_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(sub_repo)], check=True)
    subprocess.run(
        ["git", "-C", str(sub_repo), "config", "user.email", "t@t"], check=True
    )
    subprocess.run(["git", "-C", str(sub_repo), "config", "user.name", "t"], check=True)
    (sub_repo / "lib.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(sub_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(sub_repo), "commit", "-qm", "sub"], check=True)
    subprocess.run(
        ["git", "-C", git_repo, "submodule", "add", "-q", str(sub_repo), "vendor"],
        check=True,
    )
    frozen_epoch, readonly_epoch = _epochs(git_repo, "diff")
    assert frozen_epoch.workspace_gitlinks == readonly_epoch.workspace_gitlinks
    # git's diff-files name-only never reports gitlink entries (live or
    # stat-invalidated), so neither oracle frames gitlink-dirty evidence;
    # the gitlink is framed as an opaque tracked path instead.
    assert frozen_epoch.workspace_gitlinks == ()
    assert b"vendor" in frozen_epoch.tracked_paths


def test_split_index_fails_closed(git_repo: str) -> None:
    subprocess.run(["git", "-C", git_repo, "update-index", "--split-index"], check=True)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_UNSUPPORTED_INDEX"):
        oracle_generation_readonly(git_repo, "diff")


def test_capacity_fails_closed(git_repo: str) -> None:
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_CAPACITY"):
        oracle_generation_readonly(git_repo, "diff", byte_ceiling=1)


def test_runner_popen_failure_is_stable_error(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    def boom(*args, **kwargs):
        raise OSError("no git here")

    monkeypatch.setattr(module.subprocess, "Popen", boom)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
        )


def test_runner_negative_limit_fails_closed(git_repo: str) -> None:
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_CAPACITY"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=-1,
        )


class _FakeProc:
    """Minimal fake subprocess for runner error-path tests."""

    def __init__(self, stdout, stderr, stdin=None, returncode=1):
        self.stdout = stdout
        self.stderr = stderr
        self.stdin = stdin
        self.returncode = returncode

    def wait(self, timeout=0):
        return 0

    def kill(self):
        pass


class _RaisingStream:
    def read(self, size):
        raise OSError("stream gone")


class _UnboundedStream:
    def read(self, size):
        return b"x" * 65536


def test_runner_stream_failure_is_stable_error(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    for proc in (
        _FakeProc(stdout=None, stderr=None),  # missing streams
        _FakeProc(stdout=_RaisingStream(), stderr=_RaisingStream()),
        _FakeProc(stdout=_UnboundedStream(), stderr=_UnboundedStream()),
    ):

        def fake_popen(*a, _proc=proc, **k):
            return _proc

        monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
        with pytest.raises(
            Exception, match="DIFF_SNAPSHOT_GIT_ERROR|DIFF_SNAPSHOT_CAPACITY"
        ):
            _live_index_output(
                git_repo,
                b"",
                ["ls-files", "--others"],
                deadline=time.monotonic() + 35.0,
                limit=1024,
            )


def test_dirty_gitlink_frames_opaque_evidence(git_repo: str, monkeypatch) -> None:
    # Mirrors the frozen oracle's own dirty-gitlink test (monkeypatched
    # inventory): a gitlink reported in the dirty set frames opaque
    # evidence and is retained as workspace_gitlinks.
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    sub_repo = os.path.join(git_repo, "vendor")
    os.mkdir(sub_repo)
    subprocess.run(["git", "init", "-q", sub_repo], check=True)
    subprocess.run(["git", "-C", sub_repo, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", sub_repo, "config", "user.name", "t"], check=True)
    (Path(sub_repo) / "lib.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", sub_repo, "add", "."], check=True)
    subprocess.run(["git", "-C", sub_repo, "commit", "-qm", "sub"], check=True)
    subprocess.run(
        ["git", "-C", git_repo, "submodule", "add", "-q", sub_repo, "vendor"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", git_repo, "commit", "-qm", "add submodule"], check=True
    )
    original = module._live_index_output

    def fake_live_output(root, index_bytes, args, **kwargs):
        if args and args[0] == "diff-files":
            return b"vendor\0"
        return original(root, index_bytes, args, **kwargs)

    monkeypatch.setattr(module, "_live_index_output", fake_live_output)
    epochs: list = []
    oracle_generation_readonly(git_repo, "diff", epoch_out=epochs)
    entry = dict(epochs[0].index_entries)[b"vendor"]
    assert entry.startswith(b"160000 ")
    assert epochs[0].workspace_gitlinks == ((b"vendor", entry),)


def test_inventory_consistency_check_fails_closed(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    original = module._live_index_output

    def fake_live_output(root, index_bytes, args, **kwargs):
        if args and args[0] == "diff-files":
            return b"not-tracked.py\0"
        return original(root, index_bytes, args, **kwargs)

    monkeypatch.setattr(module, "_live_index_output", fake_live_output)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        oracle_generation_readonly(git_repo, "diff")


def test_worktree_path_capacity_fails_closed(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    original = module._live_index_output
    many = b"".join(f"f{i}.py\0".encode() for i in range(250_000))

    def fake_live_output(root, index_bytes, args, **kwargs):
        if args and args[0] == "ls-files":
            return many
        return original(root, index_bytes, args, **kwargs)

    monkeypatch.setattr(module, "_live_index_output", fake_live_output)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_CAPACITY"):
        oracle_generation_readonly(git_repo, "diff")


def test_empty_repo_generations_match(tmp_path) -> None:
    root = str(tmp_path / "empty")
    os.mkdir(root)
    subprocess.run(["git", "init", "-q", root], check=True)
    for mode in ("diff", "staged"):
        frozen_epochs: list = []
        readonly_epochs: list = []
        frozen_gen, _ = oracle_generation(root, mode, epoch_out=frozen_epochs)
        readonly_gen, _ = oracle_generation_readonly(
            root, mode, epoch_out=readonly_epochs
        )
        assert frozen_gen == readonly_gen


def test_root_resolution_failure_fails_closed(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    original = module.git_output

    def fake_git_output(root, args, *, deadline, limit):
        if args and args[0] == "rev-parse" and "--show-toplevel" in args:
            return b"no-such-dir-xyz\n"  # canonical_root stat fails
        return original(root, args, deadline=deadline, limit=limit)

    monkeypatch.setattr(module, "git_output", fake_git_output)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_ROOT_MISMATCH"):
        oracle_generation_readonly(git_repo, "diff")


class _BlockingStream:
    def read(self, size):
        import time as _t

        _t.sleep(30)  # blocks past any reasonable deadline
        return b""


class _BrokenStdin:
    def write(self, data):
        raise BrokenPipeError("pipe closed")

    def close(self):
        pass


def test_runner_feed_broken_pipe_is_ignored(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    class _EmptyStream:
        def read(self, size):
            return b""

    for stdin in (None, _BrokenStdin()):
        proc = _FakeProc(
            stdout=_EmptyStream(),
            stderr=_EmptyStream(),
            stdin=stdin,
            returncode=0,
        )

        def fake_popen(*a, _proc=proc, **k):
            return _proc

        monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
        out = _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
            input_=b"input-data",
        )
        assert out == b""


def test_runner_blocking_stream_times_out(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    proc = _FakeProc(stdout=_BlockingStream(), stderr=_BlockingStream())
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: proc)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_TIMEOUT"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 0.8,
            limit=1024,
        )


def test_runner_kill_cleanup_swallows_wait_errors(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    class _SlowKillProc(_FakeProc):
        def wait(self, timeout=0):
            if self._wait_calls:
                raise subprocess.TimeoutExpired("git", 0)
            self._wait_calls = True
            return 0

    class _EmptyStream:
        def read(self, size):
            return b""

    proc = _SlowKillProc(stdout=_EmptyStream(), stderr=_EmptyStream(), returncode=1)
    proc._wait_calls = False
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: proc)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
        )


def test_runner_nonzero_exit_is_stable_error(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    class _EmptyStream:
        def read(self, size):
            return b""

    proc = _FakeProc(stdout=_EmptyStream(), stderr=_EmptyStream(), returncode=2)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: proc)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
        )
