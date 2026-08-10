"""In-memory frozen git-diff snapshots for RFC-0022 P0.2.

The registry is deliberately process-local: no serialization, temp files, or
implicit cache is permitted.  Snapshot payloads are immutable; only lease and
consumer counters change under the registry lock.
"""

from __future__ import annotations

import secrets
import subprocess  # nosec B404
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .source_oracle import capture_consistent, source_generation

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

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "path": self.path,
            "status": self.status,
            "old_available": self.old_available,
            "new_available": self.new_available,
            "binary": self.binary,
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
    mode: str
    normalized_patch: bytes
    files: tuple[FrozenFile, ...]
    assessed_scope_paths: tuple[str, ...]
    created_monotonic: float
    materialized_bytes: int

    def file(self, path: str) -> FrozenFile | None:
        normalized = _normalize_path(path)
        return next(
            (item for item in self.files if item.record.path == normalized), None
        )


@dataclass
class _State:
    snapshot: FrozenDiffSnapshot
    route_lease_id: str
    lease_open: bool = True
    consumers: int = 0
    expired: bool = False


class SnapshotConsumer:
    """An acquired consumer pin. Release is idempotent."""

    def __init__(self, registry: DiffSnapshotRegistry, snapshot: FrozenDiffSnapshot):
        self._registry = registry
        self.snapshot = snapshot
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._registry._release(self.snapshot.snapshot_id)

    def __enter__(self) -> FrozenDiffSnapshot:
        return self.snapshot

    def __exit__(self, *_: object) -> None:
        self.release()


