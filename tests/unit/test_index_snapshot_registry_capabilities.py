"""Reusable capability and deadline coverage for the index snapshot registry."""

from __future__ import annotations

import os
import sqlite3

import pytest


@pytest.fixture(autouse=True)
def _close_registry():
    yield
    from tree_sitter_analyzer.index_snapshot import REGISTRY

    REGISTRY.close_all()


def _snapshot(root):
    from tree_sitter_analyzer.index_snapshot import IndexSnapshot

    return IndexSnapshot(
        None,
        "source",
        "index",
        "generation",
        "complete",
        None,
        str(root.resolve()),
        0,
    )


def test_registry_publish_preserves_source_scope(tmp_path):
    # PR #1254 review 3765918784: reusable snapshots need their scan scope.
    from dataclasses import replace

    import tree_sitter_analyzer.index_snapshot as owner
    from tree_sitter_analyzer.index_source_scope import (
        make_source_scope_descriptor,
    )

    scope = make_source_scope_descriptor(roots=("src",))
    candidate = replace(_snapshot(tmp_path), source_scope=scope)
    published = owner.REGISTRY.publish(candidate, sqlite3.connect(":memory:"), 0)

    assert published.source_scope == scope


def test_registry_retires_logical_match_when_source_scope_changes(tmp_path):
    # Final gate: a capability must retain the exact certified scope descriptor.
    from dataclasses import replace

    import tree_sitter_analyzer.index_snapshot as owner
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    first = replace(
        _snapshot(tmp_path),
        source_scope=make_source_scope_descriptor(roots=("src",)),
    )
    published = owner.REGISTRY.publish(first, sqlite3.connect(":memory:"), 0)
    second = replace(first, source_scope=make_source_scope_descriptor(roots=("lib",)))
    replacement = owner.REGISTRY.publish(second, sqlite3.connect(":memory:"), 0)

    assert replacement.snapshot_id != published.snapshot_id
    assert tuple(owner.REGISTRY._entries) == (
        published.snapshot_id,
        replacement.snapshot_id,
    )


