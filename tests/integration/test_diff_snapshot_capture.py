from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_capture as capture
import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import (
    POSIX_SNAPSHOT_TEST,
    install_fake_snapshot_materializer,
    make_repo,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
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


@POSIX_SNAPSHOT_TEST
def test_staged_snapshot_inventory_contains_only_index_tracked_paths(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "untracked.py").write_text("untracked = True\n")
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "staged", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.inventory_paths == ("gone.py", "old.py")
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_workspace_snapshot_inventory_includes_bounded_untracked_paths(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "untracked.py").write_text("untracked = True\n")
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.inventory_paths == ("gone.py", "old.py", "untracked.py")
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_untracked_executable_is_frozen_as_git_binary_patch(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    script = root / "odd name.py"
    script.write_bytes(b"print('ok')")
    script.chmod(0o755)
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    frozen = consumer.snapshot.file("odd name.py")
    assert frozen is not None
    assert frozen.record.new_mode == "100755"
    assert frozen.new_bytes == b"print('ok')"
    assert b"new file mode 100755" in consumer.snapshot.normalized_patch
    consumer.release()


def test_changed_entries_rejects_truncated_git_status(monkeypatch) -> None:
    monkeypatch.setattr(capture, "git_output", lambda *a, **k: b"R\0only-one-path\0")
    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._rows(".", "staged", 1.0, 10)


def test_changed_entries_deduplicates_tracked_and_untracked(monkeypatch) -> None:
    outputs = iter([b"M\0same.py\0", b"same.py\0"])
    monkeypatch.setattr(capture, "git_output", lambda *a, **k: next(outputs))
    assert capture._rows(".", "diff", 1.0, 10) == [("M", None, "same.py", True)]


def test_safe_mode_rejects_malformed_leaf_metadata() -> None:
    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_UNSAFE_PATH"):
        capture._safe_mode("file", (b"bad",))


def test_safe_mode_reports_missing_without_mode() -> None:
    assert capture._safe_mode("missing", ()) == (None, "missing")


def test_numstat_z_binary_rename_uses_destination_path(monkeypatch) -> None:
    monkeypatch.setattr(
        capture, "git_output", lambda *args, **kwargs: b"-\t-\t\0old.bin\0new.bin\0"
    )

    result = capture._tracked_binary_paths(".", "staged", 1e20, 1024)

    assert result == {"new.bin"}


@pytest.mark.parametrize(
    "raw",
    [
        b"bad\0",
        b"-\t-\t\0old.bin",
        b"-\t-\t\0old.bin\0",
        b"-\t-\t\0\0new.bin\0",
    ],
)
def test_numstat_z_rejects_malformed_rename_continuations(monkeypatch, raw) -> None:
    from tree_sitter_analyzer.source_oracle import SourceOracleError

    monkeypatch.setattr(capture, "git_output", lambda *args, **kwargs: raw)

    with pytest.raises(SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._tracked_binary_paths(".", "staged", 1e20, 1024)


def test_bind_assessed_scope_rejects_materialized_capacity(
    tmp_path: Path, monkeypatch
) -> None:
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    monkeypatch.setattr(snapshots, "MAX_MATERIALIZED_BYTES", registry.stats()[1])

    assert (
        registry.bind_assessed_scope(consumer, ["extra.py"]) == "DIFF_SNAPSHOT_CAPACITY"
    )
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_frozen_scope_inventory_does_not_admit_post_capture_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252: later live workspace identities cannot enter the frozen epoch.
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    captured_inventory = consumer.snapshot.inventory_paths
    (root / "later.py").write_text("later = True\n")

    assert consumer.snapshot.inventory_paths == captured_inventory
    assert "later.py" not in consumer.snapshot.inventory_paths
    consumer.release()


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
def test_staged_symlink_records_unsupported_source_kind(tmp_path: Path) -> None:
    # PR #1252 review thread 3746878582.
    root = _repo(tmp_path)
    (root / "module.py").symlink_to("old.py")
    _git(root, "add", "module.py")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])

    assert result["success"] is True
    record = next(
        item for item in result["changed_records"] if item["path"] == "module.py"
    )
    assert (record["new_kind"], record["new_mode"]) == ("symlink", "120000")


def test_entry_parts_rejects_malformed_git_header() -> None:
    # PR #1252 review thread 3746878580.
    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._entry_parts(b"160000")


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
    assert created["success"] is True
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    assert consumer.snapshot.file("old.py").new_bytes == b"value = 2\n"
    consumer.release()


@POSIX_SNAPSHOT_TEST
@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="tracked: PR #1252 Darwin rejects non-UTF-8 leaf creation",
)
def test_non_utf8_path_is_wire_safe_and_round_trips(tmp_path: Path) -> None:
    # PR #1252 review thread 3747113059.
    root = _repo(tmp_path)
    raw = b"non-utf8-\xff.py"
    absolute = os.path.join(os.fsencode(root), raw)
    fd = os.open(absolute, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        os.write(fd, b"value = 1\n")
    finally:
        os.close(fd)
    subprocess.run([b"git", b"add", b"--", raw], cwd=os.fsencode(root), check=True)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "staged", [])
    encoded = json.dumps(created, ensure_ascii=False).encode("utf-8")
    assert b"git-path-b64:" in encoded
    token = next(
        record["path"]
        for record in created["changed_records"]
        if record["path"].startswith("git-path-b64:")
    )
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    assert consumer.snapshot.file(token).new_bytes == b"value = 1\n"
    consumer.release()
    assert (
        registry.close_lease(
            str(created["diff_snapshot_id"]), str(created["route_lease_id"])
        )["success"]
        is True
    )


