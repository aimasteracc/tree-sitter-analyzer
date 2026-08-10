from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import tree_sitter_analyzer.diff_snapshot_epoch as epoch_module
import tree_sitter_analyzer.diff_snapshot_registry as snapshots
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
