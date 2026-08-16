"""RFC-0022 P0.4 zero-write staged constraint probe differential contract.

The zero-write staged probes (``diff_snapshot_constraints_readonly``)
must reproduce the frozen probes' evidence (constraint config discovery,
staged-sources-match-worktree) with zero filesystem writes. These tests
prove equality on staged constraint/config fixtures and assert the
read-only invocation set never materializes a temporary index.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST
from tree_sitter_analyzer.diff_snapshot_constraints import (
    frozen_index_constraint_config,
    frozen_index_sources_match_worktree,
)
from tree_sitter_analyzer.diff_snapshot_constraints_readonly import (
    frozen_index_constraint_config_readonly,
    frozen_index_sources_match_worktree_readonly,
)
from tree_sitter_analyzer.diff_snapshot_readonly import oracle_generation_readonly
from tree_sitter_analyzer.source_oracle_git import GitEpoch, oracle_generation


@pytest.fixture()
def git_repo(tmp_path) -> str:
    root = str(tmp_path)
    subprocess.run(["git", "init", "-q", root], check=True)
    for cfg in (
        ["user.email", "t@t"],
        ["user.name", "t"],
        ["maintenance.auto", "false"],
        ["gc.auto", "0"],
    ):
        subprocess.run(["git", "-C", root, "config", *cfg], check=True)
    (tmp_path / "base.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "init"], check=True)
    return root


def _epochs(root: str) -> tuple[GitEpoch, GitEpoch]:
    frozen_epochs: list[GitEpoch] = []
    readonly_epochs: list[GitEpoch] = []
    frozen_gen, _ = oracle_generation(root, "staged", epoch_out=frozen_epochs)
    readonly_gen, _ = oracle_generation_readonly(
        root, "staged", epoch_out=readonly_epochs
    )
    assert frozen_gen == readonly_gen
    return frozen_epochs[0], readonly_epochs[0]


@POSIX_SNAPSHOT_TEST
def test_constraint_config_missing_matches(git_repo: str) -> None:
    frozen_epoch, readonly_epoch = _epochs(git_repo)
    deadline = time.monotonic() + 60.0
    assert frozen_index_constraint_config(
        git_repo, frozen_epoch, deadline, 16 * 1024 * 1024
    ) == frozen_index_constraint_config_readonly(
        git_repo, readonly_epoch, deadline, 16 * 1024 * 1024
    )


@POSIX_SNAPSHOT_TEST
def test_staged_constraint_config_matches(git_repo: str) -> None:
    Path(git_repo, "architectural-constraints.yml").write_text(
        "rules:\n  - id: r1\n", encoding="utf-8"
    )
    Path(git_repo, ".tree-sitter-analyzer").mkdir()
    Path(git_repo, ".tree-sitter-analyzer", "constraints.yml").write_text(
        "rules:\n  - id: r2\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", git_repo, "add", "."], check=True)
    frozen_epoch, readonly_epoch = _epochs(git_repo)
    deadline = time.monotonic() + 60.0
    frozen = frozen_index_constraint_config(
        git_repo, frozen_epoch, deadline, 16 * 1024 * 1024
    )
    readonly = frozen_index_constraint_config_readonly(
        git_repo, readonly_epoch, deadline, 16 * 1024 * 1024
    )
    assert frozen == readonly
    assert frozen[0] == "architectural-constraints.yml"
    assert frozen[1] == b"rules:\n  - id: r1\n"


@POSIX_SNAPSHOT_TEST
def test_staged_sources_match_worktree_matches_clean(git_repo: str) -> None:
    frozen_epoch, readonly_epoch = _epochs(git_repo)
    deadline = time.monotonic() + 60.0
    frozen = frozen_index_sources_match_worktree(
        git_repo, frozen_epoch, deadline, 16 * 1024 * 1024
    )
    readonly = frozen_index_sources_match_worktree_readonly(
        git_repo, readonly_epoch, deadline, 16 * 1024 * 1024
    )
    assert frozen == readonly


@POSIX_SNAPSHOT_TEST
def test_staged_sources_match_worktree_matches_dirty_source(git_repo: str) -> None:
    # A dirty supported-language source must fail the match in both probes.
    Path(git_repo, "base.py").write_text("value = 2\n", encoding="utf-8")
    frozen_epoch, readonly_epoch = _epochs(git_repo)
    deadline = time.monotonic() + 60.0
    assert not frozen_index_sources_match_worktree(
        git_repo, frozen_epoch, deadline, 16 * 1024 * 1024
    )
    assert not frozen_index_sources_match_worktree_readonly(
        git_repo, readonly_epoch, deadline, 16 * 1024 * 1024
    )


@POSIX_SNAPSHOT_TEST
def test_staged_probe_never_materializes_temporary_index(
    git_repo: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    mkstemp_calls: list[str] = []

    def spy_mkstemp(*args, **kwargs):
        mkstemp_calls.append("mkstemp")
        return tempfile.mkstemp(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
    _readonly_epochs: list[GitEpoch] = []
    oracle_generation_readonly(git_repo, "staged", epoch_out=_readonly_epochs)
    deadline = time.monotonic() + 60.0
    frozen_index_constraint_config_readonly(
        git_repo, _readonly_epochs[0], deadline, 16 * 1024 * 1024
    )
    frozen_index_sources_match_worktree_readonly(
        git_repo, _readonly_epochs[0], deadline, 16 * 1024 * 1024
    )
    assert mkstemp_calls == []
