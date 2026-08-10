from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

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
def test_capacity_is_stable_error_and_close_releases_charge(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "MAX_SNAPSHOTS", 1)
    first = registry.create(str(root), "diff", [])

    second = registry.create(str(root), "diff", [])

    assert second == {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"}
    assert (
        registry.close_lease(
            str(first["diff_snapshot_id"]), str(first["route_lease_id"])
        )
        is True
    )
    assert registry.stats() == (0, 0)


@POSIX_SNAPSHOT_TEST
def test_expiry_retains_active_consumer_bytes_until_release(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    now = [10.0]
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    result = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    charged = registry.stats()[1]

    now[0] += snapshots.HARD_LIFETIME_SECONDS
    blocked, blocked_error = registry.acquire(
        str(result["diff_snapshot_id"]), str(root)
    )

    assert blocked is None
    assert blocked_error == "DIFF_SNAPSHOT_EXPIRED"
    assert registry.stats() == (1, charged)
    assert consumer is not None
    consumer.release()
    assert registry.stats() == (0, 0)


@POSIX_SNAPSHOT_TEST
def test_snapshot_id_is_bound_to_exact_root_identity(tmp_path: Path) -> None:
    root = _repo(tmp_path / "one")
    other = _repo(tmp_path / "two")
    (root / "old.py").write_text("value = 2\n")
    (other / "old.py").write_text("value = 2\n")
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(root), "diff", [])

    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(other))

    assert consumer is None
    assert error == "DIFF_SNAPSHOT_ROOT_MISMATCH"


def test_reset_rejects_active_consumer_then_clears(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None

    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_CONSUMERS_ACTIVE"):
        registry.reset()
    consumer.release()
    registry.reset()
    assert registry.stats() == (0, 0)


def test_snapshot_consumer_schema_rejects_live_arguments(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
    from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
        SemanticClassifyTool,
    )

    arguments = {"diff_snapshot_id": "ds_x", "file_path": "old.py", "old_ref": "HEAD"}

    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        ASTDiffTool(str(tmp_path)).validate_arguments(arguments)
    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        SemanticClassifyTool(str(tmp_path)).validate_arguments(arguments)


def test_consumer_lifecycle_is_idempotent_context_managed_and_thread_owned(
    tmp_path: Path, monkeypatch
) -> None:
    import concurrent.futures

    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        wrong_thread = pool.submit(consumer.release).exception()
    assert isinstance(wrong_thread, RuntimeError)
    assert str(wrong_thread) == "DIFF_SNAPSHOT_WRONG_THREAD"
    with consumer as frozen:
        assert frozen.file("../bad") is None
    consumer.release()
    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_PIN_INVALID"):
        registry._release(str(result["diff_snapshot_id"]), "bad-pin", 0)


def test_registry_defensive_capacity_and_mode_errors(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()

    assert registry.create(str(root), "branch", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_MODE",
    }
    registry._charged_bytes = snapshots.MAX_MATERIALIZED_BYTES
    assert registry.create(str(root), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPACITY",
    }
    registry._erase("unknown")
    called = []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(snapshots.REGISTRY, "reset", lambda: called.append(True))
    snapshots.reset_registry()
    monkeypatch.undo()
    assert called == [True]


def _created(tmp_path: Path, monkeypatch):
    """Create registry state without invoking the POSIX workspace oracle."""
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(tmp_path), "diff", [])
    return tmp_path, registry, result


def test_acquire_translates_root_error(monkeypatch) -> None:
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(
        snapshots,
        "canonical_root",
        lambda value: (_ for _ in ()).throw(snapshots.SourceOracleError("ROOT")),
    )
    assert registry.acquire("missing", ".") == (None, "ROOT")


def test_acquire_releases_reserved_pin_after_oracle_error(
    tmp_path: Path, monkeypatch
) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *a, **k: (_ for _ in ()).throw(snapshots.SourceOracleError("GEN")),
    )
    assert registry.acquire(str(result["diff_snapshot_id"]), str(root)) == (None, "GEN")
    assert next(iter(registry._states.values())).pins == {}


