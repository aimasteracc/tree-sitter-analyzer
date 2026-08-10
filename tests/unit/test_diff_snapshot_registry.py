"""Contract tests for the RFC-0022 P0.2 in-memory frozen registry."""

from __future__ import annotations

import subprocess
from pathlib import Path

import tree_sitter_analyzer.diff_snapshot_registry as snapshots


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "old.py").write_text("value = 1\n")
    (tmp_path / "gone.py").write_text("gone = True\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def test_staged_snapshot_freezes_add_delete_rename_binary_and_multiple_files(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _git(root, "mv", "old.py", "renamed.py")
    (root / "gone.py").unlink()
    (root / "added.py").write_text("added = True\n")
    (root / "image.bin").write_bytes(b"a\0b")
    _git(root, "add", "-A")
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(str(root), "staged", ["impact.py"])

    assert result["success"] is True
    records = result["changed_records"]
    assert [record["path"] for record in records] == [
        "added.py",
        "gone.py",
        "image.bin",
        "renamed.py",
    ]
    by_path = {record["path"]: record for record in records}
    assert by_path["added.py"]["old_available"] is False
    assert by_path["gone.py"]["new_available"] is False
    assert by_path["renamed.py"]["old_path"] == "old.py"
    assert by_path["image.bin"]["binary"] is True
    assert result["assessed_scope_paths"] == [
        "added.py",
        "gone.py",
        "image.bin",
        "impact.py",
        "renamed.py",
    ]


def test_staged_snapshot_reads_index_not_workspace(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    _git(root, "add", "old.py")
    (root / "old.py").write_text("value = 3\n")
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(str(root), "staged", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    frozen = consumer.snapshot.file("old.py")
    assert frozen is not None
    assert frozen.old_bytes == b"value = 1\n"
    assert frozen.new_bytes == b"value = 2\n"
    consumer.release()


def test_capacity_is_stable_error_and_close_releases_charge(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "MAX_SNAPSHOTS", 1)
    first = registry.create(str(root), "diff", [])

    second = registry.create(str(root), "diff", [])

    assert second == {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"}
    assert (
        registry.close_lease(
            str(first["diff_snapshot_id"]), str(first["route_lease_id"])
        )
        is True
    )
    assert registry.stats() == (0, 0)


def test_expiry_retains_active_consumer_bytes_until_release(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    now = [10.0]
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    result = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    charged = registry.stats()[1]

    now[0] += snapshots.HARD_LIFETIME_SECONDS
    blocked, blocked_error = registry.acquire(
        str(result["diff_snapshot_id"]), str(root)
    )

    assert blocked is None
    assert blocked_error == "DIFF_SNAPSHOT_EXPIRED"
    assert registry.stats() == (1, charged)
    assert consumer is not None
    consumer.release()
    assert registry.stats() == (0, 0)


def test_workspace_mutation_after_capture_returns_stable_source_error(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(root), "diff", [])
    (root / "old.py").write_text("value = 99\n")

    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))

    assert consumer is None
    assert error == "DIFF_SNAPSHOT_SOURCE_CHANGED"
