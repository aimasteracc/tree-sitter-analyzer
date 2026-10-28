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

#: The exact-14 field set of a persisted verifier verdict envelope.
_VERDICT_ENVELOPE_KEYS = frozenset(
    {
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
)
_SIGNED_PROOF_KEYS = frozenset({"record", "key_id", "algorithm", "signature"})
_EVENT_ROW_KEYS = (
    "counter",
    "event",
    "challenge",
    "manifest_sha256",
    "issued_at_ns",
    "event_at_ns",
    "prev_hash",
    "record_hash",
)
#: ``prior event -> events allowed to follow it`` in one challenge history.
_EVENT_TRANSITIONS = {
    "CHALLENGED": frozenset({"VERIFYING", "FAILED"}),
    "VERIFYING": frozenset({"CONSUMED", "FAILED"}),
}
_DECISION_RECEIPT_KEYS = frozenset({"receipt", "key_id", "algorithm", "signature"})
_DECISION_BODY_KEYS = frozenset(
    {
        "schema_version",
        "decision_id",
        "decision_contract_sha256",
        "manifest_sha256",
        "verdict_status",
        "consumed_at_ns",
        "service_identity",
    }
)

#: One challenge history entry: ``(event, manifest, issued_at_ns, counter)``.
_History = list[tuple[str, str, int, int]]


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in _HEX for c in value):
        raise ValueError(f"{label} invalid")
    return value


