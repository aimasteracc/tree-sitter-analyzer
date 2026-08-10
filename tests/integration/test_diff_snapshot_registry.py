from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
import tree_sitter_analyzer.source_oracle_git as oracle
from tests.unit._diff_snapshot_support import (
    POSIX_SNAPSHOT_TEST,
    install_fake_snapshot_materializer,
    make_repo,
)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def test_validate_publish_rejects_released_consumer(
    tmp_path: Path, monkeypatch
) -> None:
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    consumer.release()

    assert registry.validate_publish(consumer) == "DIFF_SNAPSHOT_EXPIRED"


def test_validate_publish_rejects_generation_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *args, **kwargs: ("sg_changed", consumer.snapshot.root_identity),
    )

    assert registry.validate_publish(consumer) == "DIFF_SNAPSHOT_SOURCE_CHANGED"
    consumer.release()


def _frozen_result(
    monkeypatch,
    *,
    records,
    inventory_paths=(),
    scope_paths=None,
    bind_error=None,
    publish_error=None,
    agent_summary_only=False,
    scope_mode="strict",
    bound_paths=None,
):
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(
            assessed_scope_paths=(), inventory_paths=tuple(inventory_paths)
        )
    )

    def bind(_consumer, paths):
        if bound_paths is not None:
            bound_paths.extend(paths)
        return bind_error

    monkeypatch.setattr(snapshots.REGISTRY, "bind_assessed_scope", bind)
    monkeypatch.setattr(
        snapshots.REGISTRY, "validate_publish", lambda *args: publish_error
    )
    return ChangeImpactTool(None)._execute_frozen_snapshot(
        frozen={"success": True, "changed_records": records},
        consumer=consumer,
        mode="diff",
        scope_paths=scope_paths or [],
        scope_mode=scope_mode,
        output_format="json",
        agent_summary_only=agent_summary_only,
        compact_only=False,
    )


def test_frozen_impact_builds_no_changes_result(monkeypatch) -> None:
    result = _frozen_result(monkeypatch, records=[])

    assert result["changed_files"] == []


