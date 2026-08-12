"""Consumer validation operations for the process-local diff snapshot registry."""

from __future__ import annotations

import inspect
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .diff_snapshot_leases import SnapshotConsumer
from .diff_snapshot_paths import normalize_bounded_paths, path_collection_storage
from .git_path_codec import path_to_raw
from .source_oracle import RootIdentity, SourceOracleError, canonical_root


def acquire(
    registry: Any,
    snapshot_id: str,
    project_root: str | None,
    *,
    oracle_generation: Callable[..., tuple[str, RootIdentity]],
    shared_source_generation: Callable[[str, float], str],
    hard_lifetime_seconds: float,
    canonicalize_root: Callable[
        [str | None], tuple[str, RootIdentity]
    ] = canonical_root,
) -> tuple[SnapshotConsumer | None, str | None]:
    try:
        _, identity = canonicalize_root(project_root)
    except SourceOracleError as exc:
        return None, str(exc)
    with registry._lock:
        registry._sweep()
        state = registry._states.get(snapshot_id)
        if state is None or state.expired or not state.lease_open:
            return None, "DIFF_SNAPSHOT_EXPIRED"
        if state.snapshot.root_identity != identity:
            return None, "DIFF_SNAPSHOT_ROOT_MISMATCH"
        pin = secrets.token_urlsafe(16)
        owner = threading.get_ident()
        state.pins[pin] = owner
        consumer = SnapshotConsumer(registry, state.snapshot, pin)
        remaining = (
            state.snapshot.created_monotonic + hard_lifetime_seconds - registry._clock()
        )
        if remaining <= 0:
            consumer.release()
            return None, "DIFF_SNAPSHOT_EXPIRED"
    try:
        generation, current_identity = oracle_generation(
            identity.realpath,
            consumer.snapshot.mode,
            deadline=time.monotonic() + remaining,
        )
        shared_generation = shared_source_generation(
            identity.realpath, time.monotonic() + remaining
        )
        generation_after, identity_after = oracle_generation(
            identity.realpath,
            consumer.snapshot.mode,
            deadline=time.monotonic() + remaining,
        )
    except SourceOracleError as exc:
        consumer.release()
        return None, str(exc)
    with registry._lock:
        registry._sweep()
        current = registry._states.get(snapshot_id)
        remaining = (
            state.snapshot.created_monotonic + hard_lifetime_seconds - registry._clock()
        )
        if (
            current is not state
            or state.expired
            or not state.lease_open
            or state.pins.get(pin) != owner
            or remaining <= 0
        ):
            consumer.release()
            return None, "DIFF_SNAPSHOT_EXPIRED"
        if (
            current_identity != identity
            or identity_after != identity
            or generation != generation_after
            or generation != consumer.snapshot.git_generation
            or shared_generation != consumer.snapshot.source_generation
        ):
            consumer.release()
            return None, "DIFF_SNAPSHOT_SOURCE_CHANGED"
    return consumer, None


def bind_assessed_scope(
    registry: Any,
    consumer: SnapshotConsumer,
    paths: list[str],
    *,
    scope_limits: tuple[int, int, int],
    max_materialized_bytes: int,
    hard_lifetime_seconds: float,
    normalize_paths: Callable[..., tuple[str, ...]] = normalize_bounded_paths,
) -> str | None:
    try:
        normalized = normalize_paths(
            paths,
            count_limit=scope_limits[0],
            path_limit=scope_limits[1],
            storage_limit=scope_limits[2],
        )
    except SourceOracleError as exc:
        return str(exc)
    with registry._lock:
        registry._sweep()
        snapshot = consumer._snapshot
        state = registry._states.get(snapshot.snapshot_id) if snapshot else None
        if (
            state is None
            or consumer._released
            or state.pins.get(consumer._pin) != consumer._owner
        ):
            return "DIFF_SNAPSHOT_EXPIRED"
        if threading.get_ident() != consumer._owner:
            return "DIFF_SNAPSHOT_WRONG_THREAD"
        if len(state.pins) != 1:
            return "DIFF_SNAPSHOT_IN_USE"
        if (
            state.expired
            or not state.lease_open
            or registry._clock() - state.snapshot.created_monotonic
            >= hard_lifetime_seconds
        ):
            state.expired = True
            state.lease_open = False
            return "DIFF_SNAPSHOT_EXPIRED"
        old_paths_size = path_collection_storage(state.snapshot.assessed_scope_paths)
        delta = path_collection_storage(normalized) - old_paths_size
        if (
            registry._charged_bytes + sum(registry._reservations.values()) + delta
            > max_materialized_bytes
        ):
            return "DIFF_SNAPSHOT_CAPACITY"
        updated = replace(
            state.snapshot,
            assessed_scope_paths=normalized,
            _assessed_scope_raw_paths=tuple(path_to_raw(path) for path in normalized),
            materialized_bytes=state.snapshot.materialized_bytes + delta,
        )
        state.snapshot = updated
        consumer._snapshot = updated
        registry._charged_bytes += delta
    return None


