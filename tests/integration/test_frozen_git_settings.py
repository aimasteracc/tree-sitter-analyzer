from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import tree_sitter_analyzer.diff_snapshot_epoch as epoch_module
import tree_sitter_analyzer.diff_snapshot_registry as snapshots
import tree_sitter_analyzer.git_subprocess as git_subprocess
from tests.unit._diff_snapshot_support import (
    POSIX_SNAPSHOT_TEST,
    make_repo,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@POSIX_SNAPSHOT_TEST
def test_payload_ignores_live_info_attributes_after_shadow_verification(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3748730781: payloads use frozen attributes.
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    info_attributes = root / ".git" / "info" / "attributes"
    original_verify = epoch_module.FrozenGitEnvironment.verify_source_epoch
    original_exit = epoch_module.FrozenGitEnvironment.__exit__

    def mutate_after_verify(environment) -> None:
        original_verify(environment)
        info_attributes.write_text("old.py binary\n")

    def restore_on_exit(environment, *args) -> None:
        info_attributes.unlink(missing_ok=True)
        original_exit(environment, *args)

    monkeypatch.setattr(
        epoch_module.FrozenGitEnvironment, "verify_source_epoch", mutate_after_verify
    )
    monkeypatch.setattr(epoch_module.FrozenGitEnvironment, "__exit__", restore_on_exit)
    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert result["success"] is True
    assert result["changed_records"][0]["binary"] is False


@POSIX_SNAPSHOT_TEST
def test_payload_ignores_live_config_after_shadow_verification(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3748730781: payloads use frozen config.
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    hostile_attributes = tmp_path.parent / "hostile.attributes"
    hostile_attributes.write_text("old.py binary\n")
    config_path = root / ".git" / "config"
    original_config = config_path.read_bytes()
    original_verify = epoch_module.FrozenGitEnvironment.verify_source_epoch
    original_exit = epoch_module.FrozenGitEnvironment.__exit__

    def mutate_after_verify(environment) -> None:
        original_verify(environment)
        _git(root, "config", "core.attributesFile", str(hostile_attributes))

    def restore_on_exit(environment, *args) -> None:
        config_path.write_bytes(original_config)
        original_exit(environment, *args)

    monkeypatch.setattr(
        epoch_module.FrozenGitEnvironment, "verify_source_epoch", mutate_after_verify
    )
    monkeypatch.setattr(epoch_module.FrozenGitEnvironment, "__exit__", restore_on_exit)
    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert result["success"] is True
    assert result["changed_records"][0]["binary"] is False


@POSIX_SNAPSHOT_TEST
def test_workspace_snapshot_rejects_clean_filter_without_execution(
    tmp_path: Path,
) -> None:
    # PR #1252 review thread 4861: LFS/custom clean filters are unsupported.
    root = _repo(tmp_path)
    sentinel = tmp_path / "filter-ran"
    driver = tmp_path / "malicious-filter.py"
    driver.write_text(
        "import pathlib, sys\n"
        f"pathlib.Path({str(sentinel)!r}).write_text('ran')\n"
        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n"
    )
    (root / ".gitattributes").write_text("*.py filter=malicious\n")
    _git(
        root,
        "config",
        "filter.malicious.clean",
        f"{sys.executable} {driver}",
    )
    (root / "old.py").write_text("value = 2\n")

    assert sentinel.exists() is False
    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])
    assert result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_FILTER"
    assert sentinel.exists() is False


@POSIX_SNAPSHOT_TEST
def test_external_diff_order_file_content_is_not_snapshot_input(tmp_path: Path) -> None:
    """External order-file changes cannot alter a frozen staged snapshot."""
    root = make_repo(tmp_path)
    order = root.parent / f"{root.name}-order"
    order.write_text("old.py\ngone.py\n")
    _git(root, "config", "diff.orderFile", str(order))
    (root / "old.py").write_text("value = 2\n")
    _git(root, "add", "old.py")
    first = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])
    order.write_text("gone.py\nold.py\n")
    second = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])

    assert (first["source_generation"], first["changed_records"]) == (
        second["source_generation"],
        second["changed_records"],
    )


