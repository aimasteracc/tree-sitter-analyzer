"""RFC-0022 task-outcome/v1 evidence identity (Phase A).

Every supported/contradicted claim cites evidence; unknown claims cite an
unknown. Evidence IDs are deterministic digests over the canonical wire
fragment supporting the claim:

    evidence:sha256(canonical_json({
      primitive_facade, action, action_version,
      normalized_result_sha256, source_snapshots, locator
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
from typing import Literal

_EVIDENCE_PREFIX = "evidence:"

SnapshotKind = Literal["index", "diff"]


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
class SourceSnapshotRecord:
    """One stable P0.4 snapshot record bound to a contribution.

    RFC-0022: ``source_snapshots`` is the exact stable P0.4 list received
    for that fragment — a constraint contribution binds both the diff/config
    and graph-index identities (``kind`` is ``index`` or ``diff``).
    """

    kind: SnapshotKind
    snapshot_id: str
    source_generation: str

    def __post_init__(self) -> None:
        if self.kind not in {"index", "diff"}:
            raise ValueError(f"unknown snapshot kind {self.kind!r}")
        if type(self.snapshot_id) is not str or not self.snapshot_id:
            raise ValueError("snapshot_id must be a non-empty string")
        if type(self.source_generation) is not str or not self.source_generation:
            raise ValueError("source_generation must be a non-empty string")


@dataclass(frozen=True)
class EvidenceInput:
    """The six owner/result fields that define one evidence identity.

    ``normalized_result_sha256`` is the digest of the canonical bytes of the
    exact primitive wire fragment supporting the claim; the primitive wire
    already carries its facade, action, action version and (when rule-derived)
    producer rule id/version — the task adapter never inserts them.
    ``source_snapshots`` is the exact stable P0.4 record list received for
    that fragment (RFC-0022 §Evidence and provenance identity).
    """

    primitive_facade: str
    action: str
    action_version: str
    normalized_result_sha256: str
    source_snapshots: tuple[SourceSnapshotRecord, ...]
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
        if type(self.source_snapshots) is not tuple or any(
            type(record) is not SourceSnapshotRecord for record in self.source_snapshots
        ):
            raise ValueError("source_snapshots must be a tuple of SourceSnapshotRecord")
        if type(self.locator) is not str:
            raise ValueError("locator must be a string")


def evidence_identity(inputs: EvidenceInput) -> str:
    """Mint the deterministic evidence ID for one contribution.

    Returns ``evidence:sha256(...)`` over the canonical owner/result fields,
    with ``source_snapshots`` serialized as the exact record list. Missing or
    disagreeing ownership is handled by the caller as ``unknown`` (no ID
    minted) before this function is invoked.
    """
    payload = {
        "primitive_facade": inputs.primitive_facade,
        "action": inputs.action,
        "action_version": inputs.action_version,
        "normalized_result_sha256": inputs.normalized_result_sha256,
        "source_snapshots": [
            {
                "kind": record.kind,
                "snapshot_id": record.snapshot_id,
                "source_generation": record.source_generation,
            }
            for record in inputs.source_snapshots
        ],
        "locator": inputs.locator,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"{_EVIDENCE_PREFIX}{digest}"


def normalized_result_hash(fragment: object) -> str:
    """Canonical digest of the exact primitive wire fragment bytes.

    RFC-0022: the hash covers the canonical bytes of the exact primitive wire
    fragment supporting the claim — that wire already contains its primitive
    facade, action, action version and (when rule-derived) producer rule
    id/version, so the adapter never inserts owner fields.
    """
    return hashlib.sha256(canonical_json_bytes(fragment)).hexdigest()