def validate_publish(
    registry: Any,
    consumer: SnapshotConsumer,
    publish_guard: Callable[[], str | None] | None = None,
    *,
    oracle_generation: Callable[..., tuple[str, RootIdentity]],
    shared_source_generation: Callable[[str, float], str],
    hard_lifetime_seconds: float,
) -> str | None:
    """Revalidate the snapshot and an optional response guard in one publish window."""
    with registry._lock:
        registry._sweep()
        snapshot = consumer._snapshot
        state = registry._states.get(snapshot.snapshot_id) if snapshot else None
        remaining = (
            hard_lifetime_seconds
            - (registry._clock() - state.snapshot.created_monotonic)
            if state is not None
            else 0.0
        )
        if state is None or state.expired or not state.lease_open or remaining <= 0:
            if state is not None:
                state.expired = True
                state.lease_open = False
            return "DIFF_SNAPSHOT_EXPIRED"
        assert snapshot is not None
    try:
        oracle_params = inspect.signature(oracle_generation).parameters
        if "deadline" in oracle_params:
            generation, identity = oracle_generation(
                snapshot.root_identity.realpath,
                snapshot.mode,
                deadline=time.monotonic() + remaining,
            )
        else:  # compatibility for injected platform seams
            generation, identity = oracle_generation(
                snapshot.root_identity.realpath, snapshot.mode
            )
        shared_generation = shared_source_generation(
            snapshot.root_identity.realpath, time.monotonic() + remaining
        )
        guard_error = publish_guard() if publish_guard is not None else None
        shared_generation_after = shared_source_generation(
            snapshot.root_identity.realpath, time.monotonic() + remaining
        )
        if "deadline" in oracle_params:
            generation_after, identity_after = oracle_generation(
                snapshot.root_identity.realpath,
                snapshot.mode,
                deadline=time.monotonic() + remaining,
            )
        else:
            generation_after, identity_after = oracle_generation(
                snapshot.root_identity.realpath, snapshot.mode
            )
    except SourceOracleError as exc:
        return str(exc)
    with registry._lock:
        state = registry._states.get(snapshot.snapshot_id)
        if (
            state is None
            or consumer._released
            or state.pins.get(consumer._pin) != consumer._owner
        ):
            return "DIFF_SNAPSHOT_EXPIRED"
        if threading.get_ident() != consumer._owner:
            return "DIFF_SNAPSHOT_WRONG_THREAD"
        if (
            state.expired
            or not state.lease_open
            or registry._clock() - state.snapshot.created_monotonic
            >= hard_lifetime_seconds
        ):
            state.expired = True
            state.lease_open = False
            return "DIFF_SNAPSHOT_EXPIRED"
        if (
            state.snapshot.root_identity != snapshot.root_identity
            or identity != state.snapshot.root_identity
            or identity_after != state.snapshot.root_identity
        ):
            return "DIFF_SNAPSHOT_ROOT_MISMATCH"
        if generation != generation_after:
            return "DIFF_SNAPSHOT_SOURCE_CHANGED"
        if (
            state.snapshot.source_generation != snapshot.source_generation
            or generation != state.snapshot.git_generation
            or shared_generation != state.snapshot.source_generation
            or shared_generation_after != shared_generation
        ):
            return "DIFF_SNAPSHOT_SOURCE_CHANGED"
        if guard_error is not None:
            return guard_error
    return None
