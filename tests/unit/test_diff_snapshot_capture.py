from __future__ import annotations

from pathlib import Path

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import make_repo


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def test_create_releases_reservation_after_unexpected_capture_error(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (_ for _ in ()).throw(RuntimeError())
    )
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPTURE_ERROR",
    }
    assert registry._reservations == {}


def test_create_rejects_payload_larger_than_reservation(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    identity = snapshots.RootIdentity(str(root), 1, 2)
    monkeypatch.setattr(snapshots, "MAX_MATERIALIZED_BYTES", 1)
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(root), identity)
    )
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *a, **k: ("sg", identity)
    )
    monkeypatch.setattr(snapshots, "capture_inventory", lambda *a, **k: ())
    monkeypatch.setattr(snapshots, "_capture_payload", lambda *a: (b"xx", ()))
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPACITY",
    }


def test_create_rejects_generation_change_after_impact(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    identity = snapshots.RootIdentity(str(root), 1, 2)
    generations = iter([("before", identity), ("after", identity)])
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(root), identity)
    )
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *a, **k: next(generations)
    )
    monkeypatch.setattr(snapshots, "_capture_payload", lambda *a: (b"", ()))
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_SOURCE_CHANGED",
    }


def test_create_rejects_capture_that_exhausts_lifetime(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    times = iter(
        [0.0, 0.0, snapshots.HARD_LIFETIME_SECONDS, snapshots.HARD_LIFETIME_SECONDS]
    )
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: next(times))
    identity = snapshots.RootIdentity(str(root), 1, 2)
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(root), identity)
    )
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *a, **k: ("sg", identity)
    )
    monkeypatch.setattr(snapshots, "_capture_payload", lambda *a: (b"", ()))
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_TIMEOUT",
    }


def test_create_rejects_oracle_root_identity_drift(tmp_path: Path, monkeypatch) -> None:
    root = _repo(tmp_path)
    identity = snapshots.RootIdentity(str(root), 1, 2)
    monkeypatch.setattr(
        snapshots, "canonical_root", lambda value: (str(root), identity)
    )
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *a, **k: ("sg", snapshots.RootIdentity(str(root), 3, 4)),
    )
    assert snapshots.DiffSnapshotRegistry().create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_ROOT_MISMATCH",
    }