def test_bind_assessed_scope_translates_invalid_path(
    tmp_path: Path, monkeypatch
) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    assert (
        registry.bind_assessed_scope(consumer, ["../bad"])
        == "DIFF_SNAPSHOT_INVALID_PATH"
    )
    consumer.release()


def test_bind_assessed_scope_rejects_released_consumer(
    tmp_path: Path, monkeypatch
) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    consumer.release()
    assert registry.bind_assessed_scope(consumer, ["ok.py"]) == "DIFF_SNAPSHOT_EXPIRED"


def test_verify_translates_oracle_error(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *a: (_ for _ in ()).throw(snapshots.SourceOracleError("GEN")),
    )
    assert registry.verify(consumer) == "GEN"
    consumer.release()


def test_release_rejects_wrong_thread_owner(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert isinstance(consumer, snapshots.SnapshotConsumer)
    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_PIN_INVALID"):
        registry._release(consumer.snapshot.snapshot_id, consumer._pin, -1)
    consumer.release()


def test_release_rejects_pin_underflow(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    assert (
        registry.close_lease(
            str(result["diff_snapshot_id"]), str(result["route_lease_id"])
        )
        is True
    )
    consumer.release()
    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_PIN_INVALID"):
        registry._release(consumer.snapshot.snapshot_id, consumer._pin, consumer._owner)


def test_close_lease_rejects_wrong_lease(tmp_path: Path, monkeypatch) -> None:
    _, registry, result = _created(tmp_path, monkeypatch)
    assert registry.close_lease(str(result["diff_snapshot_id"]), "wrong") is False


def test_acquire_rejects_generation_drift(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    identity = next(iter(registry._states.values())).snapshot.root_identity
    monkeypatch.setattr(
        snapshots, "oracle_generation", lambda *a: ("different", identity)
    )
    assert registry.acquire(str(result["diff_snapshot_id"]), str(root)) == (
        None,
        "DIFF_SNAPSHOT_SOURCE_CHANGED",
    )


def test_verify_rejects_root_identity_drift(tmp_path: Path, monkeypatch) -> None:
    root, registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(root))
    assert consumer is not None
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *a: (
            consumer.snapshot.source_generation,
            snapshots.RootIdentity(str(root), -1, -1),
        ),
    )
    assert registry.verify(consumer) == "DIFF_SNAPSHOT_ROOT_MISMATCH"
    consumer.release()


def test_sweep_erases_expired_unpinned_snapshot(tmp_path: Path, monkeypatch) -> None:
    _, registry, _ = _created(tmp_path, monkeypatch)
    next(iter(registry._states.values())).expired = True
    assert registry.stats() == (0, 0)


def test_create_rejects_excessive_scope_item_count() -> None:
    registry = snapshots.DiffSnapshotRegistry()

    result = registry.create(
        ".", "diff", [f"path-{index}" for index in range(snapshots.MAX_SCOPE_PATHS + 1)]
    )

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"}


def test_validate_publish_rejects_snapshot_expired_while_pinned(
    tmp_path: Path, monkeypatch
) -> None:
    now = [0.0]
    root = tmp_path
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    now[0] = snapshots.HARD_LIFETIME_SECONDS

    result = registry.validate_publish(consumer)

    assert result == "DIFF_SNAPSHOT_EXPIRED"
    consumer.release()


def test_create_rejects_invalid_scope_storage_inputs() -> None:
    registry = snapshots.DiffSnapshotRegistry()
    too_long = "x" * (snapshots.MAX_PATH_BYTES + 1)
    total_too_long = [f"{index}-" + "x" * 4090 for index in range(257)]

    results = [
        registry.create(".", "diff", [None]),
        registry.create(".", "diff", ["../bad"]),
        registry.create(".", "diff", [too_long]),
        registry.create(".", "diff", total_too_long),
    ]

    assert results == [
        {"success": False, "error_code": "DIFF_SNAPSHOT_INVALID_PATH"},
        {"success": False, "error_code": "DIFF_SNAPSHOT_INVALID_PATH"},
        {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"},
        {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"},
    ]


def test_bind_rejects_invalid_scope_storage_inputs() -> None:
    registry = snapshots.DiffSnapshotRegistry()
    too_many = ["x"] * (snapshots.MAX_SCOPE_PATHS + 1)
    too_long = "x" * (snapshots.MAX_PATH_BYTES + 1)
    total_too_long = [f"{index}-" + "x" * 4090 for index in range(257)]

    results = [
        registry.bind_assessed_scope(None, too_many),
        registry.bind_assessed_scope(None, [None]),
        registry.bind_assessed_scope(None, [too_long]),
        registry.bind_assessed_scope(None, total_too_long),
    ]

    assert results == [
        "DIFF_SNAPSHOT_CAPACITY",
        "DIFF_SNAPSHOT_INVALID_PATH",
        "DIFF_SNAPSHOT_CAPACITY",
        "DIFF_SNAPSHOT_CAPACITY",
    ]


def test_bind_rejects_lease_closed_while_pinned(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    registry.close_lease(
        str(created["diff_snapshot_id"]), str(created["route_lease_id"])
    )

    result = registry.bind_assessed_scope(consumer, ["old.py"])

    assert result == "DIFF_SNAPSHOT_EXPIRED"
    consumer.release()


@POSIX_SNAPSHOT_TEST
def test_bind_large_to_small_rejects_multiple_pins_without_undercharge(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", ["x" * 100])
    first, _ = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    second, _ = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    charged = registry.stats()[1]
    assert registry.bind_assessed_scope(first, ["x"]) == "DIFF_SNAPSHOT_IN_USE"
    assert registry.stats()[1] == charged
    first.release()
    second.release()


@POSIX_SNAPSHOT_TEST
def test_bind_assessed_scope_replaces_scope_for_single_pin(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", ["large-path.py"])
    consumer, _ = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert registry.bind_assessed_scope(consumer, ["small.py"]) is None
    assert consumer.snapshot.assessed_scope_paths == ("small.py",)
    consumer.release()


def test_release_route_lease_reports_unknown_snapshot() -> None:
    registry = snapshots.DiffSnapshotRegistry()
    assert registry.release_route_lease("missing", "lease") == "DIFF_SNAPSHOT_EXPIRED"


def test_validate_publish_bounds_oracle_by_remaining_lifetime(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3746940417.
    now = [0.0]
    root = tmp_path
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    now[0] = snapshots.HARD_LIFETIME_SECONDS - 1.0
    deadlines: list[float] = []
    monkeypatch.setattr(snapshots.time, "monotonic", lambda: 100.0)

    def oracle_with_deadline(root, mode, *, deadline=None):
        deadlines.append(deadline)
        return consumer.snapshot.source_generation, consumer.snapshot.root_identity

    monkeypatch.setattr(snapshots, "oracle_generation", oracle_with_deadline)

    result = registry.validate_publish(consumer)

    assert result is None
    assert deadlines == [101.0]
    consumer.release()


def test_validate_publish_marks_closed_pinned_state_expired(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    registry.close_lease(
        str(created["diff_snapshot_id"]), str(created["route_lease_id"])
    )

    result = registry.validate_publish(consumer)

    assert result == "DIFF_SNAPSHOT_EXPIRED"
    consumer.release()


def test_validate_publish_rejects_expiry_during_bounded_oracle(
    tmp_path: Path, monkeypatch
) -> None:
    now = [0.0]
    root = tmp_path
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None

    def expire_during_oracle(root, mode, *, deadline=None):
        now[0] = snapshots.HARD_LIFETIME_SECONDS
        return consumer.snapshot.source_generation, consumer.snapshot.root_identity

    monkeypatch.setattr(snapshots, "oracle_generation", expire_during_oracle)

    result = registry.validate_publish(consumer)

    assert result == "DIFF_SNAPSHOT_EXPIRED"
    consumer.release()


def test_validate_publish_rejects_erased_snapshot_before_oracle(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    consumer.release()
    registry.reset()

    assert registry.validate_publish(consumer) == "DIFF_SNAPSHOT_EXPIRED"
