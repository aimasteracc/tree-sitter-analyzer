"""Human Judge record for NO1-002D production trust.

This module implements the Judge role defined in issues #1221 and #1223.
The maintainer (who holds the Anchor Custodian key) reviews the collected
evidence and records a verdict.  The verdict is HMAC-signed to bind it to
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

import hmac
import time
from dataclasses import dataclass
from typing import Any

from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    _canonical_bytes,
)

_SCHEMA_VERSION = 1
VALID_VERDICTS = frozenset({"ACCEPT", "REJECT", "INVALID", "NOT_EVALUATED"})


@dataclass(frozen=True)
class JudgeRecord:
    """Tamper-evident verdict record signed by the Judge (Anchor Custodian key).

    The HMAC binds verdict, evidence_digest, spec_hash, recorded_at_unix, and
    judge_note so that any post-fact modification is detectable and the verdict
    is tied to a specific run spec (preventing replay across different runs).
    """

    schema_version: int
    verdict: str
    evidence_digest: str
    spec_hash: str
    recorded_at_unix: int
    judge_note: str
    hmac_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "verdict": self.verdict,
            "evidence_digest": self.evidence_digest,
            "spec_hash": self.spec_hash,
            "recorded_at_unix": self.recorded_at_unix,
            "judge_note": self.judge_note,
            "hmac_sha256": self.hmac_sha256,
        }


def _judge_payload(
    verdict: str,
    evidence_digest: str,
    spec_hash: str,
    recorded_at_unix: int,
    judge_note: str,
) -> bytes:
    return _canonical_bytes(
        {
            "schema_version": _SCHEMA_VERSION,
            "verdict": verdict,
            "evidence_digest": evidence_digest,
            "spec_hash": spec_hash,
            "recorded_at_unix": recorded_at_unix,
            "judge_note": judge_note,
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
) -> JudgeRecord:
    """Record a signed Judge verdict against a specific evidence bundle and run spec.

    The HMAC payload includes spec_hash so that this verdict cannot be replayed
    against a different run whose evidence happens to share the same ledger digest.

    Args:
        verdict: One of ACCEPT, REJECT, INVALID, NOT_EVALUATED.
        evidence_digest: SHA-256 of the evidence bundle (CollectionReceipt.ledger_sha256).
        spec_hash: SHA-256 of the ProductionRunSpecV1 this verdict is issued for.
        key: The Anchor Custodian key used for signing.
        judge_note: Optional human-readable rationale for the verdict.
        now_unix: Current Unix time (defaults to time.time()).

    Raises:
        ValueError: If verdict or digest arguments are invalid.
    """
    if verdict not in VALID_VERDICTS:
        raise ValueError(
            f"verdict must be one of {sorted(VALID_VERDICTS)}, got {verdict!r}"
        )
    if (
        not evidence_digest
        or len(evidence_digest) != 64
        or not all(c in "0123456789abcdef" for c in evidence_digest)
    ):
        raise ValueError(
            "evidence_digest must be a 64-character lowercase hex string"
        )
    if (
        not spec_hash
        or len(spec_hash) != 64
        or not all(c in "0123456789abcdef" for c in spec_hash)
    ):
        raise ValueError(
            "spec_hash must be a 64-character lowercase hex string"
        )
    recorded_at = int(time.time()) if now_unix is None else now_unix
    payload = _judge_payload(verdict, evidence_digest, spec_hash, recorded_at, judge_note)
    signature = key.sign(payload)
    return JudgeRecord(
        schema_version=_SCHEMA_VERSION,
        verdict=verdict,
        evidence_digest=evidence_digest,
        spec_hash=spec_hash,
        recorded_at_unix=recorded_at,
        judge_note=judge_note,
        hmac_sha256=signature,
    )


def verify_judge_record(record: JudgeRecord, key: AnchorKey) -> None:
    """Verify a JudgeRecord HMAC signature.

    Raises:
        ValueError: If the record is malformed or HMAC verification fails.
    """
    if not isinstance(record, JudgeRecord):
        raise ValueError("record must be a JudgeRecord")
    if record.schema_version != _SCHEMA_VERSION:
        raise ValueError(
            f"JudgeRecord schema_version {record.schema_version} is not supported"
        )
    if record.verdict not in VALID_VERDICTS:
        raise ValueError(f"Unknown verdict: {record.verdict!r}")
    payload = _judge_payload(
        record.verdict,
        record.evidence_digest,
        record.spec_hash,
        record.recorded_at_unix,
        record.judge_note,
    )
    expected = key.sign(payload)
    if not hmac.compare_digest(expected, record.hmac_sha256):
        raise ValueError("JudgeRecord HMAC verification failed")
