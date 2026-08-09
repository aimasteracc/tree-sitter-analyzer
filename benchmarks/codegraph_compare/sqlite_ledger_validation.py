"""Startup validation for NO1-008A durable SQLite ledgers."""

from __future__ import annotations

from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.receipt_v3 import (
    canonical_json_bytes,
    strict_json_loads,
)

GENESIS = "0" * 64
DECISION_RECEIPT_DOMAIN = b"NO1-008A-DECISION-RECEIPT-V1\0"
VERDICT_DOMAIN = b"NO1-008A-EXTERNAL-VERIFIER-VERDICT-V2\0"
LEDGER_DOMAIN = b"NO1-008A-EXTERNAL-VERIFIER-LEDGER-V1\0"
EVENTS = frozenset({"CHALLENGED", "VERIFYING", "CONSUMED", "FAILED"})
_HEX = frozenset("0123456789abcdef")


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        raise ValueError(f"{label} invalid")
    return value


def _validate_verifier_envelope(
    envelope: Any,
    *,
    challenge: str,
    manifest: str,
    histories: dict[str, list[tuple[str, str, int, int]]],
    db: Any,
    config: Any,
    service_identity: Any,
    public: Ed25519PublicKey,
) -> None:
    """Authenticate every persisted exact-14 verdict binding at startup."""
    required = {
        "manifest_sha256",
        "decision_id",
        "decision_contract_sha256",
        "challenge",
        "ledger_counter",
        "ledger_prev_hash",
        "issued_at_ns",
        "verdict",
        "service_identity",
        "consumption_record",
        "ledger_head",
        "key_id",
        "algorithm",
        "signature",
    }
    role = config["verifier"]
    if (
        type(envelope) is not dict
        or set(envelope) != required
        or envelope["manifest_sha256"] != manifest
        or envelope["challenge"] != challenge
        or envelope["key_id"] != role["key_id"]
        or envelope["algorithm"] != "Ed25519"
        or envelope["service_identity"] != service_identity
    ):
        raise ValueError("persisted verifier envelope binding invalid")
    _hex64(envelope["decision_id"], "persisted decision id")
    _hex64(envelope["decision_contract_sha256"], "persisted decision contract digest")
    _hex64(envelope["ledger_prev_hash"], "persisted ledger previous hash")
    signed = {
        key: envelope[key] for key in required - {"key_id", "algorithm", "signature"}
    }
    public.verify(
        bytes.fromhex(envelope["signature"]),
        VERDICT_DOMAIN + canonical_json_bytes(signed),
    )
    consumption = envelope["consumption_record"]
    head = envelope["ledger_head"]
    for retained in (consumption, head):
        if (
            type(retained) is not dict
            or set(retained) != {"record", "key_id", "algorithm", "signature"}
            or retained["key_id"] != role["key_id"]
            or retained["algorithm"] != "Ed25519"
        ):
            raise ValueError("persisted signed ledger proof invalid")
        public.verify(
            bytes.fromhex(retained["signature"]),
            LEDGER_DOMAIN + canonical_json_bytes(retained["record"]),
        )
    record = consumption["record"]
    row = db.execute(
        "SELECT counter,event,challenge,manifest_sha256,issued_at_ns,event_at_ns,"
        "prev_hash,record_hash FROM events WHERE challenge=? AND event='CONSUMED'",
        (challenge,),
    ).fetchone()
    row_keys = (
        "counter",
        "event",
        "challenge",
        "manifest_sha256",
        "issued_at_ns",
        "event_at_ns",
        "prev_hash",
        "record_hash",
    )
    durable_record = dict(zip(row_keys, row, strict=True)) if row is not None else None
    if durable_record is None:
        raise ValueError("persisted verifier consumed event missing")
    durable_head = {
        "counter": durable_record["counter"],
        "record_hash": durable_record["record_hash"],
    }
    if (
        record != durable_record
        or head["record"] != durable_head
        or envelope["ledger_counter"] != durable_record["counter"]
        or envelope["ledger_prev_hash"] != durable_record["prev_hash"]
        or envelope["issued_at_ns"] != histories[challenge][0][2]
    ):
        raise ValueError("persisted verifier ledger binding invalid")
    from benchmarks.codegraph_compare.verifier_aggregate import _validate_verdict_schema

    _validate_verdict_schema(envelope["verdict"])


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
        verification = getattr(owner, "verification_config", None)
        service_identity = getattr(owner, "service_identity", None)
        public = None
        if verification is not None:
            try:
                role = verification["verifier"]
                configured_identity = verification["trusted"]["verifier_runtime"][
                    "measurement"
                ]
                if service_identity != configured_identity:
                    raise ValueError("verifier ledger runtime configuration mismatch")
                public = Ed25519PublicKey.from_public_bytes(
                    bytes.fromhex(role["public_key_hex"])
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    "verifier ledger verification config invalid"
                ) from error
        for challenge, manifest, envelope in verdicts:
            if (
                challenge in verdict_challenges
                or states.get(challenge) != ("CONSUMED", manifest)
                or type(envelope) is not bytes
            ):
                raise ValueError("challenge ledger verdict state mismatch")
            if public is not None:
                try:
                    parsed = strict_json_loads(envelope)
                    if canonical_json_bytes(parsed) != envelope:
                        raise ValueError("persisted verifier envelope is not canonical")
                    _validate_verifier_envelope(
                        parsed,
                        challenge=challenge,
                        manifest=manifest,
                        histories=histories,
                        db=db,
                        config=verification,
                        service_identity=service_identity,
                        public=public,
                    )
                except Exception as error:
                    raise ValueError(
                        "persisted verifier envelope authentication failed"
                    ) from error
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
                or body["consumed_at_ns"] != consumed_at
                or body["service_identity"]
                != owner._decision_config["trusted"]["decision_consumer_runtime"][
                    "measurement"
                ]
                or receipt["algorithm"] != "Ed25519"
                or receipt["key_id"]
                != owner._decision_config["decision_consumer"]["key_id"]
                or type(receipt["signature"]) is not str
                or len(receipt["signature"]) != 128
            ):
                raise ValueError("stored decision receipt does not match ledger row")
            _hex64(body["decision_contract_sha256"], "stored decision digest")
            try:
                signature = bytes.fromhex(receipt["signature"])
                public = bytes.fromhex(
                    owner._decision_config["decision_consumer"]["public_key_hex"]
                )
                Ed25519PublicKey.from_public_bytes(public).verify(
                    signature,
                    DECISION_RECEIPT_DOMAIN + canonical_json_bytes(body),
                )
            except (TypeError, ValueError) as error:
                raise ValueError("stored decision receipt signature invalid") from error
            except Exception as error:
                raise ValueError("stored decision receipt signature invalid") from error
    finally:
        db.close()