class TestReusableSnapshotLease:
    def test_registry_reusable_pin_is_held_only_inside_context(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        published = owner.REGISTRY.publish(
            _snapshot(tmp_path),
            sqlite3.connect(":memory:"),
            0,
        )

        with owner.REGISTRY.pin_reusable(str(tmp_path)) as snapshot:
            assert snapshot.snapshot_id == published.snapshot_id
            assert owner.REGISTRY._entries[published.snapshot_id].readers == 1

        assert owner.REGISTRY._entries[published.snapshot_id].readers == 0
        owner.REGISTRY.close_all()

    def test_registry_reusable_pin_returns_none_without_capability(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        with owner.REGISTRY.pin_reusable(str(tmp_path)) as snapshot:
            assert snapshot is None

    def test_reusable_lease_rejects_capability_without_source_scope(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot as owner

        owner.REGISTRY.publish(
            _snapshot(tmp_path),
            sqlite3.connect(":memory:"),
            0,
        )

        with owner.lease_reusable_snapshot(str(tmp_path)) as snapshot:
            assert snapshot is None
        owner.REGISTRY.close_all()

    @pytest.mark.parametrize(
        ("current_state", "current_generation", "is_reused"),
        [
            ("unknown", "generation", False),
            ("exact", "different", False),
            ("exact", "generation", True),
        ],
    )
    def test_reusable_lease_requires_exact_current_generation(
        self, tmp_path, monkeypatch, current_state, current_generation, is_reused
    ):
        from dataclasses import replace
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_snapshot as owner
        from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

        candidate = replace(
            _snapshot(tmp_path),
            source_scope=make_source_scope_descriptor(roots=("src",)),
        )
        published = owner.REGISTRY.publish(candidate, sqlite3.connect(":memory:"), 0)
        monkeypatch.setattr(
            owner,
            "capture_current_source_snapshot",
            lambda *_args, **_kwargs: SimpleNamespace(
                state=current_state, generation=current_generation
            ),
        )

        with owner.lease_reusable_snapshot(str(tmp_path)) as snapshot:
            assert (snapshot is not None) is is_reused
            assert owner.REGISTRY._entries[published.snapshot_id].readers == 1

        assert owner.REGISTRY._entries[published.snapshot_id].readers == 0
        owner.REGISTRY.close_all()


def test_registry_acquire_deadline_fails_before_io_lock_wait(monkeypatch) -> None:
    """PR #1254 final audit P1: acquisition must not wait beyond one deadline."""
    import tree_sitter_analyzer.index_snapshot as owner

    owner.REGISTRY.close_all()
    snapshot = owner.IndexSnapshot(
        None,
        "source",
        "index",
        "generation",
        "complete",
        None,
        os.path.realpath("/project"),
        1,
    )
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    published = owner.REGISTRY.publish(snapshot, connection, 1, 50.0)
    entry = owner.REGISTRY._entries[str(published.snapshot_id)]

    class RefusingLock:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def acquire(self, *, timeout: float) -> bool:
            self.timeouts.append(timeout)
            return False

        def release(self) -> None:
            pytest.fail("unacquired lock was released")

    lock = RefusingLock()
    entry.io_lock = lock
    monkeypatch.setattr(owner.REGISTRY, "_clock", lambda: 7.0)
    with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
        with owner.REGISTRY.acquire(
            str(published.snapshot_id), "/project", deadline=9.5
        ):
            pytest.fail("timed-out acquisition yielded")
    assert lock.timeouts == [2.5]
    assert entry.readers == 0
    owner.REGISTRY.close_all()


def test_registry_acquire_rejects_already_expired_deadline(monkeypatch) -> None:
    import tree_sitter_analyzer.index_snapshot as owner

    owner.REGISTRY.close_all()
    snapshot = owner.IndexSnapshot(
        None,
        "source",
        "index",
        "generation",
        "complete",
        None,
        os.path.realpath("/project"),
        1,
    )
    published = owner.REGISTRY.publish(
        snapshot, sqlite3.connect(":memory:", check_same_thread=False), 1, 50.0
    )
    entry = owner.REGISTRY._entries[str(published.snapshot_id)]
    monkeypatch.setattr(owner.REGISTRY, "_clock", lambda: 10.0)

    try:
        with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
            with owner.REGISTRY.acquire(
                str(published.snapshot_id), "/project", deadline=10.0
            ):
                pytest.fail("expired acquisition yielded")
        assert entry.readers == 0
    finally:
        owner.REGISTRY.close_all()


def test_registry_acquire_rechecks_deadline_after_io_lock(monkeypatch) -> None:
    import tree_sitter_analyzer.index_snapshot as owner

    owner.REGISTRY.close_all()
    snapshot = owner.IndexSnapshot(
        None,
        "source",
        "index",
        "generation",
        "complete",
        None,
        os.path.realpath("/project"),
        1,
    )
    published = owner.REGISTRY.publish(
        snapshot, sqlite3.connect(":memory:", check_same_thread=False), 1, 50.0
    )
    entry = owner.REGISTRY._entries[str(published.snapshot_id)]

    class DeadlineCrossingLock:
        def __init__(self) -> None:
            self.events: list[tuple[str, float] | tuple[str]] = []

        def acquire(self, *, timeout: float) -> bool:
            self.events.append(("acquire", timeout))
            return True

        def release(self) -> None:
            self.events.append(("release",))

    lock = DeadlineCrossingLock()
    entry.io_lock = lock
    clock_values = iter((1.0, 2.0, 3.0, 4.0))
    monkeypatch.setattr(owner.REGISTRY, "_clock", lambda: next(clock_values))

    try:
        with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
            with owner.REGISTRY.acquire(
                str(published.snapshot_id), "/project", deadline=3.0
            ):
                pytest.fail("deadline-crossing acquisition yielded")
        assert lock.events == [("acquire", 1.0), ("release",)]
        assert entry.readers == 0
    finally:
        owner.REGISTRY.close_all()


def test_registry_acquire_yields_when_io_lock_precedes_deadline(monkeypatch) -> None:
    import tree_sitter_analyzer.index_snapshot as owner

    owner.REGISTRY.close_all()
    snapshot = owner.IndexSnapshot(
        None,
        "source",
        "index",
        "generation",
        "complete",
        None,
        os.path.realpath("/project"),
        1,
    )
    published = owner.REGISTRY.publish(
        snapshot, sqlite3.connect(":memory:", check_same_thread=False), 1, 50.0
    )
    entry = owner.REGISTRY._entries[str(published.snapshot_id)]
    monkeypatch.setattr(owner.REGISTRY, "_clock", lambda: 1.0)

    try:
        with owner.REGISTRY.acquire(
            str(published.snapshot_id), "/project", deadline=3.0
        ) as acquired:
            assert acquired == (published, entry.connection)
        assert entry.readers == 0
    finally:
        owner.REGISTRY.close_all()