def _normalize_path(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _run(root: str, args: list[str]) -> tuple[int, bytes]:
    try:
        result = subprocess.run(  # nosec B603
            ["git", *args], cwd=root, capture_output=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, b""
    return result.returncode, result.stdout


def _git_blob(root: str, spec: str) -> bytes | None:
    rc, data = _run(root, ["show", spec])
    return data if rc == 0 else None


def _worktree_bytes(root: str, path: str) -> bytes | None:
    try:
        return (Path(root) / path).read_bytes()
    except OSError:
        return None


def _name_status(root: str, mode: str) -> list[tuple[str, str | None, str]]:
    args = ["diff", "--name-status", "-z", "--find-renames"]
    if mode == "staged":
        args.insert(1, "--cached")
    rc, raw = _run(root, args)
    if rc != 0:
        return []
    tokens = [x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x]
    rows: list[tuple[str, str | None, str]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if status.startswith(("R", "C")):
            old, new = tokens[index : index + 2]
            index += 2
            rows.append(("R", _normalize_path(old), _normalize_path(new)))
        else:
            path = tokens[index]
            index += 1
            rows.append((status[:1], None, _normalize_path(path)))
    if mode == "diff":
        _, untracked = _run(root, ["ls-files", "--others", "--exclude-standard", "-z"])
        known = {row[2] for row in rows}
        rows.extend(
            ("A", None, p)
            for p in sorted(
                _normalize_path(x.decode("utf-8", "surrogateescape"))
                for x in untracked.split(b"\0")
                if x
            )
            if p not in known
        )
    return sorted(rows, key=lambda row: row[2])


def _capture_payload(root: str, mode: str) -> tuple[bytes, tuple[FrozenFile, ...]]:
    args = ["diff", "--binary", "--no-ext-diff", "--full-index"]
    if mode == "staged":
        args.insert(1, "--cached")
    _, patch = _run(root, args)
    files: list[FrozenFile] = []
    tracked_paths: set[str] = set()
    for status, old_path, path in _name_status(root, mode):
        lookup_old = old_path or path
        if mode == "staged":
            old = _git_blob(root, f"HEAD:{lookup_old}")
            new = _git_blob(root, f":{path}")
        else:
            old = _git_blob(root, f":{lookup_old}")
            new = _worktree_bytes(root, path)
        if status == "A":
            old = None
        if status == "D":
            new = None
        binary = (old is not None and b"\0" in old) or (
            new is not None and b"\0" in new
        )
        record = ChangedFile(
            path, status, old is not None, new is not None, binary, old_path
        )
        files.append(FrozenFile(record, old, new))
        tracked_paths.add(path)
        if mode == "diff" and status == "A":
            header = f"diff --git a/{path} b/{path}\nnew file mode 100644\n".encode()
            if binary:
                patch += (
                    header + f"Binary files /dev/null and b/{path} differ\n".encode()
                )
            else:
                import difflib

                text = (new or b"").decode("utf-8", "replace").splitlines(keepends=True)
                body = "".join(
                    difflib.unified_diff(
                        [], text, fromfile="/dev/null", tofile=f"b/{path}"
                    )
                )
                patch += header + body.encode()
    return patch.replace(b"\r\n", b"\n"), tuple(files)


class DiffSnapshotRegistry:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._states: dict[str, _State] = {}
        self._charged_bytes = 0

    def _sweep(self) -> None:
        now = self._clock()
        for sid, state in list(self._states.items()):
            if now - state.snapshot.created_monotonic >= HARD_LIFETIME_SECONDS:
                state.expired = True
                state.lease_open = False
            if state.expired and state.consumers == 0:
                self._erase(sid)

    def _erase(self, snapshot_id: str) -> None:
        state = self._states.pop(snapshot_id, None)
        if state is not None:
            self._charged_bytes -= state.snapshot.materialized_bytes

    def create(
        self, project_root: str | None, mode: str, assessed_scope_paths: list[str]
    ) -> dict[str, object]:
        if mode not in ("diff", "staged"):
            return {"success": False, "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_MODE"}
        root = str(Path(project_root or ".").resolve())
        generation, payload = capture_consistent(
            root, lambda: _capture_payload(root, mode)
        )
        if generation is None:
            return {"success": False, "error_code": "DIFF_SNAPSHOT_SOURCE_CHANGED"}
        patch, files = payload
        size = len(patch) + sum(
            len(x.old_bytes or b"") + len(x.new_bytes or b"") for x in files
        )
        with self._lock:
            self._sweep()
            if (
                len(self._states) == MAX_SNAPSHOTS
                or self._charged_bytes + size > MAX_MATERIALIZED_BYTES
            ):
                return {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"}
            sid = "ds_" + secrets.token_urlsafe(24)
            lease = "dl_" + secrets.token_urlsafe(24)
            paths = tuple(
                sorted(
                    {_normalize_path(p) for p in assessed_scope_paths}
                    | {x.record.path for x in files}
                )
            )
            snapshot = FrozenDiffSnapshot(
                sid, generation, mode, patch, files, paths, self._clock(), size
            )
            self._states[sid] = _State(snapshot, lease)
            self._charged_bytes += size
        return {
            "success": True,
            "diff_snapshot_id": sid,
            "route_lease_id": lease,
            "source_generation": generation,
            "changed_records": [x.record.to_dict() for x in files],
            "assessed_scope_paths": list(paths),
        }

    def acquire(
        self, snapshot_id: str, project_root: str | None
    ) -> tuple[SnapshotConsumer | None, str | None]:
        with self._lock:
            self._sweep()
            state = self._states.get(snapshot_id)
            if state is None or state.expired or not state.lease_open:
                return None, "DIFF_SNAPSHOT_EXPIRED"
            state.consumers += 1
            consumer = SnapshotConsumer(self, state.snapshot)
        if source_generation(project_root) != consumer.snapshot.source_generation:
            consumer.release()
            return None, "DIFF_SNAPSHOT_SOURCE_CHANGED"
        return consumer, None

    def _release(self, snapshot_id: str) -> None:
        with self._lock:
            state = self._states.get(snapshot_id)
            if state is None:
                return
            state.consumers -= 1
            if state.consumers == 0 and (state.expired or not state.lease_open):
                self._erase(snapshot_id)

    def close_lease(self, snapshot_id: str, route_lease_id: str) -> bool:
        with self._lock:
            self._sweep()
            state = self._states.get(snapshot_id)
            if state is None or state.route_lease_id != route_lease_id:
                return False
            state.lease_open = False
            state.expired = True
            if state.consumers == 0:
                self._erase(snapshot_id)
            return True

    def stats(self) -> tuple[int, int]:
        with self._lock:
            self._sweep()
            return len(self._states), self._charged_bytes


REGISTRY = DiffSnapshotRegistry()


def close_route_lease(diff_snapshot_id: str, route_lease_id: str) -> bool:
    """Orchestration-host hook; Phase A will call this from its finally block."""
    return REGISTRY.close_lease(diff_snapshot_id, route_lease_id)
