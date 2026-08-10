from __future__ import annotations

import threading
from pathlib import Path

from tests.unit._diff_snapshot_support import install_fake_snapshot_materializer
from tree_sitter_analyzer import diff_snapshot_registry as snapshots


def test_idle_short_lifetime_timer_erases_unpinned_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review 9397: expiry must not depend on a later registry request.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    monkeypatch.setattr(snapshots, "HARD_LIFETIME_SECONDS", 0.02)
    entered = threading.Event()
    proceed = threading.Event()
    fired = threading.Event()

    def timer_factory(delay: float, callback):
        def expire() -> None:
            entered.set()
            proceed.wait(1.0)
            callback()
            fired.set()

        return threading.Timer(delay, expire)

    registry = snapshots.DiffSnapshotRegistry(timer_factory=timer_factory)
    result = registry.create(str(tmp_path), "diff", ["x.py"])
    assert result["success"] is True
    assert registry._charged_bytes != 0
    assert entered.wait(1.0) is True

    proceed.set()
    assert fired.wait(1.0) is True
    with registry._lock:
        assert registry._states == {}
        assert registry._charged_bytes == 0


def test_hard_deadline_timer_retains_pinned_bytes_until_release(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review 9397: a pinned deadline marks expiry before deferred erase.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    callbacks = []

    class Timer:
        daemon = False

        def __init__(self, _delay, callback) -> None:
            callbacks.append(callback)

        def start(self) -> None:
            return None

        def cancel(self) -> None:
            return None

    registry = snapshots.DiffSnapshotRegistry(timer_factory=Timer)
    result = registry.create(str(tmp_path), "diff", ["x.py"])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    charged = registry._charged_bytes

    callbacks[0]()
    assert registry._charged_bytes == charged
    assert next(iter(registry._states.values())).expired is True
    consumer.release()
    assert registry._charged_bytes == 0
    callbacks[0]()
    assert registry._charged_bytes == 0


def test_timer_factory_failure_rolls_back_inserted_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review: timer provisioning is part of atomic snapshot publish.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)

    def fail_factory(_delay, _callback):
        raise RuntimeError("factory failed")

    registry = snapshots.DiffSnapshotRegistry(timer_factory=fail_factory)

    assert registry.create(str(tmp_path), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPTURE_ERROR",
    }
    assert registry.stats() == (0, 0)


def test_timer_schedule_failure_rolls_back_inserted_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review: scheduler exceptions cannot leak charged state.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(
        registry._expiry,
        "schedule",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("schedule failed")),
    )

    assert registry.create(str(tmp_path), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPTURE_ERROR",
    }
    assert registry.stats() == (0, 0)


def test_timer_start_failure_cancels_timer_and_rolls_back_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review: Timer.start may fail after the scheduler retains it.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    cancelled: list[bool] = []

    class Timer:
        daemon = False

        def __init__(self, _delay, _callback) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("start failed")

        def cancel(self) -> None:
            cancelled.append(True)

    registry = snapshots.DiffSnapshotRegistry(timer_factory=Timer)

    assert registry.create(str(tmp_path), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPTURE_ERROR",
    }
    assert cancelled == [True]
    assert registry.stats() == (0, 0)


def test_timer_start_callback_race_does_not_double_charge_rollback(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review: callback may fire synchronously before start raises.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)

    class Timer:
        daemon = False

        def __init__(self, _delay, callback) -> None:
            self.callback = callback

        def start(self) -> None:
            self.callback()
            raise RuntimeError("start failed after callback")

        def cancel(self) -> None:
            return None

    registry = snapshots.DiffSnapshotRegistry(timer_factory=Timer)

    assert registry.create(str(tmp_path), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPTURE_ERROR",
    }
    assert registry.stats() == (0, 0)


def test_timer_start_and_cancel_failure_still_rolls_back_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3751341035: rollback survives cancel failure too.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)

    class Timer:
        daemon = False

        def __init__(self, _delay, _callback) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("start failed")

        def cancel(self) -> None:
            raise RuntimeError("cancel failed")

    registry = snapshots.DiffSnapshotRegistry(timer_factory=Timer)

    assert registry.create(str(tmp_path), "diff", []) == {
        "success": False,
        "error_code": "DIFF_SNAPSHOT_CAPTURE_ERROR",
    }
    assert registry.stats() == (0, 0)


def test_validate_publish_rejects_pin_released_during_oracle(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252: final validation rechecks the pin after the bounded oracle.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None
    snapshot = consumer.snapshot

    def release_during_oracle(_root, _mode, *, deadline=None):
        consumer.release()
        return snapshot.source_generation, snapshot.root_identity

    monkeypatch.setattr(snapshots, "oracle_generation", release_during_oracle)

    assert registry.validate_publish(consumer) == "DIFF_SNAPSHOT_EXPIRED"
