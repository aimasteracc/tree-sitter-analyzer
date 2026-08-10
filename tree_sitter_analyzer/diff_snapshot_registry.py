"""Bounded process-local immutable diff snapshot registry (RFC-0022)."""

from __future__ import annotations

import base64
import json
import os
import secrets
import stat
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .source_oracle import (
    RootIdentity,
    SourceOracleError,
    canonical_root,
    git_output,
    normalize_repo_path,
    oracle_generation,
    safe_workspace_path,
)

MAX_SNAPSHOTS = 16
MAX_MATERIALIZED_BYTES = 64 * 1024 * 1024
HARD_LIFETIME_SECONDS = 35.0


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    old_available: bool
    new_available: bool
    binary: bool
    old_path: str | None = None
    patch_available: bool = True

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "path": self.path,
            "status": self.status,
            "old_available": self.old_available,
            "new_available": self.new_available,
            "binary": self.binary,
            "patch_available": self.patch_available,
        }
        if self.old_path is not None:
            value["old_path"] = self.old_path
        return value


@dataclass(frozen=True)
class FrozenFile:
    record: ChangedFile
    old_bytes: bytes | None
    new_bytes: bytes | None


@dataclass(frozen=True)
class FrozenDiffSnapshot:
    snapshot_id: str
    source_generation: str
    root_identity: RootIdentity
    mode: str
    normalized_patch: bytes
    files: tuple[FrozenFile, ...]
    assessed_scope_paths: tuple[str, ...]
    created_monotonic: float
    materialized_bytes: int

    def file(self, path: str) -> FrozenFile | None:
        try:
            normalized = normalize_repo_path(path)
        except SourceOracleError:
            return None
        return next(
            (item for item in self.files if item.record.path == normalized), None
        )


@dataclass
class _State:
    snapshot: FrozenDiffSnapshot
    route_lease_id: str
    lease_open: bool = True
    expired: bool = False
    pins: dict[str, int] = field(default_factory=dict)


class SnapshotConsumer:
    """Thread-owned pin; release is idempotent and synchronized."""

    def __init__(
        self, registry: DiffSnapshotRegistry, snapshot: FrozenDiffSnapshot, pin: str
    ):
        self._registry = registry
        self.snapshot = snapshot
        self._pin = pin
        self._owner = threading.get_ident()
        self._released = False
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            if threading.get_ident() != self._owner:
                raise RuntimeError("DIFF_SNAPSHOT_WRONG_THREAD")
            self._registry._release(self.snapshot.snapshot_id, self._pin, self._owner)
            self._released = True

    def __enter__(self) -> FrozenDiffSnapshot:
        return self.snapshot

    def __exit__(self, *_: object) -> None:
        self.release()


def _rows(
    root: str, mode: str, deadline: float, limit: int
) -> list[tuple[str, str | None, str, bool]]:
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--name-status",
        "-z",
        "--find-renames",
        "--no-ext-diff",
    ]
    raw = git_output(root, args, deadline=deadline, limit=limit)
    tokens = [x for x in raw.split(b"\0") if x]
    result: list[tuple[str, str | None, str, bool]] = []
    index = 0
    while index < len(tokens):
        status_raw = tokens[index]
        index += 1
        status = status_raw[:1].decode("ascii", "strict")
        try:
            if status in ("R", "C"):
                old_raw, path_raw = tokens[index : index + 2]
                index += 2
                old = normalize_repo_path(old_raw.decode("utf-8", "surrogateescape"))
            else:
                path_raw = tokens[index]
                index += 1
                old = None
            path = normalize_repo_path(path_raw.decode("utf-8", "surrogateescape"))
        except (IndexError, UnicodeError) as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        result.append(("R" if status in ("R", "C") else status, old, path, True))
    if mode == "diff":
        raw = git_output(
            root,
            ["ls-files", "--others", "--exclude-standard", "-z"],
            deadline=deadline,
            limit=limit,
        )
        known = {row[2] for row in result}
        for item in raw.split(b"\0"):
            if not item:
                continue
            path = normalize_repo_path(item.decode("utf-8", "surrogateescape"))
            if path not in known:
                result.append(("A", None, path, False))
    return sorted(result, key=lambda row: os.fsencode(row[2]))


def _blob(root: str, spec: str, deadline: float, limit: int) -> bytes:
    return git_output(root, ["show", spec], deadline=deadline, limit=limit)


def _tracked_binary_paths(
    root: str, mode: str, deadline: float, limit: int
) -> set[str]:
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--numstat",
        "-z",
        "--no-ext-diff",
    ]
    raw = git_output(root, args, deadline=deadline, limit=limit)
    binary: set[str] = set()
    for row in raw.split(b"\0"):
        if not row:
            continue
        fields = row.split(b"\t")
        if len(fields) >= 3 and fields[0] == fields[1] == b"-":
            binary.add(
                normalize_repo_path(fields[-1].decode("utf-8", "surrogateescape"))
            )
    return binary


def _untracked_segment(path: str, data: bytes, file_mode: int, binary: bool) -> bytes:
    # Synthetic records are deliberately not represented as fake Git patches.
    record = {
        "binary": binary,
        "content_b64": base64.b64encode(data).decode("ascii"),
        "mode": stat.S_IMODE(file_mode),
        "path_b64": base64.b64encode(os.fsencode(path)).decode("ascii"),
        "type": "tsa-untracked-v1",
    }
    return (
        b"\n"
        + json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        + b"\n"
    )


