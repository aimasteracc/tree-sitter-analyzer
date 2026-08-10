from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.unit._diff_snapshot_support import make_repo
from tree_sitter_analyzer import frozen_git_settings as settings
from tree_sitter_analyzer.diff_snapshot_registry import DiffSnapshotRegistry
from tree_sitter_analyzer.source_epoch import (
    GitEpoch,
    capture_source_epoch,
)
from tree_sitter_analyzer.source_oracle import SourceOracleError


def _setting_file(path: bytes, kind: str = "missing", data: bytes | None = None):
    return settings.FrozenSettingFile(path, kind, data)


def _frozen_settings(**changes):
    values = {
        "config_entries": (
            settings.ConfigEntry(b"core.repositoryformatversion", b"0"),
            settings.ConfigEntry(b"core.bare", b"false"),
        ),
        "core_attributes_path": None,
        "core_attributes": None,
        "info_attributes": _setting_file(b"info/attributes"),
        "worktree_attributes": (),
        "object_directory": b"/objects",
        "fingerprint": b"fingerprint",
    }
    values.update(changes)
    return settings.FrozenGitSettings(**values)


def _epoch(git_settings=None, source_epoch=None, tracked_paths=()):
    return GitEpoch(
        b"head",
        "sha1",
        (),
        tracked_paths,
        (),
        (),
        index_bytes=b"index",
        source_epoch=source_epoch,
        git_settings=git_settings,
    )


def test_source_epoch_bounds_attribute_path_input(monkeypatch) -> None:
    monkeypatch.setattr("tree_sitter_analyzer.source_epoch._MAX_SETTINGS_PATH_BYTES", 1)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        capture_source_epoch(".", b"", (b"long",), deadline=1e20, object_format="sha1")


@pytest.mark.parametrize("inactive", [b"unspecified", b"unset"])
def test_filter_attribute_inactive_semantics_are_allowed(inactive: bytes) -> None:
    # PR #1252 review thread 4861: only inactive filter states are deterministic.
    settings.reject_active_filters(b"a.py\0filter\0" + inactive + b"\0", (b"a.py",))


@pytest.mark.parametrize("active", [b"set", b"lfs", b"custom-driver"])
def test_filter_attribute_active_semantics_are_rejected(active: bytes) -> None:
    # PR #1252 review thread 4861: external clean drivers must never run.
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_UNSUPPORTED_FILTER"):
        settings.reject_active_filters(b"a.py\0filter\0" + active + b"\0", (b"a.py",))


@pytest.mark.parametrize(
    "raw",
    [
        b"a.py\0filter",
        b"",
        b"other.py\0filter\0unspecified\0",
        b"a.py\0text\0unspecified\0",
    ],
)
def test_filter_attribute_malformed_output_fails_closed(raw: bytes) -> None:
    # PR #1252 review thread 4861: frozen check-attr output is exact.
    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        settings.reject_active_filters(raw, (b"a.py",))


def test_filter_attribute_output_without_final_nul_is_accepted() -> None:
    # PR #1252 review thread 4861: bounded Git output need not end in a NUL.
    settings.reject_active_filters(b"a.py\0filter\0unspecified", (b"a.py",))


def test_ignored_directory_attributes_are_frozen_for_binary_diff(
    tmp_path: Path,
) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6X2mXl: ignored settings still apply.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    directory = tmp_path / "dir"
    directory.mkdir()
    (directory / "a.txt").write_bytes(b"before\n")
    (tmp_path / ".gitignore").write_text("dir/.gitattributes\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    (directory / ".gitattributes").write_text("*.txt binary\n")
    (directory / "a.txt").write_bytes(b"after\n")
    result = DiffSnapshotRegistry().create(str(tmp_path), "diff", [])

    assert result["success"] is True
    assert [(item["path"], item["binary"]) for item in result["changed_records"]] == [
        ("dir/a.txt", True)
    ]


def test_active_replace_ref_cannot_split_snapshot_head_evidence(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6X2mXp: use the original object graph.
    root = make_repo(tmp_path)
    run = lambda *args, input_=None: subprocess.run(  # noqa: E731
        ["git", *args], cwd=root, input=input_, check=True, capture_output=True
    ).stdout.strip()
    original = run("rev-parse", "HEAD")
    raw_blob = run("rev-parse", "HEAD:old.py")
    blob = run("hash-object", "-w", "--stdin", input_=b"replacement = True\n")
    tree = run("mktree", input_=b"100644 blob " + blob + b"\told.py\n")
    replacement = run("commit-tree", tree.decode(), input_=b"replacement commit\n")
    run("update-ref", "refs/replace/" + original.decode(), replacement.decode())
    (root / "old.py").write_bytes(b"value = 2\n")
    run("add", "old.py")
    live_patch = run("diff", "--cached")
    result = (registry := DiffSnapshotRegistry()).create(str(root), "staged", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    frozen = consumer.snapshot.file("old.py")
    assert b"-replacement = True" in live_patch
    assert frozen is not None
    old_oid = result["changed_records"][0]["old_oid"].encode("ascii")
    assert (frozen.old_bytes, old_oid) == (b"value = 1\n", raw_blob)
    assert b"-value = 1" in consumer.snapshot.normalized_patch
    consumer.release()


def test_staged_records_ignore_git_order_and_use_raw_path_order(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6X3LAF.
    root = make_repo(tmp_path)
    order = root.parent / f"{root.name}-order"
    order.write_text("old.py\ngone.py\n")
    subprocess.run(
        ["git", "config", "diff.orderFile", str(order)], cwd=root, check=True
    )
    (root / "old.py").write_text("value = 2\n")
    (root / "gone.py").write_text("gone = False\n")
    subprocess.run(["git", "add", "old.py", "gone.py"], cwd=root, check=True)

    result = DiffSnapshotRegistry().create(str(root), "staged", [])

    assert [item["path"] for item in result["changed_records"]] == [
        "gone.py",
        "old.py",
    ]


def test_missing_born_index_is_empty_and_reports_head_deletions(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6X3LAM.
    root = make_repo(tmp_path)
    (root / ".git" / "index").unlink()

    result = DiffSnapshotRegistry().create(str(root), "staged", [])

    assert [(item["path"], item["status"]) for item in result["changed_records"]] == [
        ("gone.py", "D"),
        ("old.py", "D"),
    ]


def test_external_diff_order_file_content_is_not_snapshot_input(tmp_path: Path) -> None:
    # PR #1252 review thread PRRT_kwDOPVL-OM6X3LAP.
    root = make_repo(tmp_path)
    order = root.parent / f"{root.name}-order"
    order.write_text("old.py\ngone.py\n")
    subprocess.run(
        ["git", "config", "diff.orderFile", str(order)], cwd=root, check=True
    )
    (root / "old.py").write_text("value = 2\n")
    subprocess.run(["git", "add", "old.py"], cwd=root, check=True)
    first = DiffSnapshotRegistry().create(str(root), "staged", [])
    order.write_text("gone.py\nold.py\n")
    second = DiffSnapshotRegistry().create(str(root), "staged", [])

    assert (first["source_generation"], first["changed_records"]) == (
        second["source_generation"],
        second["changed_records"],
    )