@POSIX_SNAPSHOT_TEST
def test_staged_deletion_freezes_ignored_old_side_attributes(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3751341011: HEAD-only paths and shadow cwd are frozen.
    root = _repo(tmp_path)
    nested = root / "nested"
    nested.mkdir()
    deleted = nested / "old.txt"
    attributes = nested / ".gitattributes"
    deleted.write_text("old side\n")
    (root / ".gitignore").write_text("nested/.gitattributes\n")
    _git(root, "add", ".gitignore", "nested/old.txt")
    _git(root, "commit", "-m", "nested baseline")
    _git(root, "rm", "nested/old.txt")
    nested.mkdir()
    attributes.write_text("old.txt binary\n")
    original_verify = epoch_module.FrozenGitEnvironment.verify_source_epoch
    original_exit = epoch_module.FrozenGitEnvironment.__exit__

    def mutate_after_verify(environment) -> None:
        original_verify(environment)
        attributes.write_text("old.txt -binary\n")

    def restore_on_exit(environment, *args) -> None:
        attributes.write_text("old.txt binary\n")
        original_exit(environment, *args)

    monkeypatch.setattr(
        epoch_module.FrozenGitEnvironment, "verify_source_epoch", mutate_after_verify
    )
    monkeypatch.setattr(epoch_module.FrozenGitEnvironment, "__exit__", restore_on_exit)

    result = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])

    assert result == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_SOURCE_CHANGED",
    }


@POSIX_SNAPSHOT_TEST
def test_staged_snapshot_ignores_untracked_fifo_and_later_mutation(
    tmp_path: Path,
) -> None:
    # PR #1252 review thread 3751807896: staged epochs bind only HEAD/index/settings.
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    _git(root, "add", "old.py")
    fifo = root / "untracked.fifo"
    os.mkfifo(fifo)
    registry = snapshots.DiffSnapshotRegistry()

    created = registry.create(str(root), "staged", [])
    fifo.unlink()
    (root / "untracked.txt").write_text("unrelated mutation\n")
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_frozen_order_file_uses_project_safety_root(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3751807878: shadow cwd cannot authorize project temp.
    root = _repo(tmp_path / "project")
    ignored_temp = root / "ignored-temp"
    ignored_temp.mkdir()
    (root / ".gitignore").write_text("ignored-temp/\n")
    (root / "old.py").write_text("value = 2\n")
    _git(root, "add", "old.py")
    external = tmp_path / "external-temp"
    external.mkdir()
    parents: list[str] = []
    original = git_subprocess.create_private_temp

    def capture_parent(**kwargs):
        parents.append(str(kwargs["directory"]))
        return original(**kwargs)

    monkeypatch.setattr(
        git_subprocess,
        "_order_file_candidates",
        lambda: [str(ignored_temp), str(external)],
    )
    monkeypatch.setattr(git_subprocess, "create_private_temp", capture_parent)
    result = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])

    assert result["success"] is True
    assert parents == [str(external)] * len(parents)
    assert tuple(ignored_temp.iterdir()) == ()


@POSIX_SNAPSHOT_TEST
def test_staged_deletion_verifies_exact_settings_inventory(tmp_path: Path) -> None:
    # PR #1252 review thread 3751807909: shadow check-attr reuses HEAD-only paths.
    root = _repo(tmp_path)
    nested = root / "nested"
    nested.mkdir()
    (nested / ".gitattributes").write_text("old.txt binary\n")
    (nested / "old.txt").write_text("old side\n")
    _git(root, "add", "nested/.gitattributes", "nested/old.txt")
    _git(root, "commit", "-m", "attribute baseline")
    _git(root, "rm", "nested/old.txt")

    old_oid = (
        subprocess.run(
            ["git", "rev-parse", "HEAD:nested/old.txt"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        .stdout.strip()
        .decode()
    )
    result = snapshots.DiffSnapshotRegistry().create(str(root), "staged", [])

    assert result["success"] is True
    assert result["changed_records"] == [
        {
            "path": "nested/old.txt",
            "status": "D",
            "old_available": True,
            "new_available": False,
            "binary": True,
            "patch_available": True,
            "old_kind": "file",
            "new_kind": "missing",
            "old_mode": "100644",
            "old_oid": old_oid,
        }
    ]


@POSIX_SNAPSHOT_TEST
def test_staged_gitlink_patch_forces_short_format(tmp_path: Path) -> None:
    # PR #1252 review thread 3751807924: config cannot enable child commit traversal.
    child = tmp_path / "child"
    child.mkdir()
    _git(child, "init")
    _git(child, "config", "user.email", "test@example.com")
    _git(child, "config", "user.name", "Test")
    (child / "value.txt").write_text("one\n")
    _git(child, "add", "value.txt")
    _git(child, "commit", "-m", "one")
    root = _repo(tmp_path / "super")
    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(child),
            "sub",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    _git(root, "commit", "-am", "gitlink baseline")
    (child / "value.txt").write_text("two\n")
    _git(child, "commit", "-am", "two")
    _git(root / "sub", "fetch")
    _git(root / "sub", "checkout", "FETCH_HEAD")
    _git(root, "add", "sub")
    _git(root, "config", "diff.submodule", "log")
    expected = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--binary",
            "--full-index",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--find-renames",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--submodule=short",
            "--ignore-submodules=none",
            "HEAD",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "staged", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.normalized_patch == expected
    assert b"Submodule sub " not in consumer.snapshot.normalized_patch
    consumer.release()
