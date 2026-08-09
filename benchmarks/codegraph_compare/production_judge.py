"""Human Judge record for NO1-002D production trust.

This module implements the Judge role defined in issues #1221 and #1223.
An independent Judge with a role-specific key reviews the collected evidence
and records a verdict.  The verdict is Ed25519-signed to bind it to
a specific evidence_digest, preventing replay of old verdicts against new
evidence bundles.

Verdicts:
    ACCEPT       — all acceptance criteria are met; qualifies this cell for a
                   separately pre-registered future Smoke
    REJECT       — criteria not met; cell is permanently closed
    INVALID      — protocol violation detected; cell is permanently closed
    NOT_EVALUATED — insufficient evidence to decide; run may not be reused
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    _canonical_bytes,
)

_SCHEMA_VERSION = 1
JUDGE_ROLE = "independent-judge"
DEFAULT_JUDGE_KEY_ID = "legacy-judge-key"
VALID_VERDICTS = frozenset({"ACCEPT", "REJECT", "INVALID", "NOT_EVALUATED"})


@dataclass(frozen=True)
class JudgeRecord:
    """Tamper-evident verdict record signed by the independent Judge key.

    The Ed25519 signature binds verdict, evidence_digest, spec_hash, recorded_at_unix, and
    judge_note so that any post-fact modification is detectable and the verdict
    is tied to a specific run spec (preventing replay across different runs).
    """

    schema_version: int
    verdict: str
    evidence_digest: str
    spec_hash: str
    recorded_at_unix: int
    judge_note: str
    signature_ed25519: str
    issuer_role: str = JUDGE_ROLE
    key_id: str = DEFAULT_JUDGE_KEY_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "verdict": self.verdict,
            "evidence_digest": self.evidence_digest,
            "spec_hash": self.spec_hash,
            "recorded_at_unix": self.recorded_at_unix,
            "judge_note": self.judge_note,
            "signature_ed25519": self.signature_ed25519,
            "issuer_role": self.issuer_role,
            "key_id": self.key_id,
        }


def _judge_payload(
    verdict: str,
    evidence_digest: str,
    spec_hash: str,
    recorded_at_unix: int,
    judge_note: str,
    issuer_role: str,
    key_id: str,
) -> bytes:
    return _canonical_bytes(
        {
            "schema_version": _SCHEMA_VERSION,
            "verdict": verdict,
            "evidence_digest": evidence_digest,
            "spec_hash": spec_hash,
            "recorded_at_unix": recorded_at_unix,
            "judge_note": judge_note,
            "issuer_role": issuer_role,
            "key_id": key_id,
        }
    )


def submit_verdict(
    verdict: str,
    evidence_digest: str,
    spec_hash: str,
    key: AnchorKey,
    *,
    judge_note: str = "",
    now_unix: int | None = None,
    issuer_role: str = JUDGE_ROLE,
    key_id: str = DEFAULT_JUDGE_KEY_ID,
) -> JudgeRecord:
    """Record a signed Judge verdict against a specific evidence bundle and run spec.

    The Ed25519 payload includes spec_hash so that this verdict cannot be replayed
    against a different run whose evidence happens to share the same ledger digest.

    Args:
        verdict: One of ACCEPT, REJECT, INVALID, NOT_EVALUATED.
        evidence_digest: SHA-256 of the evidence bundle (CollectionReceipt.ledger_sha256).
        spec_hash: SHA-256 of the ProductionRunSpecV1 this verdict is issued for.
        key: The independent Judge key used for signing.
        judge_note: Optional human-readable rationale for the verdict.
        now_unix: Current Unix time (defaults to time.time()).

    Raises:
        ValueError: If verdict or digest arguments are invalid.
    """
    if issuer_role != JUDGE_ROLE:
        raise ValueError(f"issuer_role must be {JUDGE_ROLE!r}")
    if not key_id:
        raise ValueError("key_id must be non-empty")
    if verdict not in VALID_VERDICTS:
        raise ValueError(
            f"verdict must be one of {sorted(VALID_VERDICTS)}, got {verdict!r}"
        )
    if (
        not evidence_digest
        or len(evidence_digest) != 64
        or not all(c in "0123456789abcdef" for c in evidence_digest)
    ):
        raise ValueError("evidence_digest must be a 64-character lowercase hex string")
    if (
        not spec_hash
        or len(spec_hash) != 64
        or not all(c in "0123456789abcdef" for c in spec_hash)
    ):
        raise ValueError("spec_hash must be a 64-character lowercase hex string")
    recorded_at = int(time.time()) if now_unix is None else now_unix
    payload = _judge_payload(
        verdict,
        evidence_digest,
        spec_hash,
        recorded_at,
        judge_note,
        issuer_role,
        key_id,
    )
    signature = key.sign(payload)
    return JudgeRecord(
        schema_version=_SCHEMA_VERSION,
        verdict=verdict,
        evidence_digest=evidence_digest,
        spec_hash=spec_hash,
        recorded_at_unix=recorded_at,
        judge_note=judge_note,
        signature_ed25519=signature,
        issuer_role=issuer_role,
        key_id=key_id,
    )


def verify_judge_record(record: JudgeRecord, public_key: bytes) -> None:
    """Verify a JudgeRecord Ed25519 signature.

    Raises:
        ValueError: If the record is malformed or Ed25519 verification fails.
    """
    if not isinstance(record, JudgeRecord):
        raise ValueError("record must be a JudgeRecord")
    if record.schema_version != _SCHEMA_VERSION:
        raise ValueError(
            f"JudgeRecord schema_version {record.schema_version} is not supported"
        )
    if record.verdict not in VALID_VERDICTS:
        raise ValueError(f"Unknown verdict: {record.verdict!r}")
    if record.issuer_role != JUDGE_ROLE:
        raise ValueError("record issuer role is not independent-judge")
    if not record.key_id:
        raise ValueError("record key_id is empty")
    payload = _judge_payload(
        record.verdict,
        record.evidence_digest,
        record.spec_hash,
        record.recorded_at_unix,
        record.judge_note,
        record.issuer_role,
        record.key_id,
    )
    if type(public_key) is not bytes or len(public_key) != 32:
        raise ValueError("judge verifier requires a 32-byte Ed25519 public key")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(record.signature_ed25519), payload
        )
    except (InvalidSignature, ValueError) as error:
        raise ValueError("JudgeRecord Ed25519 verification failed") from error
