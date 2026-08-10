"""Shared deterministic helpers for frozen snapshot tests."""

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tree_sitter_analyzer.diff_snapshot_capture import ChangedFile, FrozenFile

POSIX_SNAPSHOT_TEST = pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: RFC-0022 P0.2 workspace snapshots require POSIX openat/O_NOFOLLOW",
)


def install_fake_snapshot_materializer(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    *,
    records: Sequence[ChangedFile] = (),
    inventory_paths: Sequence[str] = (),
) -> snapshots.RootIdentity:
    """Install deterministic registry seams without opening workspace files.

    Registry lifecycle and MCP projection tests do not exercise the production
    source oracle.  Keeping their state setup synthetic lets those contracts run
    on Windows while the production workspace oracle continues to fail closed.
    """
    root.mkdir(parents=True, exist_ok=True)
    canonical = str(root.resolve())
    identity = snapshots.RootIdentity(canonical, 1, 2)
    frozen = tuple(FrozenFile(record, None, None) for record in records)
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (canonical, identity)
    )
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *args, **kwargs: ("sg_test", identity),
    )
    monkeypatch.setattr(
        snapshots,
        "capture_inventory",
        lambda *args, **kwargs: tuple(inventory_paths),
    )
    monkeypatch.setattr(snapshots, "_capture_payload", lambda *args: (b"", frozen))
    return identity


def make_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "old.py").write_text("value = 1\n")
    (tmp_path / "gone.py").write_text("gone = True\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True
    )
    return tmp_path
