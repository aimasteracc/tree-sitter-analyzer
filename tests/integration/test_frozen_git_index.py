from __future__ import annotations

import subprocess
from pathlib import Path

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
import tree_sitter_analyzer.source_oracle_git as oracle
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST, make_repo


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@POSIX_SNAPSHOT_TEST
def test_staged_gitlink_freezes_mode_and_oid_without_blob_reads(tmp_path: Path) -> None:
    # PR #1252 review thread 3746878580.
    root = _repo(tmp_path)
    oid = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (root / "vendor").mkdir()
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{oid},vendor")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])

    assert result["success"] is True
    record = next(
        item for item in result["changed_records"] if item["path"] == "vendor"
    )
    assert (record["new_kind"], record["new_mode"], record["new_oid"]) == (
        "gitlink",
        "160000",
        oid,
    )


@POSIX_SNAPSHOT_TEST
def test_stage_zero_selector_disambiguates_colon_prefixed_path(tmp_path: Path) -> None:
    # PR #1252 review thread 3746940420.
    root = _repo(tmp_path)
    (root / "foo").write_text("plain old\n")
    (root / "0:foo").write_text("colon old\n")
    _git(root, "add", "foo", "0:foo")
    _git(root, "commit", "-m", "colon baseline")
    (root / "foo").write_text("plain new\n")
    (root / "0:foo").write_text("colon new\n")
    _git(root, "add", "foo", "0:foo")
    registry = snapshots.DiffSnapshotRegistry()

    created = registry.create(str(root), "staged", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    frozen = consumer.snapshot.file("0:foo")
    assert frozen is not None
    assert (frozen.old_bytes, frozen.new_bytes) == (b"colon old\n", b"colon new\n")
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_payload_uses_pre_epoch_index_during_transient_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3747113051: payload must never publish transient index bytes.
    root = _repo(tmp_path)
    target = root / "old.py"
    target.write_text("value = 2\n")
    subprocess.run(["git", "add", "old.py"], cwd=root, check=True)
    original_index = (root / ".git" / "index").read_bytes()
    target.write_text("value = 3\n")
    subprocess.run(["git", "add", "old.py"], cwd=root, check=True)
    transient_index = (root / ".git" / "index").read_bytes()
    (root / ".git" / "index").write_bytes(original_index)
    original_capture = snapshots._capture_payload

    def replace_during_payload(
        root_arg, mode, deadline, ceiling, expected_manifest=None, epoch=None
    ):
        (root / ".git" / "index").write_bytes(transient_index)
        try:
            return original_capture(
                root_arg,
                mode,
                deadline,
                ceiling,
                expected_manifest=expected_manifest,
                epoch=epoch,
            )
        finally:
            (root / ".git" / "index").write_bytes(original_index)

    monkeypatch.setattr(snapshots, "_capture_payload", replace_during_payload)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "staged", [])
    if not created["success"]:
        assert created == {
            "success": False,
            "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_FILTER",
        }
        return
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    assert consumer.snapshot.file("old.py").new_bytes == b"value = 2\n"
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_epoch_entry_derivation_ignores_transient_live_index(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 zero-gate 2026-07-01: stage entries come from no-follow index bytes.
    root = _repo(tmp_path)
    target = root / "old.py"
    target.write_text("value = 2\n")
    _git(root, "add", "old.py")
    safe_index = (root / ".git" / "index").read_bytes()
    target.write_text("value = 3\n")
    _git(root, "add", "old.py")
    transient_index = (root / ".git" / "index").read_bytes()
    (root / ".git" / "index").write_bytes(safe_index)
    real_entries = oracle._index_entries

    def swap_around_derivation(*args, **kwargs):
        (root / ".git" / "index").write_bytes(transient_index)
        try:
            return real_entries(*args, **kwargs)
        finally:
            (root / ".git" / "index").write_bytes(safe_index)

    monkeypatch.setattr(oracle, "_index_entries", swap_around_derivation)
    registry = snapshots.DiffSnapshotRegistry()

    created = registry.create(str(root), "staged", [])
    if not created["success"]:
        assert created == {
            "success": False,
            "error_code": "DIFF_SNAPSHOT_SOURCE_CHANGED",
        }
        return
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.file("old.py").new_bytes == b"value = 2\n"
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_sparse_skip_worktree_missing_path_is_not_a_deletion(tmp_path: Path) -> None:
    # PR #1252 review thread 3748259944.
    root = _repo(tmp_path)
    (root / "kept.py").write_text("value = 1\n")
    _git(root, "add", "kept.py")
    _git(root, "commit", "-m", "sparse baseline")
    _git(root, "update-index", "--skip-worktree", "kept.py")
    (root / "kept.py").unlink()

    created = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert created["success"] is True
    assert created["changed_records"] == []


@POSIX_SNAPSHOT_TEST
def test_assume_unchanged_edit_matches_git_diff_omission(tmp_path: Path) -> None:
    # PR #1252 review thread 3748259944.
    root = _repo(tmp_path)
    (root / "quiet.py").write_text("value = 1\n")
    _git(root, "add", "quiet.py")
    _git(root, "commit", "-m", "assume baseline")
    _git(root, "update-index", "--assume-unchanged", "quiet.py")
    (root / "quiet.py").write_text("value = 2\n")

    expected = subprocess.run(
        ["git", "diff", "--name-only"], cwd=root, check=True, capture_output=True
    ).stdout
    created = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert expected == b""
    assert created["success"] is True
    assert created["changed_records"] == []


@POSIX_SNAPSHOT_TEST
def test_intent_to_add_semantics_match_git_diff(tmp_path: Path) -> None:
    # PR #1252 review thread 3748259944.
    root = _repo(tmp_path)
    (root / "intent.py").write_text("value = 1\n")
    _git(root, "add", "--intent-to-add", "intent.py")
    expected = subprocess.run(
        ["git", "diff", "--name-only", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout

    created = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert expected == b"intent.py\0"
    assert created["success"] is True
    assert [item["path"] for item in created["changed_records"]] == ["intent.py"]


@POSIX_SNAPSHOT_TEST
def test_split_index_is_rejected_without_live_shared_index(tmp_path: Path) -> None:
    # PR #1252 review thread 3748259944.
    root = _repo(tmp_path)
    (root / "tracked.py").write_text("value = 1\n")
    _git(root, "add", "tracked.py")
    _git(root, "commit", "-m", "split baseline")
    _git(root, "update-index", "--split-index")

    created = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert created == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_INDEX",
    }
