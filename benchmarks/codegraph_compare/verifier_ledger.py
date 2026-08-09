"""Crash-safe root-owned one-use verifier challenge hash-chain ledger."""

from __future__ import annotations

import fcntl
import hashlib
import os
import secrets
import stat
import struct
import threading
import time
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

GENESIS = "0" * 64
MAX_LEDGER_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 64 * 1024
EVENTS = frozenset({"CHALLENGED", "VERIFYING", "CONSUMED", "FAILED"})


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short ledger write")
        view = view[written:]


class ChallengeLedger:
    """A process/thread serialized state machine with durable framed records."""

    def __init__(self, path: Path, *, challenge_quota: int = 1024):
        self.path = path
        self.challenge_quota = challenge_quota
        self._lock = threading.Lock()
        parent = path.parent.resolve(strict=True)
        metadata = os.stat(parent)
        if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
            raise ValueError("challenge ledger directory must be root-controlled")
        self.fd = os.open(
            path,
            os.O_RDWR
            | os.O_APPEND
            | os.O_CREAT
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        info = os.fstat(self.fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            os.close(self.fd)
            raise ValueError("challenge ledger must be root-owned 0600 regular file")
        try:
            with self._exclusive():
                records, _previous = self._read_locked()
                states = {record["challenge"]: record for record in records}
                # A process crash can strand VERIFYING; restart closes it fail-safe.
                for challenge, record in list(states.items()):
                    if record["event"] == "VERIFYING":
                        self._transition(record["manifest_sha256"], challenge, "FAILED")
        except Exception:
            os.close(self.fd)
            raise

    class _Guard:
        def __init__(self, owner: ChallengeLedger):
            self.owner = owner

        def __enter__(self) -> None:
            self.owner._lock.acquire()
            fcntl.flock(self.owner.fd, fcntl.LOCK_EX)

        def __exit__(self, *_: object) -> None:
            fcntl.flock(self.owner.fd, fcntl.LOCK_UN)
            self.owner._lock.release()

    def _exclusive(self) -> ChallengeLedger._Guard:
        return self._Guard(self)

    def close(self) -> None:
        os.close(self.fd)

    def _read_locked(self) -> tuple[list[dict[str, Any]], str]:
        size = os.fstat(self.fd).st_size
        if size > MAX_LEDGER_BYTES:
            raise ValueError("challenge ledger exceeds bound")
        raw = os.pread(self.fd, size, 0)
        if len(raw) != size:
            raise ValueError("challenge ledger changed during read")
        records: list[dict[str, Any]] = []
        offset, previous = 0, GENESIS
        while offset < len(raw):
            if len(raw) - offset < 4:
                raise ValueError("challenge ledger has partial record header")
            length = struct.unpack("!I", raw[offset : offset + 4])[0]
            offset += 4
            if length < 2 or length > MAX_RECORD_BYTES or len(raw) - offset < length:
                raise ValueError("challenge ledger has partial or invalid record")
            payload = raw[offset : offset + length]
            offset += length
            item = strict_json_loads(payload)
            keys = {
                "counter",
                "event",
                "challenge",
                "manifest_sha256",
                "issued_at_ns",
                "event_at_ns",
                "prev_hash",
                "record_hash",
            }
            if (
                type(item) is not dict
                or set(item) != keys
                or canonical_json_bytes(item) != payload
                or item["counter"] != len(records) + 1
                or item["prev_hash"] != previous
                or item["event"] not in EVENTS
            ):
                raise ValueError("challenge ledger chain is invalid")
            unsigned = {
                key: value for key, value in item.items() if key != "record_hash"
            }
            digest = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
            if digest != item["record_hash"]:
                raise ValueError("challenge ledger record hash mismatch")
            previous = digest
            records.append(item)
        self._validate_transitions(records)
        return records, previous

    @staticmethod
    def _validate_transitions(records: list[dict[str, Any]]) -> None:
        states: dict[str, str] = {}
        for item in records:
            old = states.get(item["challenge"])
            allowed = {
                None: "CHALLENGED",
                "CHALLENGED": "VERIFYING",
                "VERIFYING": item["event"],
            }
            if (
                old not in allowed
                or item["event"] != allowed[old]
                or (old == "VERIFYING" and item["event"] not in {"CONSUMED", "FAILED"})
            ):
                raise ValueError("challenge ledger state transition is invalid")
            states[item["challenge"]] = item["event"]

    def _append(self, item: dict[str, Any]) -> dict[str, Any]:
        item["record_hash"] = hashlib.sha256(canonical_json_bytes(item)).hexdigest()
        payload = canonical_json_bytes(item)
        _write_all(self.fd, struct.pack("!I", len(payload)) + payload)
        os.fsync(self.fd)
        parent_fd = os.open(
            self.path.parent, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return dict(item)

    def _transition(
        self, manifest_sha256: str, challenge: str, event: str
    ) -> dict[str, Any]:
        records, previous = self._read_locked()
        related = [r for r in records if r["challenge"] == challenge]
        expected = {
            "VERIFYING": "CHALLENGED",
            "CONSUMED": "VERIFYING",
            "FAILED": "VERIFYING",
        }[event]
        if (
            not related
            or related[-1]["event"] != expected
            or related[0]["manifest_sha256"] != manifest_sha256
        ):
            raise ValueError(
                "verifier challenge is absent, mismatched, or in terminal state"
            )
        issued = related[0]
        return self._append(
            {
                "counter": len(records) + 1,
                "event": event,
                "challenge": challenge,
                "manifest_sha256": manifest_sha256,
                "issued_at_ns": issued["issued_at_ns"],
                "event_at_ns": time.time_ns(),
                "prev_hash": previous,
            }
        )

    def begin(self, manifest_sha256: str) -> dict[str, Any]:
        with self._exclusive():
            records, previous = self._read_locked()
            active = {r["challenge"] for r in records if r["event"] == "CHALLENGED"} - {
                r["challenge"]
                for r in records
                if r["event"] in {"VERIFYING", "CONSUMED", "FAILED"}
            }
            if len(active) >= self.challenge_quota:
                raise RuntimeError("outstanding challenge quota exceeded")
            used = {r["challenge"] for r in records}
            challenge = secrets.token_hex(32)
            while challenge in used:
                challenge = secrets.token_hex(32)
            now = time.time_ns()
            return self._append(
                {
                    "counter": len(records) + 1,
                    "event": "CHALLENGED",
                    "challenge": challenge,
                    "manifest_sha256": manifest_sha256,
                    "issued_at_ns": now,
                    "event_at_ns": now,
                    "prev_hash": previous,
                }
            )

    def start_verifying(self, manifest_sha256: str, challenge: str) -> dict[str, Any]:
        with self._exclusive():
            return self._transition(manifest_sha256, challenge, "VERIFYING")

    def finish(
        self, manifest_sha256: str, challenge: str, *, success: bool
    ) -> dict[str, Any]:
        record, _head = self.finish_with_head(
            manifest_sha256, challenge, success=success
        )
        return record

    def finish_with_head(
        self, manifest_sha256: str, challenge: str, *, success: bool
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._exclusive():
            record = self._transition(
                manifest_sha256, challenge, "CONSUMED" if success else "FAILED"
            )
            return record, {
                "counter": record["counter"],
                "record_hash": record["record_hash"],
            }

    def head(self) -> dict[str, Any]:
        with self._exclusive():
            records, digest = self._read_locked()
            return {"counter": len(records), "record_hash": digest}

    def consume(self, manifest_sha256: str, challenge: str) -> dict[str, Any]:
        self.start_verifying(manifest_sha256, challenge)
        return self.finish(manifest_sha256, challenge, success=True)
