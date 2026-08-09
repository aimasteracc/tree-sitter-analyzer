"""Durable root-owned one-use verifier challenge hash-chain ledger."""

from __future__ import annotations

import fcntl
import hashlib
import os
import secrets
import stat
import threading
import time
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

GENESIS = "0" * 64


class ChallengeLedger:
    def __init__(self, path: Path):
        self.path = path
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
        self._read_locked(validate_only=True)

    def close(self) -> None:
        os.close(self.fd)

    def _read_locked(
        self, *, validate_only: bool = False
    ) -> tuple[list[dict[str, Any]], str]:
        os.lseek(self.fd, 0, os.SEEK_SET)
        raw = bytearray()
        while chunk := os.read(self.fd, 1024 * 1024):
            raw.extend(chunk)
            if len(raw) > 64 * 1024 * 1024:
                raise ValueError("challenge ledger exceeds bound")
        records: list[dict[str, Any]] = []
        previous = GENESIS
        for ordinal, line in enumerate(bytes(raw).splitlines(), 1):
            item = strict_json_loads(line)
            keys = {
                "counter",
                "event",
                "challenge",
                "manifest_sha256",
                "issued_at_ns",
                "prev_hash",
                "record_hash",
            }
            if (
                type(item) is not dict
                or set(item) != keys
                or item["counter"] != ordinal
                or item["prev_hash"] != previous
                or item["event"] not in {"ISSUED", "CONSUMED"}
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
        return records, previous

    def _append(self, item: dict[str, Any]) -> dict[str, Any]:
        item["record_hash"] = hashlib.sha256(canonical_json_bytes(item)).hexdigest()
        os.write(self.fd, canonical_json_bytes(item) + b"\n")
        os.fsync(self.fd)
        return item

    def begin(self, manifest_sha256: str) -> dict[str, Any]:
        with self._lock:
            fcntl.flock(self.fd, fcntl.LOCK_EX)
            try:
                records, previous = self._read_locked()
                used = {item["challenge"] for item in records}
                challenge = secrets.token_hex(32)
                while challenge in used:
                    challenge = secrets.token_hex(32)
                item = {
                    "counter": len(records) + 1,
                    "event": "ISSUED",
                    "challenge": challenge,
                    "manifest_sha256": manifest_sha256,
                    "issued_at_ns": time.time_ns(),
                    "prev_hash": previous,
                }
                return self._append(item)
            finally:
                fcntl.flock(self.fd, fcntl.LOCK_UN)

    def consume(self, manifest_sha256: str, challenge: str) -> dict[str, Any]:
        with self._lock:
            fcntl.flock(self.fd, fcntl.LOCK_EX)
            try:
                records, previous = self._read_locked()
                issued = [
                    item
                    for item in records
                    if item["event"] == "ISSUED" and item["challenge"] == challenge
                ]
                consumed = any(
                    item["event"] == "CONSUMED" and item["challenge"] == challenge
                    for item in records
                )
                if (
                    len(issued) != 1
                    or consumed
                    or issued[0]["manifest_sha256"] != manifest_sha256
                ):
                    raise ValueError(
                        "verifier challenge is absent, mismatched, or already consumed"
                    )
                item = {
                    "counter": len(records) + 1,
                    "event": "CONSUMED",
                    "challenge": challenge,
                    "manifest_sha256": manifest_sha256,
                    "issued_at_ns": issued[0]["issued_at_ns"],
                    "prev_hash": previous,
                }
                self._append(item)
                return issued[0]
            finally:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