@POSIX_SNAPSHOT_TEST
def test_workspace_deletion_and_mode_use_safe_leaf_metadata(tmp_path: Path) -> None:
    # PR #1252 review thread 3747113054.
    root = _repo(tmp_path)
    subprocess.run(["git", "config", "core.filemode", "true"], cwd=root, check=True)
    (root / "old.py").chmod(0o755)
    (root / "gone.py").unlink()
    created = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])
    records = {record["path"]: record for record in created["changed_records"]}
    assert records["old.py"]["new_kind"] == "file"
    assert records["old.py"]["new_mode"] == "100755"
    assert "new_oid" not in records["old.py"]
    assert records["gone.py"]["new_kind"] == "missing"
    assert "new_mode" not in records["gone.py"]
    assert "new_oid" not in records["gone.py"]


def test_frozen_name_status_rejects_truncated_rename() -> None:
    class Git:
        def run(self, *args, **kwargs):
            return b"R\0only-old\0"

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._frozen_rows(Git(), b"head", 1024)


def test_compat_name_status_parses_rename_and_untracked(monkeypatch) -> None:
    outputs = iter((b"R100\0old.py\0new.py\0", b"extra.py\0"))
    monkeypatch.setattr(capture, "git_output", lambda *args, **kwargs: next(outputs))
    assert capture._rows(".", "diff", 1e20, 1024) == [
        ("A", None, "extra.py", False),
        ("R", "old.py", "new.py", True),
    ]


def test_compat_name_status_successful_staged_path(monkeypatch) -> None:
    monkeypatch.setattr(
        capture, "git_output", lambda *args, **kwargs: b"M\0tracked.py\0"
    )
    assert capture._rows(".", "staged", 1e20, 1024) == [("M", None, "tracked.py", True)]


def test_compat_numstat_ignores_text_path(monkeypatch) -> None:
    monkeypatch.setattr(
        capture, "git_output", lambda *args, **kwargs: b"1\t2\ttext.py\0"
    )
    assert capture._tracked_binary_paths(".", "staged", 1e20, 1024) == set()


def test_frozen_numstat_rejects_malformed_row() -> None:
    class Git:
        def run(self, *args, **kwargs):
            return b"bad\0"

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._binary_paths(Git(), b"head", 1024)


@pytest.mark.parametrize("raw", [b"-\t-\t\0old.bin", b"-\t-\t\0old.bin\0"])
def test_frozen_numstat_rejects_truncated_rename(raw: bytes) -> None:
    class Git:
        def run(self, *args, **kwargs):
            return raw

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_GIT_ERROR"):
        capture._binary_paths(Git(), b"head", 1024)


def test_frozen_numstat_parses_binary_rename_destination() -> None:
    class Git:
        def run(self, *args, **kwargs):
            return b"-\t-\t\0old.bin\0new.bin\0"

    assert capture._binary_paths(Git(), b"head", 1024) == {b"new.bin"}


def test_safe_mode_reports_symlink() -> None:
    assert capture._safe_mode("symlink", ()) == ("120000", "symlink")


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
def test_snapshot_disables_external_fsmonitor_hook(tmp_path: Path) -> None:
    # PR #1252 review thread 3747224316.
    root = _repo(tmp_path)
    marker = root / "fsmonitor-invoked"
    hook = root / "hostile-fsmonitor"
    hook.write_text(f"#!/bin/sh\necho invoked > {marker!s}\nsleep 30\n")
    hook.chmod(0o755)
    _git(root, "config", "core.fsmonitor", str(hook))
    (root / "old.py").write_text("value = 2\n")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert result["success"] is True
    assert marker.exists() is False
