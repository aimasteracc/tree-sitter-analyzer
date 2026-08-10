"""Bounded process-local immutable diff snapshot registry (RFC-0022)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .diff_snapshot_capture import FrozenFile, _capture_payload
from .diff_snapshot_leases import SnapshotConsumer
from .diff_snapshot_paths import epoch_inventory, path_collection_storage
from .git_path_codec import path_from_wire, path_to_wire
from .source_oracle import (
    RootIdentity,
    SourceOracleError,
    canonical_root,
    capture_inventory,
    oracle_generation,
)
from .source_oracle_git import GitEpoch

MAX_SNAPSHOTS = 16
MAX_MATERIALIZED_BYTES = 64 * 1024 * 1024
HARD_LIFETIME_SECONDS = 35.0
MAX_SCOPE_PATHS = 4096
MAX_PATH_BYTES = 4096
MAX_SCOPE_BYTES = 1024 * 1024
_PROCESS_LEASE_KEY = secrets.token_bytes(32)


def _path_storage(paths: tuple[str, ...] | list[str] | set[str]) -> int:
    return path_collection_storage(paths)


def _record_storage(files: tuple[FrozenFile, ...]) -> int:
    """Charge the deterministic serialized changed-record metadata."""
    return sum(
        len(
            json.dumps(
                item.record.to_dict(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        for item in files
    )


@dataclass(frozen=True)
class FrozenDiffSnapshot:
    snapshot_id: str
    source_generation: str
    root_identity: RootIdentity
    mode: str
    normalized_patch: bytes
    files: tuple[FrozenFile, ...]
    inventory_paths: tuple[str, ...]
    assessed_scope_paths: tuple[str, ...]
    created_monotonic: float
    materialized_bytes: int
    _inventory_raw_paths: tuple[bytes, ...] = ()
    _assessed_scope_raw_paths: tuple[bytes, ...] = ()

    def file(self, path: str) -> FrozenFile | None:
        try:
            normalized = path_from_wire(path)
        except SourceOracleError:
            return None
        raw = os.fsencode(normalized)
        return next((item for item in self.files if item.record.raw_path == raw), None)


@dataclass
class _State:
    snapshot: FrozenDiffSnapshot
    lease_open: bool = True
    expired: bool = False
    pins: dict[str, int] = field(default_factory=dict)


class DiffSnapshotRegistry:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._states: dict[str, _State] = {}
        self._reservations: dict[str, int] = {}
        # One fixed process-local capability key gives unbounded exact-pair
        # close idempotency without retaining attacker-controlled tombstones.
        self._lease_key = _PROCESS_LEASE_KEY
        self._charged_bytes = 0

    def _sweep(self) -> None:
        now = self._clock()
        for sid, state in list(self._states.items()):
            if now - state.snapshot.created_monotonic >= HARD_LIFETIME_SECONDS:
                state.expired = True
                state.lease_open = False
            if state.expired and not state.pins:
                self._erase(sid)

    def _erase(self, sid: str) -> None:
        state = self._states.pop(sid, None)
        if state:
            self._charged_bytes -= state.snapshot.materialized_bytes

    @staticmethod
    def _error(code: str) -> dict[str, object]:
        return {"success": False, "error_code": code}

    def _route_lease(self, snapshot_id: str) -> str:
        digest = hmac.new(
            self._lease_key, snapshot_id.encode("ascii"), hashlib.sha256
        ).digest()
        token = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return "dl_" + token

    def create(
        self, project_root: str | None, mode: str, assessed_scope_paths: list[str]
    ) -> dict[str, object]:
        if mode not in ("diff", "staged"):
            return self._error("DIFF_SNAPSHOT_UNSUPPORTED_MODE")
        if len(assessed_scope_paths) > MAX_SCOPE_PATHS:
            return self._error("DIFF_SNAPSHOT_CAPACITY")
        if any(not isinstance(path, str) for path in assessed_scope_paths):
            return self._error("DIFF_SNAPSHOT_INVALID_PATH")
        try:
            normalized_input = {path_from_wire(path) for path in assessed_scope_paths}
        except SourceOracleError as exc:
            return self._error(str(exc))
        if any(len(os.fsencode(path)) > MAX_PATH_BYTES for path in normalized_input):
            return self._error("DIFF_SNAPSHOT_CAPACITY")
        if _path_storage(normalized_input) > MAX_SCOPE_BYTES:
            return self._error("DIFF_SNAPSHOT_CAPACITY")
        started = self._clock()
        deadline = time.monotonic() + HARD_LIFETIME_SECONDS
        reservation = secrets.token_urlsafe(16)
        with self._lock:
            self._sweep()
            if len(self._states) + len(self._reservations) >= MAX_SNAPSHOTS:
                return self._error("DIFF_SNAPSHOT_CAPACITY")
            ceiling = (
                MAX_MATERIALIZED_BYTES
                - self._charged_bytes
                - sum(self._reservations.values())
            )
            if ceiling <= 0:
                return self._error("DIFF_SNAPSHOT_CAPACITY")
            # Conservatively reserve every byte that this capture could retain.
            self._reservations[reservation] = ceiling
        try:
            root, identity = canonical_root(project_root)
            pre_manifest: dict[str, tuple[bytes, ...]] = {}
            epochs: list[GitEpoch] = []
            oracle_params = inspect.signature(oracle_generation).parameters
            if "epoch_out" in oracle_params:
                before, before_identity = oracle_generation(
                    root,
                    mode,
                    deadline=deadline,
                    manifest=pre_manifest,
                    epoch_out=epochs,
                )
            elif "manifest" in oracle_params:
                before, before_identity = oracle_generation(
                    root, mode, deadline=deadline, manifest=pre_manifest
                )
            else:
                before, before_identity = oracle_generation(
                    root, mode, deadline=deadline
                )
            if before_identity != identity:
                raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH")
            epoch = epochs[0] if epochs else None
            inventory_paths = (
                epoch_inventory(epoch, mode, ceiling)
                if epoch is not None
                else capture_inventory(root, mode, deadline=deadline, limit=ceiling)
            )
            inventory_size = _path_storage(inventory_paths)
            capture_params = inspect.signature(_capture_payload).parameters
            if "epoch" in capture_params and epoch is not None:
                patch, files = _capture_payload(
                    root,
                    mode,
                    deadline,
                    ceiling - inventory_size,
                    expected_manifest=pre_manifest,
                    epoch=epoch,
                )
            elif "expected_manifest" in capture_params:
                patch, files = _capture_payload(
                    root,
                    mode,
                    deadline,
                    ceiling - inventory_size,
                    expected_manifest=pre_manifest,
                )
            else:
                patch, files = _capture_payload(
                    root, mode, deadline, ceiling - inventory_size
                )
            after, after_identity = oracle_generation(root, mode, deadline=deadline)
            if before != after or identity != after_identity:
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            paths = set(normalized_input)
            paths.update(item.record.path for item in files)
            size = (
                len(patch)
                + sum(
                    len(item.old_bytes or b"") + len(item.new_bytes or b"")
                    for item in files
                )
                + _path_storage(paths)
                + _path_storage(inventory_paths)
                + _record_storage(files)
            )
            if size > ceiling:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            sid = "ds_" + secrets.token_urlsafe(24)
            lease = self._route_lease(sid)
            snapshot = FrozenDiffSnapshot(
                sid,
                before,
                identity,
                mode,
                patch,
                files,
                inventory_paths,
                tuple(sorted(paths, key=os.fsencode)),
                started,
                size,
                tuple(sorted(os.fsencode(path) for path in inventory_paths)),
                tuple(sorted(os.fsencode(path) for path in paths)),
            )
            with self._lock:
                self._reservations.pop(reservation, None)
                self._sweep()
                if self._clock() - started >= HARD_LIFETIME_SECONDS:
                    return self._error("DIFF_SNAPSHOT_TIMEOUT")
                # Re-check the global bound at commit time: concurrent captures
                # may still own conservative reservations.
                if (
                    self._charged_bytes + sum(self._reservations.values()) + size
                    > MAX_MATERIALIZED_BYTES
                ):
                    return self._error("DIFF_SNAPSHOT_CAPACITY")
                self._states[sid] = _State(snapshot)
                self._charged_bytes += size
            return {
                "success": True,
                "diff_snapshot_id": sid,
                "route_lease_id": lease,
                "source_generation": before,
                "changed_records": [x.record.to_dict() for x in files],
                "assessed_scope_paths": [
                    path_to_wire(path) for path in snapshot.assessed_scope_paths
                ],
            }
        except SourceOracleError as exc:
            with self._lock:
                self._reservations.pop(reservation, None)
            return self._error(str(exc))
        except Exception:
            with self._lock:
                self._reservations.pop(reservation, None)
            return self._error("DIFF_SNAPSHOT_CAPTURE_ERROR")

    def acquire(
        self, snapshot_id: str, project_root: str | None
    ) -> tuple[SnapshotConsumer | None, str | None]:
        try:
            _, identity = canonical_root(project_root)
        except SourceOracleError as exc:
            return None, str(exc)
        with self._lock:
            self._sweep()
            state = self._states.get(snapshot_id)
            if state is None or state.expired or not state.lease_open:
                return None, "DIFF_SNAPSHOT_EXPIRED"
            if state.snapshot.root_identity != identity:
                return None, "DIFF_SNAPSHOT_ROOT_MISMATCH"
            pin = secrets.token_urlsafe(16)
            owner = threading.get_ident()
            state.pins[pin] = owner
            consumer = SnapshotConsumer(self, state.snapshot, pin)
        try:
            generation, current_identity = oracle_generation(
                identity.realpath, consumer.snapshot.mode
            )
        except SourceOracleError as exc:
            consumer.release()
            return None, str(exc)
        if (
            current_identity != identity
            or generation != consumer.snapshot.source_generation
        ):
            consumer.release()
            return None, "DIFF_SNAPSHOT_SOURCE_CHANGED"
        return consumer, None

    def bind_assessed_scope(
        self, consumer: SnapshotConsumer, paths: list[str]
    ) -> str | None:
        """Bind validated analysis paths to the pinned immutable epoch."""
        if len(paths) > MAX_SCOPE_PATHS:
            return "DIFF_SNAPSHOT_CAPACITY"
        if any(not isinstance(path, str) for path in paths):
            return "DIFF_SNAPSHOT_INVALID_PATH"
        try:
            normalized = tuple(
                sorted({path_from_wire(path) for path in paths}, key=os.fsencode)
            )
        except SourceOracleError as exc:
            return str(exc)
        if any(len(os.fsencode(path)) > MAX_PATH_BYTES for path in normalized):
            return "DIFF_SNAPSHOT_CAPACITY"
        if _path_storage(normalized) > MAX_SCOPE_BYTES:
            return "DIFF_SNAPSHOT_CAPACITY"
        with self._lock:
            self._sweep()
            state = self._states.get(consumer.snapshot.snapshot_id)
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
                or self._clock() - state.snapshot.created_monotonic
                >= HARD_LIFETIME_SECONDS
            ):
                state.expired = True
                state.lease_open = False
                return "DIFF_SNAPSHOT_EXPIRED"
            old_paths_size = _path_storage(state.snapshot.assessed_scope_paths)
            delta = _path_storage(normalized) - old_paths_size
            if (
                self._charged_bytes + sum(self._reservations.values()) + delta
                > MAX_MATERIALIZED_BYTES
            ):
                return "DIFF_SNAPSHOT_CAPACITY"
            updated = replace(
                state.snapshot,
                assessed_scope_paths=normalized,
                _assessed_scope_raw_paths=tuple(
                    os.fsencode(path) for path in normalized
                ),
                materialized_bytes=state.snapshot.materialized_bytes + delta,
            )
            state.snapshot = updated
            consumer.snapshot = updated
            self._charged_bytes += delta
        return None

    def validate_publish(self, consumer: SnapshotConsumer) -> str | None:
        """Atomically reject a stale/unleased snapshot immediately before publish."""
        with self._lock:
            self._sweep()
            state = self._states.get(consumer.snapshot.snapshot_id)
            remaining = (
                HARD_LIFETIME_SECONDS
                - (self._clock() - state.snapshot.created_monotonic)
                if state is not None
                else 0.0
            )
            if state is None or state.expired or not state.lease_open or remaining <= 0:
                if state is not None:
                    state.expired = True
                    state.lease_open = False
                return "DIFF_SNAPSHOT_EXPIRED"
        try:
            oracle_params = inspect.signature(oracle_generation).parameters
            if "deadline" in oracle_params:
                generation, identity = oracle_generation(
                    consumer.snapshot.root_identity.realpath,
                    consumer.snapshot.mode,
                    deadline=time.monotonic() + remaining,
                )
            else:  # compatibility for injected platform seams
                generation, identity = oracle_generation(
                    consumer.snapshot.root_identity.realpath, consumer.snapshot.mode
                )
        except SourceOracleError as exc:
            return str(exc)
        with self._lock:
            state = self._states.get(consumer.snapshot.snapshot_id)
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
                or self._clock() - state.snapshot.created_monotonic
                >= HARD_LIFETIME_SECONDS
            ):
                state.expired = True
                state.lease_open = False
                return "DIFF_SNAPSHOT_EXPIRED"
            if (
                state.snapshot.root_identity != consumer.snapshot.root_identity
                or identity != state.snapshot.root_identity
            ):
                return "DIFF_SNAPSHOT_ROOT_MISMATCH"
            if (
                state.snapshot.source_generation != consumer.snapshot.source_generation
                or generation != state.snapshot.source_generation
            ):
                return "DIFF_SNAPSHOT_SOURCE_CHANGED"
        return None

    def verify(self, consumer: SnapshotConsumer) -> str | None:
        return self.validate_publish(consumer)

    def _release(self, sid: str, pin: str, owner: int) -> None:
        with self._lock:
            self._sweep()
            state = self._states.get(sid)
            if state is None or state.pins.get(pin) != owner:
                raise RuntimeError("DIFF_SNAPSHOT_PIN_INVALID")
            del state.pins[pin]
            if not state.pins and (state.expired or not state.lease_open):
                self._erase(sid)

    def release_route_lease(self, sid: str, lease: str) -> str | None:
        """Close an owned route lease; repeating the exact token pair is idempotent."""
        with self._lock:
            self._sweep()
            expected = self._route_lease(sid)
            if not hmac.compare_digest(expected, lease):
                return "DIFF_SNAPSHOT_LEASE_MISMATCH"
            state = self._states.get(sid)
            # A valid capability remains idempotent after expiry/erasure without
            # any per-snapshot retained state.
            if state is None:
                return None
            state.lease_open = False
            state.expired = True
            if not state.pins:
                self._erase(sid)
            return None

    def close_lease(self, sid: str, lease: str) -> bool:
        return self.release_route_lease(sid, lease) is None

    def reset(self) -> None:
        with self._lock:
            if any(state.pins for state in self._states.values()):
                raise RuntimeError("DIFF_SNAPSHOT_CONSUMERS_ACTIVE")
            self._states.clear()
            self._reservations.clear()
            self._charged_bytes = 0

    def stats(self) -> tuple[int, int]:
        with self._lock:
            self._sweep()
            return len(self._states), self._charged_bytes


REGISTRY = DiffSnapshotRegistry()


def close_route_lease(diff_snapshot_id: str, route_lease_id: str) -> bool:
    return REGISTRY.close_lease(diff_snapshot_id, route_lease_id)


def reset_registry() -> None:
    REGISTRY.reset()