def _is_hex64(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _validate_verifier_envelope(
    envelope: Any,
    *,
    challenge: str,
    manifest: str,
    histories: dict[str, _History],
    db: Any,
    config: Any,
    service_identity: Any,
    public: Ed25519PublicKey,
) -> None:
    """Authenticate every persisted exact-14 verdict binding at startup."""
    role = config["verifier"]
    if (
        type(envelope) is not dict
        or set(envelope) != _VERDICT_ENVELOPE_KEYS
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
        key: envelope[key]
        for key in _VERDICT_ENVELOPE_KEYS - {"key_id", "algorithm", "signature"}
    }
    public.verify(
        bytes.fromhex(envelope["signature"]),
        VERDICT_DOMAIN + canonical_json_bytes(signed),
    )
    consumption = envelope["consumption_record"]
    head = envelope["ledger_head"]
    for retained in (consumption, head):
        _verify_signed_ledger_proof(retained, role, public)
    durable_record = _durable_consumed_record(db, challenge)
    durable_head = {
        "counter": durable_record["counter"],
        "record_hash": durable_record["record_hash"],
    }
    if (
        consumption["record"] != durable_record
        or head["record"] != durable_head
        or envelope["ledger_counter"] != durable_record["counter"]
        or envelope["ledger_prev_hash"] != durable_record["prev_hash"]
        or envelope["issued_at_ns"] != histories[challenge][0][2]
    ):
        raise ValueError("persisted verifier ledger binding invalid")
    from benchmarks.codegraph_compare.verifier_aggregate import _validate_verdict_schema

    _validate_verdict_schema(envelope["verdict"])


def _verify_signed_ledger_proof(
    retained: Any, role: Any, public: Ed25519PublicKey
) -> None:
    """Check one retained signed ledger record's shape and signature."""
    if (
        type(retained) is not dict
        or set(retained) != _SIGNED_PROOF_KEYS
        or retained["key_id"] != role["key_id"]
        or retained["algorithm"] != "Ed25519"
    ):
        raise ValueError("persisted signed ledger proof invalid")
    public.verify(
        bytes.fromhex(retained["signature"]),
        LEDGER_DOMAIN + canonical_json_bytes(retained["record"]),
    )


def _durable_consumed_record(db: Any, challenge: str) -> dict[str, Any]:
    """Return the durable CONSUMED event row for *challenge* as a record."""
    row = db.execute(
        "SELECT counter,event,challenge,manifest_sha256,issued_at_ns,event_at_ns,"
        "prev_hash,record_hash FROM events WHERE challenge=? AND event='CONSUMED'",
        (challenge,),
    ).fetchone()
    if row is None:
        raise ValueError("persisted verifier consumed event missing")
    return dict(zip(_EVENT_ROW_KEYS, row, strict=True))


def validate_challenge_ledger(owner: Any) -> None:
    """Recompute the durable chain and materialized challenge state."""
    db = owner._connection()
    try:
        meta_counter, meta_head = _validate_ledger_meta(db)
        histories, expected_counter, previous = _replay_event_chain(owner, db)
        if (
            type(meta_counter) is not int
            or meta_counter != expected_counter
            or meta_head != previous
        ):
            raise ValueError("challenge ledger meta head mismatch")
        states = _validate_materialized_challenges(db, histories)
        _validate_persisted_verdicts(owner, db, histories, states)
    finally:
        db.close()


def _validate_ledger_meta(db: Any) -> tuple[Any, Any]:
    """Check SQLite integrity and the singleton meta row; return its head."""
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
    return meta_counter, meta_head


def _replay_event_chain(owner: Any, db: Any) -> tuple[dict[str, _History], int, str]:
    """Recompute the hash chain; return ``(histories, last counter, head)``."""
    histories: dict[str, _History] = {}
    expected_counter = 0
    previous = GENESIS
    events = db.execute(
        "SELECT counter,event,challenge,manifest_sha256,issued_at_ns,"
        "event_at_ns,prev_hash,record_hash FROM events ORDER BY counter"
    ).fetchall()
    for row in events:
        counter, event, challenge, manifest, issued, event_at, prev, stored = row
        _validate_event_row(row, expected_counter, previous)
        recomputed = owner._record(
            counter, event, challenge, manifest, issued, event_at, prev
        )["record_hash"]
        if stored != recomputed:
            raise ValueError("challenge ledger record hash mismatch")
        history = histories.setdefault(challenge, [])
        _validate_transition(history, event, manifest, issued)
        history.append((event, manifest, issued, counter))
        expected_counter = counter
        previous = stored
    return histories, expected_counter, previous


def _validate_event_row(row: Any, expected_counter: int, previous: str) -> None:
    """Check one event row's counter, fields, timestamps and chain link."""
    counter, event, challenge, manifest, issued, event_at, prev, stored = row
    if type(counter) is not int or counter != expected_counter + 1:
        raise ValueError("challenge ledger event counter discontinuity")
    if event not in EVENTS or not all(
        _is_hex64(value) for value in (challenge, manifest, prev, stored)
    ):
        raise ValueError("challenge ledger event record invalid")
    if type(issued) is not int or type(event_at) is not int or event_at < issued:
        raise ValueError("challenge ledger event timestamp invalid")
    if prev != previous:
        raise ValueError("challenge ledger previous hash mismatch")


def _validate_transition(
    history: _History, event: str, manifest: str, issued: int
) -> None:
    """Check that *event* may follow the challenge's recorded history."""
    if not history:
        if event != "CHALLENGED":
            raise ValueError("challenge ledger history does not begin challenged")
        return
    prior_event, prior_manifest, prior_issued, _prior_counter = history[-1]
    allowed = event in _EVENT_TRANSITIONS.get(prior_event, frozenset())
    if not allowed or manifest != prior_manifest or issued != prior_issued:
        raise ValueError("challenge ledger event transition invalid")


def _validate_materialized_challenges(
    db: Any, histories: dict[str, _History]
) -> dict[str, tuple[str, str]]:
    """Check each materialized challenge against its replayed history."""
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
    return states


def _verifier_public_key(
    verification: Any, service_identity: Any
) -> Ed25519PublicKey | None:
    """Return the configured verifier key (None when unconfigured)."""
    if verification is None:
        return None
    try:
        role = verification["verifier"]
        configured_identity = verification["trusted"]["verifier_runtime"]["measurement"]
        if service_identity != configured_identity:
            raise ValueError("verifier ledger runtime configuration mismatch")
        return Ed25519PublicKey.from_public_bytes(bytes.fromhex(role["public_key_hex"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("verifier ledger verification config invalid") from error


def _validate_persisted_verdicts(
    owner: Any,
    db: Any,
    histories: dict[str, _History],
    states: dict[str, tuple[str, str]],
) -> None:
    """Check that exactly the consumed challenges carry an authentic verdict."""
    verdicts = db.execute(
        "SELECT challenge,manifest_sha256,envelope FROM verdicts"
    ).fetchall()
    verdict_challenges = set()
    verification = getattr(owner, "verification_config", None)
    service_identity = getattr(owner, "service_identity", None)
    public = _verifier_public_key(verification, service_identity)
    for challenge, manifest, envelope in verdicts:
        if (
            challenge in verdict_challenges
            or states.get(challenge) != ("CONSUMED", manifest)
            or type(envelope) is not bytes
        ):
            raise ValueError("challenge ledger verdict state mismatch")
        if public is not None:
            _authenticate_verdict_envelope(
                envelope,
                challenge=challenge,
                manifest=manifest,
                histories=histories,
                db=db,
                config=verification,
                service_identity=service_identity,
                public=public,
            )
        verdict_challenges.add(challenge)
    consumed = {
        challenge
        for challenge, (state, _manifest) in states.items()
        if state == "CONSUMED"
    }
    if verdict_challenges != consumed:
        raise ValueError("challenge ledger consumed verdict missing")


def _authenticate_verdict_envelope(
    envelope: bytes,
    *,
    challenge: str,
    manifest: str,
    histories: dict[str, _History],
    db: Any,
    config: Any,
    service_identity: Any,
    public: Ed25519PublicKey,
) -> None:
    """Parse one canonical envelope and authenticate it, failing closed."""
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
            config=config,
            service_identity=service_identity,
            public=public,
        )
    except Exception as error:
        raise ValueError("persisted verifier envelope authentication failed") from error


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
        for row in rows:
            _validate_decision_row(owner, row)
    finally:
        db.close()


def _validate_decision_row(owner: Any, row: Any) -> None:
    """Check one consumed-decision row and its signed canonical receipt."""
    decision_id, nonce, manifest, consumed_at, raw_receipt = row
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
    if type(receipt) is not dict or set(receipt) != _DECISION_RECEIPT_KEYS:
        raise ValueError("stored decision receipt envelope invalid")
    body = receipt["receipt"]
    if not _decision_receipt_matches(
        owner, receipt, body, decision_id, manifest, consumed_at
    ):
        raise ValueError("stored decision receipt does not match ledger row")
    _hex64(body["decision_contract_sha256"], "stored decision digest")
    _verify_decision_signature(owner, receipt, body)


def _decision_receipt_matches(
    owner: Any,
    receipt: dict[str, Any],
    body: Any,
    decision_id: str,
    manifest: str,
    consumed_at: int,
) -> bool:
    """Return whether the receipt body is bound to this exact ledger row.

    Checks run in the original order and short-circuit at the first
    mismatch; the owner's decision config is read only once the body's own
    fields have matched.
    """
    if type(body) is not dict or set(body) != _DECISION_BODY_KEYS:
        return False
    return (
        body["schema_version"] == 1
        and body["decision_id"] == decision_id
        and body["manifest_sha256"] == manifest
        and body["verdict_status"] == "SETUP_QUALIFIED"
        and type(body["consumed_at_ns"]) is int
        and type(body["service_identity"]) is dict
        and body["consumed_at_ns"] == consumed_at
        and body["service_identity"]
        == owner._decision_config["trusted"]["decision_consumer_runtime"]["measurement"]
        and receipt["algorithm"] == "Ed25519"
        and receipt["key_id"] == owner._decision_config["decision_consumer"]["key_id"]
        and type(receipt["signature"]) is str
        and len(receipt["signature"]) == 128
    )


def _verify_decision_signature(
    owner: Any, receipt: dict[str, Any], body: dict[str, Any]
) -> None:
    """Verify the consumer's Ed25519 signature over the canonical body."""
    try:
        signature = bytes.fromhex(receipt["signature"])
        public = bytes.fromhex(
            owner._decision_config["decision_consumer"]["public_key_hex"]
        )
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature,
            DECISION_RECEIPT_DOMAIN + canonical_json_bytes(body),
        )
    except Exception as error:
        raise ValueError("stored decision receipt signature invalid") from error
