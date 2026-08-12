"""Integration coverage for staged snapshot constraint/source planes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST, make_repo


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@POSIX_SNAPSHOT_TEST
def test_staged_snapshot_constraint_config_comes_from_index_plane(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3765536002: staged constraints are index-plane evidence.
    root = _repo(tmp_path)
    config = root / "architectural-constraints.yml"
    config.write_bytes(b"version: 1\nconstraints: []\n")
    _git(root, "add", config.name)
    config.write_bytes(b"version: 1\nconstraints: [invalid-worktree]\n")
    registry = snapshots.DiffSnapshotRegistry()

    created = registry.create(str(root), "staged", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.constraint_config_path == config.name
    assert consumer.snapshot.constraint_config_data == b"version: 1\nconstraints: []\n"
    assert consumer.snapshot.staged_config_matches_worktree is False
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_staged_snapshot_records_source_plane_divergence(tmp_path: Path) -> None:
    # PR #1254 review 3765536016: live graphs cannot represent dirty staged sources.
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    _git(root, "add", "old.py")
    (root / "old.py").write_text("value = 3\n")
    registry = snapshots.DiffSnapshotRegistry()

    created = registry.create(str(root), "staged", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.staged_source_matches_worktree is False
    consumer.release()