def test_frozen_impact_returns_bind_failure(monkeypatch) -> None:
    result = _frozen_result(
        monkeypatch, records=[], bind_error="DIFF_SNAPSHOT_CAPACITY"
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_CAPACITY"


def test_frozen_impact_returns_publish_failure(monkeypatch) -> None:
    result = _frozen_result(
        monkeypatch, records=[], publish_error="DIFF_SNAPSHOT_SOURCE_CHANGED"
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_SOURCE_CHANGED"


def test_frozen_impact_supports_agent_summary_only(monkeypatch) -> None:
    result = _frozen_result(
        monkeypatch,
        records=[{"path": "a.py"}],
        agent_summary_only=True,
    )

    assert result["agent_summary_only"] is True


def test_frozen_scope_accepts_exact_clean_tracked_file(monkeypatch) -> None:
    # PR #1252: scope validity comes from frozen inventory, not changed records.
    result = _frozen_result(
        monkeypatch,
        records=[],
        inventory_paths=("src/clean.py",),
        scope_paths=["src/clean.py"],
    )

    assert result["success"] is True
    assert result["changed_files"] == []


def test_frozen_scope_accepts_clean_directory_prefix(monkeypatch) -> None:
    # PR #1252: a frozen descendant establishes directory-prefix existence.
    result = _frozen_result(
        monkeypatch,
        records=[],
        inventory_paths=("src/pkg/clean.py",),
        scope_paths=["src/pkg"],
    )

    assert result["success"] is True
    assert result["changed_files"] == []


def test_frozen_scope_rejects_truly_absent_path(monkeypatch) -> None:
    # PR #1252: only identities absent from the frozen inventory are invalid.
    result = _frozen_result(
        monkeypatch,
        records=[],
        inventory_paths=("src/clean.py",),
        scope_paths=["missing.py"],
    )

    assert result["success"] is True
    assert result["scope_paths_invalid"] == ["missing.py"]


@pytest.mark.parametrize("operation", ["bind", "publish"])
@POSIX_SNAPSHOT_TEST
def test_consumer_operations_enforce_thread_ownership(
    tmp_path: Path, operation: str
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    call = (
        (lambda: registry.bind_assessed_scope(consumer, ["old.py"]))
        if operation == "bind"
        else (lambda: registry.validate_publish(consumer))
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(call).result(timeout=2)
    assert result == "DIFF_SNAPSHOT_WRONG_THREAD"
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_unrelated_tmp_sibling_does_not_invalidate_snapshot(tmp_path: Path) -> None:
    # PR #1252 review thread 3746878588.
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    (tmp_path / "unrelated").mkdir()

    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert error is None
    assert consumer is not None
    consumer.release()
    registry.close_lease(
        str(created["diff_snapshot_id"]), str(created["route_lease_id"])
    )


def test_acquire_uses_remaining_lifetime_and_rechecks_expiry(tmp_path, monkeypatch):
    # PR #1252 review thread 3748575970.
    now = [0.0]
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    created = registry.create(str(tmp_path), "diff", [])
    deadlines = []

    def oracle(*args, deadline=None):
        deadlines.append(deadline)
        now[0] = snapshots.HARD_LIFETIME_SECONDS
        state = registry._states[str(created["diff_snapshot_id"])]
        return state.snapshot.source_generation, state.snapshot.root_identity

    monkeypatch.setattr(snapshots.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(snapshots, "oracle_generation", oracle)
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert (consumer, error, deadlines) == (None, "DIFF_SNAPSHOT_EXPIRED", [135.0])


def test_strict_scope_binds_only_scoped_change_and_valid_scope(monkeypatch):
    # PR #1252 review thread 3748575987.
    bound = []
    _frozen_result(
        monkeypatch,
        records=[{"path": "a.py"}, {"path": "b.py"}],
        inventory_paths=("a.py", "b.py"),
        scope_paths=["a.py", "missing.py"],
        bound_paths=bound,
    )
    assert bound == ["a.py"]


def test_report_scope_keeps_workspace_assessment(monkeypatch):
    bound = []
    _frozen_result(
        monkeypatch,
        records=[{"path": "a.py"}, {"path": "b.py"}],
        inventory_paths=("a.py", "b.py"),
        scope_paths=["a.py"],
        scope_mode="report",
        bound_paths=bound,
    )
    assert bound == ["a.py", "b.py"]


@POSIX_SNAPSHOT_TEST
def test_core_symlinks_false_preserves_emulated_symlink_edit(tmp_path: Path) -> None:
    # PR #1252 review thread 3748575998.
    root = _repo(tmp_path)
    link = root / "module.py"
    link.symlink_to("old.py")
    subprocess.run(["git", "add", "module.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "link"], cwd=root, check=True)
    subprocess.run(["git", "config", "core.symlinks", "false"], cwd=root, check=True)
    link.unlink()
    link.write_bytes(b"gone.py")

    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])

    record = next(r for r in created["changed_records"] if r["path"] == "module.py")
    assert (record["status"], record["old_kind"], record["new_kind"]) == (
        "M",
        "symlink",
        "symlink",
    )
    assert (record["old_mode"], record["new_mode"]) == ("120000", "120000")
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer.snapshot.file("module.py").new_bytes == b"gone.py"
    consumer.release()


def test_acquire_rejects_lifetime_exhausted_while_installing_pin(tmp_path, monkeypatch):
    # PR #1252 review thread 3748575970.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: 0.0)
    created = registry.create(str(tmp_path), "diff", [])
    ticks = iter(
        (0.0, snapshots.HARD_LIFETIME_SECONDS, snapshots.HARD_LIFETIME_SECONDS)
    )
    registry._clock = lambda: next(ticks)
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert (consumer, error) == (None, "DIFF_SNAPSHOT_EXPIRED")


def test_cleanup_writable_walk_errors_remain_bounded(monkeypatch) -> None:
    from tree_sitter_analyzer import temp_cleanup

    targets = []

    def fail_walk(*args):
        raise OSError("denied")

    def fail_chmod(path, mode):
        targets.append(path)
        raise OSError("denied")

    monkeypatch.setattr(temp_cleanup.os, "walk", fail_walk)
    monkeypatch.setattr(temp_cleanup, "_CHMOD", fail_chmod)
    temp_cleanup._make_writable("missing", directory=True)
    assert targets == ["missing"]


def test_cleanup_directory_selects_recursive_removal(monkeypatch) -> None:
    from tree_sitter_analyzer import temp_cleanup

    removed = []
    monkeypatch.setattr(temp_cleanup, "_RMTREE", removed.append)
    temp_cleanup.cleanup_path("frozen", directory=True)
    assert removed == ["frozen"]


def test_cleanup_writable_file_only_chmods_leaf(monkeypatch) -> None:
    from tree_sitter_analyzer import temp_cleanup

    calls = []
    monkeypatch.setattr(temp_cleanup, "_CHMOD", lambda path, mode: calls.append(path))
    temp_cleanup._make_writable("leaf", directory=False)
    assert calls == ["leaf"]


def test_cleanup_file_uses_supplied_unlink() -> None:
    from tree_sitter_analyzer import temp_cleanup

    removed = []
    temp_cleanup.cleanup_path("frozen", unlink=removed.append)
    assert removed == ["frozen"]


def test_cleanup_file_defaults_to_process_unlink(monkeypatch) -> None:
    from tree_sitter_analyzer import temp_cleanup

    removed = []
    monkeypatch.setattr(temp_cleanup, "_UNLINK", removed.append)
    temp_cleanup.cleanup_path("frozen")
    assert removed == ["frozen"]


def test_pr_analysis_rejects_invalid_url() -> None:
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    result = ChangeImpactTool(None)._execute_pr_analysis(
        "not-a-pr", True, "json", [], False
    )
    assert result["error"] == "Invalid GitHub PR URL: not-a-pr"


def test_pr_analysis_builds_no_changes_response(monkeypatch) -> None:
    from tree_sitter_analyzer.mcp.tools import change_impact_tool as tool_module
    from tree_sitter_analyzer.pr_url import ParsedPRUrl

    parsed = ParsedPRUrl("owner", "repo", 1)
    monkeypatch.setattr(tool_module, "parse_pr_url", lambda url: parsed)
    monkeypatch.setattr(tool_module, "check_gh_available", lambda: True)
    monkeypatch.setattr(tool_module, "fetch_pr_changed_files", lambda pr: [])
    result = tool_module.ChangeImpactTool(None)._execute_pr_analysis(
        parsed.url, True, "json", [], False
    )
    assert result["changed_files"] == []


@POSIX_SNAPSHOT_TEST
@pytest.mark.parametrize("hostile_leaf", ["directory", "fifo"])
def test_dirty_gitlink_preserves_index_evidence_without_reading_hostile_leaf(
    tmp_path: Path, hostile_leaf: str
) -> None:
    # PR #1252 review: dirty gitlink leaves are opaque even after a hostile swap.
    root = _repo(tmp_path)
    oid = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", "160000", oid, "vendor"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "add gitlink"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    if hostile_leaf == "directory":
        vendor = root / "vendor"
        vendor.mkdir()
        subprocess.run(["git", "init"], cwd=vendor, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=vendor)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=vendor)
        (vendor / "child.txt").write_text("different child head\n")
        subprocess.run(["git", "add", "."], cwd=vendor, check=True)
        subprocess.run(
            ["git", "commit", "-m", "child"],
            cwd=vendor,
            check=True,
            capture_output=True,
        )
    else:
        os.mkfifo(root / "vendor")

    result = snapshots.DiffSnapshotRegistry().create(str(root), "diff", [])

    assert result["success"] is True
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
            "new_oid": oid,
            "unsupported_kind": "dirty_gitlink",
        }
    ]


@POSIX_SNAPSHOT_TEST
def test_remaining_ceiling_bounds_index_before_frozen_materialization(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3751628120: existing charge bounds oracle reads.
    root = _repo(tmp_path)
    for number in range(80):
        (root / f"entry-{number}.txt").write_text(str(number))
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    index_path = root / ".git" / "index"
    assert index_path.stat().st_size == 6590
    calls: list[int] = []
    original_read = oracle._safe_absolute_regular

    def bounded_read(path, *, deadline, limit, allow_missing=False):
        if path == str(index_path):
            calls.append(limit)
        return original_read(
            path, deadline=deadline, limit=limit, allow_missing=allow_missing
        )

    materializations: list[bool] = []
    monkeypatch.setattr(oracle, "_safe_absolute_regular", bounded_read)
    monkeypatch.setattr(
        oracle,
        "_index_entries",
        lambda *args, **kwargs: materializations.append(True),
    )
    registry = snapshots.DiffSnapshotRegistry()
    registry._charged_bytes = snapshots.MAX_MATERIALIZED_BYTES - 1024

    result = registry.create(str(root), "diff", [])

    assert (result, calls, materializations) == (
        {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"},
        [1024],
        [],
    )
