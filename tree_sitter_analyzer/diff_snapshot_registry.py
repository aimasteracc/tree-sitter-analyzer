"""Bounded process-local immutable diff snapshot registry (RFC-0022)."""
# fmt: off
# ruff: noqa: I001

from __future__ import annotations

import hmac
import inspect
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import cast

from .diff_snapshot_capture import (
    _capture_payload,
    frozen_index_constraint_config,
    frozen_index_sources_match_worktree,
)
from .diff_snapshot_expiry import SnapshotExpiryScheduler, schedule_expiry
from .diff_snapshot_leases import (
    FrozenDiffSnapshot,
    SnapshotConsumer,
    route_lease,
    snapshot_error,
)
from .diff_snapshot_paths import (
    epoch_inventory,
    normalize_bounded_paths,
    path_collection_storage,
    record_storage,
)
from .git_path_codec import path_to_raw, path_to_wire
from .source_oracle import (
    RootIdentity as RootIdentity,
    SourceOracleError,
    WorkspaceManifestEntry,
    canonical_root,
    capture_inventory,
    oracle_generation,
    safe_workspace_path,
)
from .source_oracle_git import GitEpoch

MAX_SNAPSHOTS = 16
MAX_MATERIALIZED_BYTES = 64 * 1024 * 1024
HARD_LIFETIME_SECONDS = 35.0
MAX_SCOPE_PATHS = 4096
MAX_PATH_BYTES = 4096
MAX_SCOPE_BYTES = 1024 * 1024
_PROCESS_LEASE_KEY = secrets.token_bytes(32)
_SNAPSHOT_ID_PATTERN = re.compile(r"ds_[A-Za-z0-9_-]{32}", re.ASCII)
_ROUTE_LEASE_PATTERN = re.compile(r"dl_[A-Za-z0-9_-]{43}", re.ASCII)


def shared_source_generation(project_root: str, deadline: float) -> str:
    """Return the P0.1 source-oracle token, replaying its certified scope."""
    from .index_snapshot import lease_existing_snapshot, lease_reusable_snapshot
    from .index_source_snapshot import capture_current_source_snapshot

    if time.monotonic() > deadline:
        raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT")
    with lease_reusable_snapshot(project_root) as reusable:
        if reusable is not None and reusable.source_generation is not None:
            return reusable.source_generation
    with lease_existing_snapshot(project_root) as existing:
        if existing.source_generation is not None:
            return existing.source_generation
        if existing.reason not in ("MISSING_INDEX",):
            raise SourceOracleError(existing.reason or "DIFF_SNAPSHOT_SOURCE_CHANGED")
    current = capture_current_source_snapshot(project_root, deadline=deadline)
    if current.state != "exact" or current.generation is None:
        raise SourceOracleError(current.reason or "DIFF_SNAPSHOT_SOURCE_CHANGED")
    return current.generation


@dataclass
class _State:
    snapshot: FrozenDiffSnapshot
    lease_open: bool = True
    expired: bool = False
    pins: dict[str, int] = field(default_factory=dict)


