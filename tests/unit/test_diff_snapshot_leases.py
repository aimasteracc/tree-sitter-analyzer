from __future__ import annotations

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as registry_module
from tests.unit._diff_snapshot_support import install_fake_snapshot_materializer


def test_global_close_route_lease_delegates_boolean(monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_registry as registry

    monkeypatch.setattr(
        registry.REGISTRY, "close_lease", lambda snapshot_id, lease_id: True
    )

    assert registry.close_route_lease("snapshot", "lease") is True


def test_release_route_lease_rejects_unknown_snapshot_without_capability() -> None:
    import tree_sitter_analyzer.diff_snapshot_registry as snapshots

    registry = snapshots.DiffSnapshotRegistry()

    assert (
        registry.release_route_lease("missing", "lease")
        == "DIFF_SNAPSHOT_LEASE_MISMATCH"
    )


def test_valid_closed_capability_is_unboundedly_idempotent() -> None:
    registry = registry_module.DiffSnapshotRegistry(clock=lambda: 0.0)
    pairs = [
        (sid, registry._route_lease(sid))
        for index in range(10_000)
        if (sid := f"ds_{index:032d}")
    ]

    assert all(registry.release_route_lease(*pair) is None for pair in pairs)
    assert registry.release_route_lease(*pairs[0]) is None
    assert not hasattr(registry, "_closed_leases")


def test_reset_keeps_process_capability_key_stable() -> None:
    registry = registry_module.DiffSnapshotRegistry(clock=lambda: 0.0)
    snapshot_id = "ds_" + "a" * 32
    lease = registry._route_lease(snapshot_id)

    registry.reset()

    assert registry.release_route_lease(snapshot_id, lease) is None


def test_scope_bind_charges_concurrent_reservations(tmp_path, monkeypatch) -> None:
    # PR #1252 zero-gate 2026-07-02: bind shares the global byte ceiling.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = registry_module.DiffSnapshotRegistry()
    created = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    registry._reservations["concurrent"] = registry_module.MAX_MATERIALIZED_BYTES

    result = registry.bind_assessed_scope(consumer, ["larger-scope.py"])

    assert result == "DIFF_SNAPSHOT_CAPACITY"
    consumer.release()


def _created(tmp_path, monkeypatch):
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = registry_module.DiffSnapshotRegistry()
    result = registry.create(str(tmp_path), "diff", [])
    return registry, result


def test_release_rejects_pin_underflow(tmp_path, monkeypatch) -> None:
    registry, result = _created(tmp_path, monkeypatch)
    consumer, _ = registry.acquire(str(result["diff_snapshot_id"]), str(tmp_path))
    assert consumer is not None
    assert registry.close_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )
    snapshot_id = consumer.snapshot.snapshot_id
    consumer.release()

    with pytest.raises(RuntimeError, match="DIFF_SNAPSHOT_PIN_INVALID"):
        registry._release(snapshot_id, consumer._pin, consumer._owner)


def test_close_lease_rejects_wrong_lease(tmp_path, monkeypatch) -> None:
    registry, result = _created(tmp_path, monkeypatch)

    assert registry.close_lease(str(result["diff_snapshot_id"]), "wrong") is False


def test_create_commit_accounts_for_other_reservations(tmp_path, monkeypatch) -> None:
    # PR #1252 zero-gate 2026-07-02: commit uses the global reservation sum.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = registry_module.DiffSnapshotRegistry()
    capture = registry_module._capture_payload

    def reserve_during_capture(*args, **kwargs):
        result = capture(*args, **kwargs)
        registry._reservations["concurrent"] = registry_module.MAX_MATERIALIZED_BYTES
        return result

    monkeypatch.setattr(registry_module, "_capture_payload", reserve_during_capture)

    assert registry.create(str(tmp_path), "diff", ["x"]) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPACITY",
    }


def test_capability_is_process_wide_across_registry_instances() -> None:
    first = registry_module.DiffSnapshotRegistry()
    snapshot_id = "ds_" + "a" * 32
    lease = first._route_lease(snapshot_id)

    second = registry_module.DiffSnapshotRegistry()

    assert second.release_route_lease(snapshot_id, lease) is None


def test_final_release_clears_consumer_payload_reference(tmp_path, monkeypatch) -> None:
    # PR #1252 review thread 3751415934: erased bytes cannot remain consumer-owned.
    registry, result = _created(tmp_path, monkeypatch)
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    assert registry.close_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )

    consumer.release()

    assert consumer._snapshot is None
    with pytest.raises(RuntimeError, match="^DIFF_SNAPSHOT_RELEASED$"):
        _ = consumer.snapshot


def test_active_pin_keeps_snapshot_capacity_charged(tmp_path, monkeypatch) -> None:
    # PR #1252 review thread 3751415934: only the final pin permits byte erasure.
    registry, result = _created(tmp_path, monkeypatch)
    first, first_error = registry.acquire(
        str(result["diff_snapshot_id"]), str(tmp_path)
    )
    second, second_error = registry.acquire(
        str(result["diff_snapshot_id"]), str(tmp_path)
    )
    assert (first_error, second_error) == (None, None)
    assert first is not None and second is not None
    charged = registry._charged_bytes
    assert registry.close_lease(
        str(result["diff_snapshot_id"]), str(result["route_lease_id"])
    )

    first.release()

    assert registry._charged_bytes == charged
    assert second.snapshot.normalized_patch == b""
    second.release()
    assert registry._charged_bytes == 0


def test_release_failure_still_clears_consumer_reference(tmp_path, monkeypatch) -> None:
    # PR #1252 review thread 3751415934: release cleanup is unconditional.
    registry, result = _created(tmp_path, monkeypatch)
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    monkeypatch.setattr(
        registry,
        "_release",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("release failed")),
    )

    with pytest.raises(RuntimeError, match="^release failed$"):
        consumer.release()

    assert consumer._snapshot is None
