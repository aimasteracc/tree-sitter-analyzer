from __future__ import annotations

from tree_sitter_analyzer.diff_snapshot_leases import ClosedLeaseTombstones


def test_closed_lease_exact_pair_is_idempotent() -> None:
    tombstones = ClosedLeaseTombstones(
        capacity=2, lifetime_seconds=10.0, clock=lambda: 1.0
    )
    tombstones.remember("snapshot", "lease")

    assert tombstones.check("snapshot", "lease") == (True, None)


def test_closed_lease_rejects_different_token() -> None:
    tombstones = ClosedLeaseTombstones(
        capacity=2, lifetime_seconds=10.0, clock=lambda: 1.0
    )
    tombstones.remember("snapshot", "lease")

    assert tombstones.check("snapshot", "other") == (
        True,
        "DIFF_SNAPSHOT_LEASE_MISMATCH",
    )


def test_closed_lease_lru_evicts_oldest_entry() -> None:
    tombstones = ClosedLeaseTombstones(
        capacity=1, lifetime_seconds=10.0, clock=lambda: 1.0
    )
    tombstones.remember("first", "lease-1")
    tombstones.remember("second", "lease-2")

    assert tombstones.check("first", "lease-1") == (False, None)


def test_closed_lease_sweep_expires_at_lifetime() -> None:
    now = [1.0]
    tombstones = ClosedLeaseTombstones(
        capacity=2, lifetime_seconds=10.0, clock=lambda: now[0]
    )
    tombstones.remember("snapshot", "lease")
    now[0] = 11.0

    tombstones.sweep()

    assert tombstones.check("snapshot", "lease") == (False, None)


def test_global_close_route_lease_delegates_boolean(monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_registry as registry

    monkeypatch.setattr(
        registry.REGISTRY, "close_lease", lambda snapshot_id, lease_id: True
    )

    assert registry.close_route_lease("snapshot", "lease") is True
