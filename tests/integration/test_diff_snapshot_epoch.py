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


def _assert_frozen_patch_matches_git(root: Path) -> tuple[bytes, bytes]:
    expected = subprocess.run(
        [
            "git",
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    assert created["success"] is True
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    if consumer is None:
        pytest.fail("snapshot acquisition must return a consumer")
    frozen = consumer.snapshot.file("sample.txt")
    if frozen is None:
        pytest.fail("snapshot must contain sample.txt")
    actual = consumer.snapshot.normalized_patch
    new_bytes = frozen.new_bytes
    consumer.release()
    assert actual == expected
    if new_bytes is None:
        pytest.fail("sample.txt must retain frozen new bytes")
    return actual, new_bytes


@POSIX_SNAPSHOT_TEST
def test_core_autocrlf_frozen_patch_matches_git_exactly(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-s.
    root = _repo(tmp_path)
    (root / "sample.txt").write_bytes(b"one\ntwo\n")
    _git(root, "add", "sample.txt")
    _git(root, "commit", "-m", "baseline")
    _git(root, "config", "core.autocrlf", "true")
    (root / "sample.txt").write_bytes(b"one\r\nchanged\r\n")

    _patch, new_bytes = _assert_frozen_patch_matches_git(root)

    assert new_bytes == b"one\nchanged\n"


@POSIX_SNAPSHOT_TEST
def test_eol_attribute_frozen_patch_matches_git_exactly(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-s.
    root = _repo(tmp_path)
    (root / ".gitattributes").write_text("*.txt text eol=lf\n")
    (root / "sample.txt").write_bytes(b"left\nright\n")
    _git(root, "add", ".gitattributes", "sample.txt")
    _git(root, "commit", "-m", "baseline")
    (root / "sample.txt").write_bytes(b"left\r\nupdated\r\n")

    _patch, new_bytes = _assert_frozen_patch_matches_git(root)

    assert new_bytes == b"left\nupdated\n"


@POSIX_SNAPSHOT_TEST
def test_clean_filter_is_rejected_before_frozen_patch(tmp_path: Path) -> None:
    # PR #1252 review thread 4861: external clean filters are unsupported.
    root = _repo(tmp_path)
    _git(root, "config", "filter.upper.clean", "tr a-z A-Z")
    _git(root, "config", "filter.upper.smudge", "cat")
    (root / ".gitattributes").write_text("*.txt filter=upper\n")
    (root / "sample.txt").write_bytes(b"old value\n")
    _git(root, "add", ".gitattributes", "sample.txt")
    _git(root, "commit", "-m", "baseline")
    (root / "sample.txt").write_bytes(b"new value\n")

    created = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert created == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_FILTER",
    }


@POSIX_SNAPSHOT_TEST
def test_nondeterministic_clean_filter_is_rejected(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-s.
    root = _repo(tmp_path)
    _git(root, "config", "filter.random.clean", "uuidgen")
    _git(root, "config", "filter.random.smudge", "cat")
    (root / ".gitattributes").write_text("*.txt filter=random\n")
    (root / "sample.txt").write_bytes(b"baseline\n")
    _git(root, "add", ".gitattributes", "sample.txt")
    _git(root, "commit", "-m", "baseline")
    (root / "sample.txt").write_bytes(b"changed\n")

    created = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert created == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_FILTER",
    }


@POSIX_SNAPSHOT_TEST
def test_staged_snapshot_rejects_active_clean_filter(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-s.
    root = _repo(tmp_path)
    (root / ".gitattributes").write_text("*.txt filter=block\n")
    _git(root, "config", "filter.block.clean", "cat")
    _git(root, "config", "filter.block.smudge", "cat")
    (root / "sample.txt").write_bytes(b"baseline\n")
    _git(root, "add", ".gitattributes", "sample.txt")
    _git(root, "commit", "-m", "baseline")
    (root / "sample.txt").write_bytes(b"staged\n")
    _git(root, "add", "sample.txt")
    _git(root, "config", "filter.block.clean", "false")

    created = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])

    assert created == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_FILTER",
    }


@POSIX_SNAPSHOT_TEST
def test_payload_rejects_missing_pre_manifest_binding(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6XzR-s.
    root = _repo(tmp_path)
    (root / "sample.txt").write_bytes(b"baseline\n")
    _git(root, "add", "sample.txt")
    _git(root, "commit", "-m", "baseline")
    (root / "sample.txt").write_bytes(b"changed\n")
    epochs = []
    oracle.oracle_generation(str(root), "diff", epoch_out=epochs, manifest={})

    with pytest.raises(
        snapshots.SourceOracleError, match="^DIFF_SNAPSHOT_SOURCE_CHANGED$"
    ):
        capture._capture_payload(
            str(root),
            "diff",
            __import__("time").monotonic() + 10,
            1024 * 1024,
            expected_manifest={},
            epoch=epochs[0],
        )