def _capture_payload(
    root: str, mode: str, deadline: float, ceiling: int
) -> tuple[bytes, tuple[FrozenFile, ...]]:
    remaining = ceiling
    args = (["diff", "--cached"] if mode == "staged" else ["diff-files"]) + [
        "--binary",
        "--full-index",
        "--no-ext-diff",
    ]
    patch = git_output(root, args, deadline=deadline, limit=remaining)
    remaining -= len(patch)
    rows = _rows(root, mode, deadline, min(8 * 1024 * 1024, remaining))
    binaries = _tracked_binary_paths(
        root, mode, deadline, min(8 * 1024 * 1024, remaining)
    )
    files: list[FrozenFile] = []
    additions = bytearray()
    for status, old_path, path, tracked in rows:
        lookup = old_path or path
        old: bytes | None = None
        new: bytes | None = None
        mode_bits = 0
        if status != "A":
            old = _blob(
                root,
                f"HEAD:{lookup}" if mode == "staged" else f":{lookup}",
                deadline,
                remaining,
            )
            remaining -= len(old)
        if status != "D":
            if mode == "staged":
                new = _blob(root, f":{path}", deadline, remaining)
                remaining -= len(new)
            else:
                safe = safe_workspace_path(
                    root, path, deadline=deadline, limit=remaining
                )
                if safe.data is None:
                    raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
                new = safe.data
                remaining -= len(new)
                if safe.metadata:
                    try:
                        mode_bits = int(safe.metadata[-1].split(b",")[2])
                    except (ValueError, IndexError):
                        mode_bits = 0
        binary = path in binaries or (not tracked and new is not None and b"\0" in new)
        record = ChangedFile(
            path, status, old is not None, new is not None, binary, old_path, tracked
        )
        files.append(FrozenFile(record, old, new))
        if not tracked and new is not None:
            segment = _untracked_segment(path, new, mode_bits, binary)
            if len(segment) > remaining:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            additions.extend(segment)
            remaining -= len(segment)
    return patch + bytes(additions), tuple(files)


class DiffSnapshotRegistry:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._states: dict[str, _State] = {}
        self._reservations: dict[str, int] = {}
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

    def create(
        self, project_root: str | None, mode: str, assessed_scope_paths: list[str]
    ) -> dict[str, object]:
        if mode not in ("diff", "staged"):
            return self._error("DIFF_SNAPSHOT_UNSUPPORTED_MODE")
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
            before, before_identity = oracle_generation(root, mode, deadline=deadline)
            if before_identity != identity:
                raise SourceOracleError("DIFF_SNAPSHOT_ROOT_MISMATCH")
            patch, files = _capture_payload(root, mode, deadline, ceiling)
            after, after_identity = oracle_generation(root, mode, deadline=deadline)
            if before != after or identity != after_identity:
                raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            paths = {normalize_repo_path(path) for path in assessed_scope_paths}
            paths.update(item.record.path for item in files)
            size = len(patch) + sum(
                len(item.old_bytes or b"") + len(item.new_bytes or b"")
                for item in files
            )
            if size > ceiling:
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            sid = "ds_" + secrets.token_urlsafe(24)
            lease = "dl_" + secrets.token_urlsafe(24)
            snapshot = FrozenDiffSnapshot(
                sid,
                before,
                identity,
                mode,
                patch,
                files,
                tuple(sorted(paths, key=os.fsencode)),
                started,
                size,
            )
            with self._lock:
                self._reservations.pop(reservation, None)
                self._sweep()
                if self._clock() - started >= HARD_LIFETIME_SECONDS:
                    return self._error("DIFF_SNAPSHOT_TIMEOUT")
                self._states[sid] = _State(snapshot, lease)
                self._charged_bytes += size
            return {
                "success": True,
                "diff_snapshot_id": sid,
                "route_lease_id": lease,
                "source_generation": before,
                "changed_records": [x.record.to_dict() for x in files],
                "assessed_scope_paths": list(snapshot.assessed_scope_paths),
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
        try:
            normalized = tuple(
                sorted({normalize_repo_path(path) for path in paths}, key=os.fsencode)
            )
        except SourceOracleError as exc:
            return str(exc)
        with self._lock:
            state = self._states.get(consumer.snapshot.snapshot_id)
            if state is None or consumer._pin not in state.pins:
                return "DIFF_SNAPSHOT_EXPIRED"
            updated = replace(state.snapshot, assessed_scope_paths=normalized)
            state.snapshot = updated
            consumer.snapshot = updated
        return None

    def verify(self, consumer: SnapshotConsumer) -> str | None:
        try:
            generation, identity = oracle_generation(
                consumer.snapshot.root_identity.realpath, consumer.snapshot.mode
            )
        except SourceOracleError as exc:
            return str(exc)
        if identity != consumer.snapshot.root_identity:
            return "DIFF_SNAPSHOT_ROOT_MISMATCH"
        return (
            None
            if generation == consumer.snapshot.source_generation
            else "DIFF_SNAPSHOT_SOURCE_CHANGED"
        )

    def _release(self, sid: str, pin: str, owner: int) -> None:
        with self._lock:
            state = self._states.get(sid)
            if state is None or state.pins.get(pin) != owner:
                raise RuntimeError("DIFF_SNAPSHOT_PIN_INVALID")
            del state.pins[pin]
            if not state.pins and (state.expired or not state.lease_open):
                self._erase(sid)

    def close_lease(self, sid: str, lease: str) -> bool:
        with self._lock:
            self._sweep()
            state = self._states.get(sid)
            if state is None or state.route_lease_id != lease:
                return False
            state.lease_open = False
            state.expired = True
            if not state.pins:
                self._erase(sid)
            return True

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
