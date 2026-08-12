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

    def fake_oracle(project_root, mode="diff", *, deadline=None, manifest=None):
        return "sg_test", identity

    monkeypatch.setattr(snapshots, "oracle_generation", fake_oracle)
    monkeypatch.setattr(
        snapshots, "shared_source_generation", lambda *_a, **_k: "sg_test"
    )
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_source_snapshot as source_snapshot
    from tree_sitter_analyzer.source_oracle import SafePath

    monkeypatch.setattr(
        source_snapshot,
        "capture_current_source_snapshot",
        lambda *_a, **_k: SimpleNamespace(
            state="exact", generation="sg_test", reason=None
        ),
    )

    original_safe_workspace_path = snapshots.safe_workspace_path

    def fake_safe_workspace_path(_root, relative, **kwargs):
        try:
            return original_safe_workspace_path(_root, relative, **kwargs)
        except Exception as exc:
            if "WORKSPACE_UNSUPPORTED" not in str(exc):
                raise
        target = root / relative
        if not target.exists():
            return SafePath(data=None, metadata=(b"missing",), kind="missing")
        if target.is_dir():
            return SafePath(data=None, metadata=(b"directory",), kind="directory")
        if not target.is_file():
            return SafePath(data=None, metadata=(b"unsafe",), kind="unsafe")
        data = target.read_bytes()
        return SafePath(
            data=data,
            metadata=(b"test," + str(len(data)).encode("ascii"),),
            kind="file",
        )

    monkeypatch.setattr(snapshots, "safe_workspace_path", fake_safe_workspace_path)
    import tree_sitter_analyzer.source_oracle as source_oracle

    monkeypatch.setattr(source_oracle, "safe_workspace_path", fake_safe_workspace_path)
    monkeypatch.setattr(
        snapshots,
        "frozen_index_constraint_config",
        lambda *_a, **_k: (None, None, ()),
    )
    monkeypatch.setattr(
        snapshots, "frozen_index_sources_match_worktree", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        snapshots,
        "capture_inventory",
        lambda *args, **kwargs: tuple(inventory_paths),
    )

    def fake_capture(root, mode, deadline, ceiling, expected_manifest=None):
        return b"", frozen

    monkeypatch.setattr(snapshots, "_capture_payload", fake_capture)
    return identity


def make_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "maintenance.auto", "false"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "gc.auto", "0"], cwd=tmp_path, check=True)
    (tmp_path / "old.py").write_text("value = 1\n")
    (tmp_path / "gone.py").write_text("gone = True\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True
    )
    return tmp_path
