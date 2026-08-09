"""SQLite-backed crash-safe one-use verifier challenge ledger."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import stat
import threading
import time
from pathlib import Path
from types import TracebackType
from typing import Any, cast

from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

GENESIS = "0" * 64
EVENTS = frozenset({"CHALLENGED", "VERIFYING", "CONSUMED", "FAILED"})


class ChallengeLedger:
    """Indexed O(1) challenge state with FULL-durable atomic transitions.

    SQLite supplies recovery from torn writes; WAL permits concurrent head reads.
    The lease row prevents two verifier processes from serving the same ledger.
    """

    def __init__(
        self,
        path: Path,
        *,
        challenge_quota: int = 1024,
        total_quota: int = 1_000_000,
        challenge_ttl_seconds: int = 900,
    ):
        self.path = path
        self.challenge_quota = challenge_quota
        self.total_quota = total_quota
        self.challenge_ttl_ns = challenge_ttl_seconds * 1_000_000_000
        self._local = threading.local()
        service_uid = os.geteuid()
        parent = path.parent.resolve(strict=True)
        metadata = os.stat(parent)
        if metadata.st_uid != service_uid or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError(
                "challenge ledger directory must be service-owned and private"
            )
        try:
            db = self._connection()
            try:
                db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    counter INTEGER NOT NULL, head_hash TEXT NOT NULL,
                    lease_pid INTEGER, lease_start TEXT);
                INSERT OR IGNORE INTO meta VALUES(1,0,printf('%064d',0),NULL,NULL);
                CREATE TABLE IF NOT EXISTS challenges (
                    challenge TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL, issued_at_ns INTEGER NOT NULL,
                    expires_at_ns INTEGER NOT NULL, last_counter INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS challenges_state_expiry
                    ON challenges(state, expires_at_ns);
                CREATE TABLE IF NOT EXISTS events (
                    counter INTEGER PRIMARY KEY, event TEXT NOT NULL,
                    challenge TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
                    issued_at_ns INTEGER NOT NULL, event_at_ns INTEGER NOT NULL,
                    prev_hash TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE);
                """)
            finally:
                db.close()
            os.chmod(path, 0o600)
            info = os.stat(path, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != service_uid
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise ValueError(
                    "challenge ledger must be service-owned 0600 regular file"
                )
            self._acquire_lease()
            with self._transaction():
                rows = self.db.execute(
                    "SELECT challenge,manifest_sha256 FROM challenges WHERE state='VERIFYING'"
                ).fetchall()
                for challenge, manifest in rows:
                    self._transition_locked(manifest, challenge, "FAILED")
        except BaseException:
            raise

    def _connection(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @property
    def db(self) -> sqlite3.Connection:
        db = getattr(self._local, "db", None)
        if db is None:
            raise RuntimeError("ledger database access requires a transaction")
        return cast(sqlite3.Connection, db)

    class _Transaction:
        def __init__(self, owner: ChallengeLedger):
            self.owner = owner

        def __enter__(self) -> ChallengeLedger._Transaction:
            if getattr(self.owner._local, "db", None) is not None:
                raise RuntimeError("nested ledger transaction")
            db = self.owner._connection()
            self.owner._local.db = db
            db.execute("BEGIN IMMEDIATE")
            return self

        def __exit__(
            self,
            typ: type[BaseException] | None,
            value: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            db = self.owner.db
            try:
                db.execute("ROLLBACK" if typ else "COMMIT")
            finally:
                del self.owner._local.db
                db.close()

    def _transaction(self) -> ChallengeLedger._Transaction:
        return self._Transaction(self)

    def _acquire_lease(self) -> None:
        start = Path("/proc/self/stat").read_text(encoding="ascii").split()[21]
        with self._transaction():
            pid, old_start = self.db.execute(
                "SELECT lease_pid,lease_start FROM meta WHERE singleton=1"
            ).fetchone()
            if pid is not None:
                try:
                    live = (
                        Path(f"/proc/{pid}/stat")
                        .read_text(encoding="ascii")
                        .split()[21]
                        == old_start
                    )
                except (FileNotFoundError, ProcessLookupError):
                    live = False
                if live:
                    raise RuntimeError(
                        "challenge ledger already has a live singleton lease"
                    )
            self.db.execute(
                "UPDATE meta SET lease_pid=?,lease_start=? WHERE singleton=1",
                (os.getpid(), start),
            )

    def close(self) -> None:
        with self._transaction():
            start = Path("/proc/self/stat").read_text(encoding="ascii").split()[21]
            self.db.execute(
                "UPDATE meta SET lease_pid=NULL,lease_start=NULL WHERE singleton=1 AND lease_pid=? AND lease_start=?",
                (os.getpid(), start),
            )

    @staticmethod
    def _record(
        counter: int,
        event: str,
        challenge: str,
        manifest: str,
        issued: int,
        now: int,
        previous: str,
    ) -> dict[str, Any]:
        item = {
            "counter": counter,
            "event": event,
            "challenge": challenge,
            "manifest_sha256": manifest,
            "issued_at_ns": issued,
            "event_at_ns": now,
            "prev_hash": previous,
        }
        item["record_hash"] = hashlib.sha256(canonical_json_bytes(item)).hexdigest()
        return item

    def _append_locked(
        self, event: str, challenge: str, manifest: str, issued: int
    ) -> dict[str, Any]:
        counter, previous = self.db.execute(
            "SELECT counter,head_hash FROM meta WHERE singleton=1"
        ).fetchone()
        item = self._record(
            counter + 1, event, challenge, manifest, issued, time.time_ns(), previous
        )
        self.db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
            tuple(
                item[k]
                for k in (
                    "counter",
                    "event",
                    "challenge",
                    "manifest_sha256",
                    "issued_at_ns",
                    "event_at_ns",
                    "prev_hash",
                    "record_hash",
                )
            ),
        )
        self.db.execute(
            "UPDATE meta SET counter=?,head_hash=? WHERE singleton=1",
            (item["counter"], item["record_hash"]),
        )
        return item

    def _expire_locked(self, now: int) -> None:
        rows = self.db.execute(
            "SELECT challenge,manifest_sha256 FROM challenges WHERE state='CHALLENGED' AND expires_at_ns<=?",
            (now,),
        ).fetchall()
        for challenge, manifest in rows:
            item = self._append_locked(
                "FAILED",
                challenge,
                manifest,
                self.db.execute(
                    "SELECT issued_at_ns FROM challenges WHERE challenge=?",
                    (challenge,),
                ).fetchone()[0],
            )
            self.db.execute(
                "UPDATE challenges SET state='FAILED',last_counter=? WHERE challenge=?",
                (item["counter"], challenge),
            )

    def begin(self, manifest_sha256: str) -> dict[str, Any]:
        now = time.time_ns()
        with self._transaction():
            self._expire_locked(now)
            total = self.db.execute("SELECT COUNT(*) FROM challenges").fetchone()[0]
            active = self.db.execute(
                "SELECT COUNT(*) FROM challenges WHERE state='CHALLENGED'"
            ).fetchone()[0]
            if total >= self.total_quota:
                raise RuntimeError("challenge total quota exceeded")
            if active >= self.challenge_quota:
                raise RuntimeError("outstanding challenge quota exceeded")
            challenge = secrets.token_hex(32)
            while self.db.execute(
                "SELECT 1 FROM challenges WHERE challenge=?", (challenge,)
            ).fetchone():
                challenge = secrets.token_hex(32)
            item = self._append_locked("CHALLENGED", challenge, manifest_sha256, now)
            self.db.execute(
                "INSERT INTO challenges VALUES(?,?,?,?,?,?)",
                (
                    challenge,
                    manifest_sha256,
                    "CHALLENGED",
                    now,
                    now + self.challenge_ttl_ns,
                    item["counter"],
                ),
            )
            return item

    def _transition_locked(
        self, manifest: str, challenge: str, event: str
    ) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT manifest_sha256,state,issued_at_ns,expires_at_ns FROM challenges WHERE challenge=?",
            (challenge,),
        ).fetchone()
        expected = {
            "VERIFYING": "CHALLENGED",
            "CONSUMED": "VERIFYING",
            "FAILED": "VERIFYING",
        }[event]
        if not row or row[0] != manifest or row[1] != expected:
            raise ValueError(
                "verifier challenge is absent, mismatched, or in terminal state"
            )
        if event == "VERIFYING" and row[3] <= time.time_ns():
            failed = self._append_locked("FAILED", challenge, manifest, row[2])
            self.db.execute(
                "UPDATE challenges SET state='FAILED',last_counter=? WHERE challenge=?",
                (failed["counter"], challenge),
            )
            raise TimeoutError("verifier challenge expired")
        item = self._append_locked(event, challenge, manifest, row[2])
        self.db.execute(
            "UPDATE challenges SET state=?,last_counter=? WHERE challenge=?",
            (event, item["counter"], challenge),
        )
        return item

    def start_verifying(self, manifest_sha256: str, challenge: str) -> dict[str, Any]:
        with self._transaction():
            return self._transition_locked(manifest_sha256, challenge, "VERIFYING")

    def finish(
        self, manifest_sha256: str, challenge: str, *, success: bool
    ) -> dict[str, Any]:
        return self.finish_with_head(manifest_sha256, challenge, success=success)[0]

    def finish_with_head(
        self, manifest_sha256: str, challenge: str, *, success: bool
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._transaction():
            record = self._transition_locked(
                manifest_sha256, challenge, "CONSUMED" if success else "FAILED"
            )
            return record, {
                "counter": record["counter"],
                "record_hash": record["record_hash"],
            }

    def head(self) -> dict[str, Any]:
        with self._transaction():
            row = self.db.execute(
                "SELECT counter,head_hash FROM meta WHERE singleton=1"
            ).fetchone()
            return {"counter": row[0], "record_hash": row[1]}

    def consume(self, manifest_sha256: str, challenge: str) -> dict[str, Any]:
        self.start_verifying(manifest_sha256, challenge)
        return self.finish(manifest_sha256, challenge, success=True)
