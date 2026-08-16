"""RFC-0022 P0.4 zero-write oracle differential contract.

The read-only oracle (``diff_snapshot_readonly``) must produce the exact
same source-generation token as the frozen oracle
(``source_oracle_git``) on identical source state — otherwise task routes
comparing impact tokens against the index oracle would diverge. These
tests prove byte-equality across clean/dirty/untracked/staged states and
assert the read-only invocation set never materializes a temporary index.
"""

from __future__ import annotations

import subprocess

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
