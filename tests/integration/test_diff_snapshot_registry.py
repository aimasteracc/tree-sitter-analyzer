from __future__ import annotations

from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
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
):
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(
            assessed_scope_paths=(), inventory_paths=tuple(inventory_paths)
        )
    )
    monkeypatch.setattr(
        snapshots.REGISTRY, "bind_assessed_scope", lambda *args: bind_error
    )
    monkeypatch.setattr(
        snapshots.REGISTRY, "validate_publish", lambda *args: publish_error
    )
    return ChangeImpactTool(None)._execute_frozen_snapshot(
        frozen={"success": True, "changed_records": records},
        consumer=consumer,
        mode="diff",
        scope_paths=scope_paths or [],
        scope_mode="strict",
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
