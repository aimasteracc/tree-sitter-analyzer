"""Startup validation for NO1-008A durable SQLite ledgers."""

from __future__ import annotations

from typing import Any

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

GENESIS = "0" * 64
EVENTS = frozenset({"CHALLENGED", "VERIFYING", "CONSUMED", "FAILED"})
_HEX = frozenset("0123456789abcdef")


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        raise ValueError(f"{label} invalid")
    return value


def validate_challenge_ledger(owner: Any) -> None:
    """Recompute the durable chain and materialized challenge state."""
    db = owner._connection()
    try:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("challenge ledger SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall() != []:
            raise ValueError("challenge ledger foreign key check failed")
        meta_rows = db.execute(
            "SELECT counter,head_hash,lease_pid,lease_start FROM meta WHERE singleton=1"
        ).fetchall()
        if len(meta_rows) != 1:
            raise ValueError("challenge ledger meta row invalid")
        meta_counter, meta_head, lease_pid, lease_start = meta_rows[0]
        if (lease_pid is None) != (lease_start is None):
            raise ValueError("challenge ledger lease metadata invalid")

        histories: dict[str, list[tuple[str, str, int, int]]] = {}
        expected_counter = 0
        previous = GENESIS
        events = db.execute(
            "SELECT counter,event,challenge,manifest_sha256,issued_at_ns,"
            "event_at_ns,prev_hash,record_hash FROM events ORDER BY counter"
        ).fetchall()
        for row in events:
            counter, event, challenge, manifest, issued, event_at, prev, stored = row
            if type(counter) is not int or counter != expected_counter + 1:
                raise ValueError("challenge ledger event counter discontinuity")
            if event not in EVENTS or not all(
                type(value) is str
                and len(value) == 64
                and all(character in _HEX for character in value)
                for value in (challenge, manifest, prev, stored)
            ):
                raise ValueError("challenge ledger event record invalid")
            if (
                type(issued) is not int
                or type(event_at) is not int
                or event_at < issued
            ):
                raise ValueError("challenge ledger event timestamp invalid")
            if prev != previous:
                raise ValueError("challenge ledger previous hash mismatch")
            recomputed = owner._record(
                counter, event, challenge, manifest, issued, event_at, prev
            )["record_hash"]
            if stored != recomputed:
                raise ValueError("challenge ledger record hash mismatch")
            history = histories.setdefault(challenge, [])
            if history:
                prior_event, prior_manifest, prior_issued, _prior_counter = history[-1]
                allowed = (
                    prior_event == "CHALLENGED" and event in {"VERIFYING", "FAILED"}
                ) or (prior_event == "VERIFYING" and event in {"CONSUMED", "FAILED"})
                if not allowed or manifest != prior_manifest or issued != prior_issued:
                    raise ValueError("challenge ledger event transition invalid")
            elif event != "CHALLENGED":
                raise ValueError("challenge ledger history does not begin challenged")
            history.append((event, manifest, issued, counter))
            expected_counter = counter
            previous = stored

        if (
            type(meta_counter) is not int
            or meta_counter != expected_counter
            or meta_head != previous
        ):
            raise ValueError("challenge ledger meta head mismatch")

        challenges = db.execute(
            "SELECT challenge,manifest_sha256,state,issued_at_ns,expires_at_ns,"
            "last_counter FROM challenges"
        ).fetchall()
        seen: set[str] = set()
        states: dict[str, tuple[str, str]] = {}
        for challenge, manifest, state, issued, expires, last_counter in challenges:
            challenge_history = histories.get(challenge)
            if (
                challenge in seen
                or challenge_history is None
                or type(expires) is not int
                or expires <= issued
            ):
                raise ValueError("challenge ledger materialized challenge invalid")
            latest_event, latest_manifest, latest_issued, latest_counter = (
                challenge_history[-1]
            )
            if (
                manifest != latest_manifest
                or issued != latest_issued
                or state != latest_event
                or last_counter != latest_counter
            ):
                raise ValueError("challenge ledger materialized state mismatch")
            seen.add(challenge)
            states[challenge] = (state, manifest)
        if seen != set(histories):
            raise ValueError("challenge ledger event lacks materialized challenge")

        verdicts = db.execute(
            "SELECT challenge,manifest_sha256,envelope FROM verdicts"
        ).fetchall()
        verdict_challenges = set()
        for challenge, manifest, envelope in verdicts:
            if (
                challenge in verdict_challenges
                or states.get(challenge) != ("CONSUMED", manifest)
                or type(envelope) is not bytes
            ):
                raise ValueError("challenge ledger verdict state mismatch")
            verdict_challenges.add(challenge)
        consumed = {
            challenge
            for challenge, (state, _manifest) in states.items()
            if state == "CONSUMED"
        }
        if verdict_challenges != consumed:
            raise ValueError("challenge ledger consumed verdict missing")
    finally:
        db.close()


def validate_decision_ledger(owner: Any) -> None:
    """Fail closed on corrupted durable decisions before the service listens."""
    db = owner._connect()
    try:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("decision ledger SQLite integrity check failed")
        rows = db.execute(
            "SELECT decision_id,decision_nonce,manifest_sha256,"
            "consumed_at_ns,receipt_json FROM consumed"
        ).fetchall()
        for decision_id, nonce, manifest, consumed_at, raw_receipt in rows:
            _hex64(decision_id, "stored decision id")
            _hex64(nonce, "stored decision nonce")
            _hex64(manifest, "stored decision manifest")
            if type(consumed_at) is not int or consumed_at < 1:
                raise ValueError("stored decision timestamp invalid")
            if type(raw_receipt) is not bytes:
                raise ValueError("stored decision receipt is not canonical bytes")
            receipt = strict_json_loads(raw_receipt)
            if canonical_json_bytes(receipt) != raw_receipt:
                raise ValueError("stored decision receipt is not canonical")
            if type(receipt) is not dict or set(receipt) != {
                "receipt",
                "key_id",
                "algorithm",
                "signature",
            }:
                raise ValueError("stored decision receipt envelope invalid")
            body = receipt["receipt"]
            if (
                type(body) is not dict
                or set(body)
                != {
                    "schema_version",
                    "decision_id",
                    "decision_contract_sha256",
                    "manifest_sha256",
                    "verdict_status",
                    "consumed_at_ns",
                    "service_identity",
                }
                or body["schema_version"] != 1
                or body["decision_id"] != decision_id
                or body["manifest_sha256"] != manifest
                or body["verdict_status"] != "SETUP_QUALIFIED"
                or type(body["consumed_at_ns"]) is not int
                or type(body["service_identity"]) is not dict
                or receipt["algorithm"] != "Ed25519"
                or type(receipt["key_id"]) is not str
                or type(receipt["signature"]) is not str
                or len(receipt["signature"]) != 128
            ):
                raise ValueError("stored decision receipt does not match ledger row")
            _hex64(body["decision_contract_sha256"], "stored decision digest")
    finally:
        db.close()