class DiffSnapshotRegistry:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        timer_factory: Callable[[float, Callable[[], None]], object] = threading.Timer,
    ) -> None:
        self._clock = clock
        self._expiry = SnapshotExpiryScheduler(timer_factory)
        self._lock = threading.RLock()
        self._states: dict[str, _State] = {}
        self._reservations: dict[str, int] = {}
        self._lease_key = _PROCESS_LEASE_KEY
        self._charged_bytes = 0

    def _sweep(self) -> None:
        now = self._clock()
        for sid, state in list(self._states.items()):
            if now - state.snapshot.created_monotonic >= HARD_LIFETIME_SECONDS:
                state.expired = True
                state.lease_open = False
                self._expiry.cancel(sid)
            if state.expired and not state.pins:
                self._erase(sid)

    def _erase(self, sid: str) -> None:
        state = self._states.pop(sid, None)
        if state:
            self._expiry.cancel(sid)
            self._charged_bytes -= state.snapshot.materialized_bytes

    def _expire(self, sid: str, expected: _State) -> None:
        with self._lock:
            state = self._states.get(sid)
            if state is not expected:
                return
            self._expiry.fired(sid)
            state.expired = True
            state.lease_open = False
            if not state.pins:
                self._erase(sid)

    def _route_lease(self, snapshot_id: str) -> str:
        return route_lease(self._lease_key, snapshot_id)
    def create(
        self, project_root: str | None, mode: str, assessed_scope_paths: list[str]
    ) -> dict[str, object]:
        if mode not in ("diff", "staged"):
            return snapshot_error("DIFF_SNAPSHOT_UNSUPPORTED_MODE")
        try:
            normalized_input = set(
                normalize_bounded_paths(
                    assessed_scope_paths,
                    count_limit=MAX_SCOPE_PATHS,
                    path_limit=MAX_PATH_BYTES,
                    storage_limit=MAX_SCOPE_BYTES,
                )
            )
        except SourceOracleError as exc:
            return snapshot_error(str(exc))
        started = self._clock()
        deadline = time.monotonic() + HARD_LIFETIME_SECONDS
        reservation = secrets.token_urlsafe(16)
        with self._lock:
            self._sweep()
            if len(self._states) + len(self._reservations) >= MAX_SNAPSHOTS:
                return snapshot_error("DIFF_SNAPSHOT_CAPACITY")
            ceiling = (
                MAX_MATERIALIZED_BYTES
                - self._charged_bytes
                - sum(self._reservations.values())
            )
            if ceiling <= 0:
                return snapshot_error("DIFF_SNAPSHOT_CAPACITY")
            self._reservations[reservation] = ceiling
        try:
            root, identity = canonical_root(project_root)
            shared_before = shared_source_generation(root, deadline)
            pre_manifest: dict[str, WorkspaceManifestEntry] = {}
            epochs: list[GitEpoch] = []
            oracle_call: Callable[..., tuple[str, RootIdentity]] = oracle_generation
            oracle_params = inspect.signature(oracle_call).parameters
            oracle_budget = (
                {"byte_ceiling": ceiling} if "byte_ceiling" in oracle_params else {}
            )
            if "epoch_out" in oracle_params:
                before, before_identity = oracle_call(
                    root,
                    mode,
                    deadline=deadline,
                    manifest=pre_manifest,
                    epoch_out=epochs,
                    **oracle_budget,
                )
            elif "manifest" in oracle_params:
                before, before_identity = oracle_call(
                    root,
                    mode,
                    deadline=deadline,
                    manifest=pre_manifest,
                    **oracle_budget,
                )
            else:
                before, before_identity = oracle_call(
                    root, mode, deadline=deadline, **oracle_budget
                )
            if before_identity != identity:
                raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH")
            epoch = epochs[0] if epochs else None
            inventory_paths = (
                epoch_inventory(epoch, mode, ceiling)
                if epoch is not None
                else capture_inventory(root, mode, deadline=deadline, limit=ceiling)
            )
            inventory_size = path_collection_storage(inventory_paths)
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
            post_manifest: dict[str, WorkspaceManifestEntry] = {}
            after, after_identity = oracle_call(
                root,
                mode,
                deadline=deadline,
                manifest=post_manifest,
                **oracle_budget,
            )
            shared_after = shared_source_generation(root, deadline)
            if (
                shared_before != shared_after
                or before != after
                or identity != after_identity
                or pre_manifest != post_manifest
            ):
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            live_config = None
            live_config_path = None
            for candidate in (
                "architectural-constraints.yml",
                ".tree-sitter-analyzer/constraints.yml",
            ):
                probe = safe_workspace_path(
                    root, candidate, deadline=deadline, limit=1024 * 1024
                )
                live_config = probe
                if probe.kind != "missing":
                    if probe.kind != "file" or probe.data is None:
                        raise SourceOracleError("CONSTRAINT_CONFIG_UNSAFE")
                    live_config_path = candidate
                    break
            assert live_config is not None
            staged_source_matches_worktree = True
            staged_config_matches_worktree = True
            if mode == "staged":
                if epoch is None and "epoch_out" in oracle_params:
                    raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
                staged_epoch = cast(GitEpoch, epoch)
                (
                    constraint_config_path,
                    constraint_config_data,
                    constraint_config_metadata,
                ) = frozen_index_constraint_config(
                    root, staged_epoch, deadline, ceiling
                )
                staged_source_matches_worktree = frozen_index_sources_match_worktree(
                    root,
                    staged_epoch,
                    deadline,
                    min(16 * 1024 * 1024, ceiling),
                )
                staged_config_matches_worktree = (
                    constraint_config_path == live_config_path
                    and constraint_config_data == live_config.data
                )
                if staged_config_matches_worktree:
                    # Preserve the worktree descriptor evidence used by the
                    # final publish guard; stage-zero identity is held by epoch.
                    constraint_config_metadata = live_config.metadata
            else:
                constraint_config_path = live_config_path
                constraint_config_data = live_config.data
                constraint_config_metadata = live_config.metadata
            final_manifest: dict[str, WorkspaceManifestEntry] = {}
            final_git, final_identity = oracle_call(
                root,
                mode,
                deadline=deadline,
                manifest=final_manifest,
                **oracle_budget,
            )
            if (
                final_git != before
                or final_identity != identity
                or final_manifest != pre_manifest
            ):
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            paths = set(normalized_input)
            paths.update(item.record.path for item in files)
            size = (
                len(patch)
                + sum(
                    len(item.old_bytes or b"") + len(item.new_bytes or b"")
                    for item in files
                )
                + path_collection_storage(paths)
                + path_collection_storage(inventory_paths)
                + record_storage(files)
                + len(constraint_config_data or b"")
                + sum(len(item) for item in constraint_config_metadata)
            )
            if size > ceiling:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            sid = "ds_" + secrets.token_urlsafe(24)
            lease = route_lease(self._lease_key, sid)
            snapshot = FrozenDiffSnapshot(
                snapshot_id=sid,
                source_generation=shared_before,
                git_generation=before,
                root_identity=identity,
                mode=mode,
                normalized_patch=patch,
                files=files,
                inventory_paths=inventory_paths,
                assessed_scope_paths=tuple(sorted(paths, key=path_to_raw)),
                created_monotonic=started,
                materialized_bytes=size,
                constraint_config_path=constraint_config_path,
                constraint_config_data=constraint_config_data,
                constraint_config_metadata=constraint_config_metadata,
                staged_source_matches_worktree=staged_source_matches_worktree,
                staged_config_matches_worktree=staged_config_matches_worktree,
                _inventory_raw_paths=tuple(
                    sorted(path_to_raw(path) for path in inventory_paths)
                ),
                _assessed_scope_raw_paths=tuple(
                    sorted(path_to_raw(path) for path in paths)
                ),
            )
            with self._lock:
                self._reservations.pop(reservation, None)
                self._sweep()
                if self._clock() - started >= HARD_LIFETIME_SECONDS:
                    return snapshot_error("DIFF_SNAPSHOT_TIMEOUT")
                used = self._charged_bytes + sum(self._reservations.values()) + size
                if used > MAX_MATERIALIZED_BYTES:
                    return snapshot_error("DIFF_SNAPSHOT_CAPACITY")
                state = _State(snapshot)
                self._states[sid] = state
                self._charged_bytes += size
                schedule_expiry(
                    self._expiry,
                    sid,
                    snapshot.created_monotonic + HARD_LIFETIME_SECONDS - self._clock(),
                    lambda: self._expire(sid, state),
                    rollback=lambda: self._erase(sid),
                )
            return {
                "success": True,
                "diff_snapshot_id": sid,
                "route_lease_id": lease,
                "source_generation": shared_before,
                "changed_records": [x.record.to_dict() for x in files],
                "assessed_scope_paths": [
                    path_to_wire(path) for path in snapshot.assessed_scope_paths
                ],
            }
        except SourceOracleError as exc:
            with self._lock:
                self._reservations.pop(reservation, None)
            return snapshot_error(str(exc))
        except Exception:
            with self._lock:
                self._reservations.pop(reservation, None)
            return snapshot_error("DIFF_SNAPSHOT_CAPTURE_ERROR")
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
            remaining = (
                state.snapshot.created_monotonic + HARD_LIFETIME_SECONDS - self._clock()
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
        with self._lock:
            self._sweep()
            current = self._states.get(snapshot_id)
            remaining = (
                state.snapshot.created_monotonic + HARD_LIFETIME_SECONDS - self._clock()
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
        self, consumer: SnapshotConsumer, paths: list[str]
    ) -> str | None:
        try:
            normalized = normalize_bounded_paths(
                paths,
                count_limit=MAX_SCOPE_PATHS,
                path_limit=MAX_PATH_BYTES,
                storage_limit=MAX_SCOPE_BYTES,
            )
        except SourceOracleError as exc:
            return str(exc)
        with self._lock:
            self._sweep()
            snapshot = consumer._snapshot
            state = self._states.get(snapshot.snapshot_id) if snapshot else None
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
            old_paths_size = path_collection_storage(
                state.snapshot.assessed_scope_paths
            )
            delta = path_collection_storage(normalized) - old_paths_size
            if (
                self._charged_bytes + sum(self._reservations.values()) + delta
                > MAX_MATERIALIZED_BYTES
            ):
                return "DIFF_SNAPSHOT_CAPACITY"
            updated = replace(
                state.snapshot,
                assessed_scope_paths=normalized,
                _assessed_scope_raw_paths=tuple(
                    path_to_raw(path) for path in normalized
                ),
                materialized_bytes=state.snapshot.materialized_bytes + delta,
            )
            state.snapshot = updated
            consumer._snapshot = updated
            self._charged_bytes += delta
        return None
    def validate_publish(
        self,
        consumer: SnapshotConsumer,
        publish_guard: Callable[[], str | None] | None = None,
    ) -> str | None:
        """Revalidate the snapshot and an optional response guard in one publish window."""
        with self._lock:
            self._sweep()
            snapshot = consumer._snapshot
            state = self._states.get(snapshot.snapshot_id) if snapshot else None
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
        with self._lock:
            state = self._states.get(snapshot.snapshot_id)
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
    verify = validate_publish
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
        lengths_valid = len(sid) == 35 and len(lease) == 46
        ids_valid = _SNAPSHOT_ID_PATTERN.fullmatch(
            sid
        ) and _ROUTE_LEASE_PATTERN.fullmatch(lease)
        if not lengths_valid or not ids_valid:
            return "DIFF_SNAPSHOT_LEASE_MISMATCH"
        with self._lock:
            self._sweep()
            expected = route_lease(self._lease_key, sid)
            if not hmac.compare_digest(expected, lease):
                return "DIFF_SNAPSHOT_LEASE_MISMATCH"
            state = self._states.get(sid)
            if state is None:
                return None
            state.lease_open = False
            state.expired = True
            self._expiry.cancel(sid)
            if not state.pins:
                self._erase(sid)
            return None
    def close_lease(self, sid: str, lease: str) -> bool:
        return self.release_route_lease(sid, lease) is None
    def reset(self) -> None:
        with self._lock:
            if any(state.pins for state in self._states.values()):
                raise RuntimeError("DIFF_SNAPSHOT_CONSUMERS_ACTIVE")
            self._expiry.cancel_all()
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
# fmt: on
