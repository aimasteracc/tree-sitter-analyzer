"""Thread-owned consumers for process-local frozen diff snapshots."""

from __future__ import annotations

import base64
import hashlib
import hmac
import threading
from dataclasses import dataclass
from typing import Any

from .diff_snapshot_capture import FrozenFile
from .git_path_codec import path_from_wire, path_to_raw
from .source_oracle import RootIdentity, SourceOracleError


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
        raw = path_to_raw(normalized)
        return next((item for item in self.files if item.record.raw_path == raw), None)


class SnapshotConsumer:
    """Thread-owned snapshot pin; release is idempotent and synchronized."""

    def __init__(self, registry: Any, snapshot: FrozenDiffSnapshot, pin: str) -> None:
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


def snapshot_error(code: str) -> dict[str, object]:
    return {"success": False, "error_code": code}


def route_lease(key: bytes, snapshot_id: str) -> str:
    digest = hmac.new(key, snapshot_id.encode("ascii"), hashlib.sha256).digest()
    return "dl_" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
