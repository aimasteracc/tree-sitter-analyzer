from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_capture as capture
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


def test_every_snapshot_diff_disables_textconv(monkeypatch) -> None:
    # PR #1252 review thread 3746940423.
    from tree_sitter_analyzer.source_oracle_git import GitEpoch

    calls: list[list[str]] = []

    class FakeFrozenGit:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def run(self, args, **kwargs):
            calls.append(args)
            return b""

    monkeypatch.setattr(capture, "FrozenGitEnvironment", FakeFrozenGit)
    monkeypatch.setattr(capture, "_head_entries", lambda *args, **kwargs: {})
    epoch = GitEpoch(
        b"4b825dc642cb6eb9a060e54bf8d69288fbee4904",  # pragma: allowlist secret
        "sha1",
        (),
        (),
        (),
        (),
    )
    capture._capture_payload(".", "staged", 1e20, 1024, epoch=epoch)
    diff_calls = [args for args in calls if args and args[0] == "diff"]
    assert ["--no-textconv" in args for args in diff_calls] == [True, True, True]


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
            "error_code": "DIFF_SNAPSHOT_SOURCE_CHANGED",
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


def test_payload_requires_pre_oracle_epoch() -> None:
    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._capture_payload(".", "staged", 1e20, 1024)


@POSIX_SNAPSHOT_TEST
def test_staged_gitlink_ignores_configured_submodule_suppression(
    tmp_path: Path,
) -> None:
    # PR #1252 review thread 3747224312.
    root = _repo(tmp_path)
    oid = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(root, "config", "diff.ignoreSubmodules", "all")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{oid},vendor")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])

    assert [record["path"] for record in result["changed_records"]] == ["vendor"]


@POSIX_SNAPSHOT_TEST
def test_dirty_gitlink_ignores_configured_submodule_suppression(tmp_path: Path) -> None:
    # PR #1252 review thread 3747224312.
    child = _repo(tmp_path / "child")
    root = _repo(tmp_path / "parent")
    _git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(child),
        "vendor",
    )
    _git(root, "commit", "-am", "add submodule")
    (child / "next.py").write_text("next = True\n")
    _git(child, "add", "next.py")
    _git(child, "commit", "-m", "advance")
    _git(root / "vendor", "pull", "--ff-only")
    _git(root, "config", "diff.ignoreSubmodules", "all")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert [record["path"] for record in result["changed_records"]] == ["vendor"]


@POSIX_SNAPSHOT_TEST
def test_dirty_gitlink_same_oid_remains_explicitly_unsupported(tmp_path: Path) -> None:
    # PR #1252 zero-gate 2026-07-02: dirty-only gitlinks cannot disappear.
    child = _repo(tmp_path / "child")
    root = _repo(tmp_path / "parent")
    _git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(child),
        "vendor",
    )
    _git(root, "commit", "-am", "add submodule")
    (root / "vendor" / "untracked.py").write_text("dirty = True\n")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    oid = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root / "vendor",
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert result["changed_records"] == [
        {
            "path": "vendor",
            "status": "M",
            "old_available": True,
            "new_available": True,
            "binary": False,
            "patch_available": False,
            "old_kind": "gitlink",
            "new_kind": "gitlink",
            "old_mode": "160000",
            "new_mode": "160000",
            "old_oid": oid,
            "unsupported_kind": "dirty_gitlink",
        }
    ]
