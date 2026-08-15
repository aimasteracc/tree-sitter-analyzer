"""RFC-0022 task-outcome/v1 evidence identity (Phase A).

Every supported/contradicted claim cites evidence; unknown claims cite an
unknown. Evidence IDs are deterministic digests over the canonical wire
fragment supporting the claim:

    evidence:sha256(canonical_json({
      primitive_facade, action, action_version,
      normalized_result_sha256, source_snapshot_id, locator
    }))

The task adapter only validates, canonicalizes, and hashes the exact
primitive wire bytes; it never inserts owner fields, and the primitive never
supplies the digest. Missing or disagreement makes the contribution
``unknown`` and mints no evidence ID. Locator alone never identifies or
deduplicates evidence (RFC-0022 §Evidence and provenance identity).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

_EVIDENCE_PREFIX = "evidence:"


#: Canonical JSON for digest inputs: sorted keys, compact separators, no
#: NaN, ASCII-escaped — byte-stable across interpreters.
def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class EvidenceInput:
    """The six owner/result fields that define one evidence identity.

    ``normalized_result_sha256`` is the digest of the canonical bytes of the
    exact primitive wire fragment supporting the claim; the primitive wire
    already carries its facade, action, action version and (when rule-derived)
    producer rule id/version — the task adapter never inserts them.
    """

    primitive_facade: str
    action: str
    action_version: str
    normalized_result_sha256: str
    source_snapshot_id: str | None
    locator: str

    def __post_init__(self) -> None:
        for name, value in (
            ("primitive_facade", self.primitive_facade),
            ("action", self.action),
            ("action_version", self.action_version),
        ):
            if type(value) is not str or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if (
            type(self.normalized_result_sha256) is not str
            or len(self.normalized_result_sha256) != 64
            or any(
                char not in "0123456789abcdef" for char in self.normalized_result_sha256
            )
        ):
            raise ValueError("normalized_result_sha256 must be a 64-hex digest")
        if self.source_snapshot_id is not None and (
            type(self.source_snapshot_id) is not str or not self.source_snapshot_id
        ):
            raise ValueError("source_snapshot_id must be a non-empty string or null")
        if type(self.locator) is not str:
            raise ValueError("locator must be a string")


def evidence_identity(inputs: EvidenceInput) -> str:
    """Mint the deterministic evidence ID for one contribution.

    Returns ``evidence:sha256(...)`` over the canonical owner/result fields.
    Missing or disagreeing ownership is handled by the caller as ``unknown``
    (no ID minted) before this function is invoked.
    """
    payload = {
        "primitive_facade": inputs.primitive_facade,
        "action": inputs.action,
        "action_version": inputs.action_version,
        "normalized_result_sha256": inputs.normalized_result_sha256,
        "source_snapshot_id": inputs.source_snapshot_id,
        "locator": inputs.locator,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"{_EVIDENCE_PREFIX}{digest}"


def normalized_result_hash(result: object) -> str:
    """Canonical digest of one exact primitive wire fragment (result only)."""
    return hashlib.sha256(canonical_json_bytes(result)).hexdigest()
