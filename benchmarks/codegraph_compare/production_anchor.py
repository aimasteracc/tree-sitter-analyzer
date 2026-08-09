"""HMAC-SHA256 Anchor Custodian for NO1-002D production trust.

This module implements the Anchor Custodian role defined in issue #1223.
The custodian signs a ProductionRunSpecV1 before any model call, binding the
manifest hash, nonce, and budget enforcement mode into a tamper-evident
SpendAttestation.

Key material is loaded exclusively from outside the evidence bundle:
  - Environment variable: CANARY_ANCHOR_KEY (hex-encoded 32+ bytes)
  - Or a key file whose path is supplied out-of-band

Bundle-provided keys, TOFU, and self-signed attestations are forbidden.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ENV_KEY = "CANARY_ANCHOR_KEY"
_SCHEMA_VERSION = 1
SPEND_ROLE = "spend-authorizer"
DEFAULT_SPEND_KEY_ID = "legacy-spend-key"
_VALID_ENFORCEMENT_MODES = frozenset({"provider", "client-process-kill"})


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True)
class AnchorKey:
    """Key material for the Anchor Custodian.

    Must be loaded from operator-controlled storage outside the evidence bundle.
    """

    raw: bytes

    @classmethod
    def from_env(cls) -> AnchorKey:
        hex_key = os.environ.get(_ENV_KEY, "")
        if len(hex_key) < 64:
            raise ValueError(
                f"Anchor key in {_ENV_KEY} must be at least 64 hex characters (32 bytes)"
            )
        try:
            raw = bytes.fromhex(hex_key)
        except ValueError as error:
            raise ValueError(
                f"Anchor key in {_ENV_KEY} must be hex-encoded: {error}"
            ) from error
        if len(raw) < 32:
            raise ValueError(
                f"Anchor key in {_ENV_KEY} decodes to only {len(raw)} bytes; "
                "must be at least 32 (hex string may contain whitespace)"
            )
        return cls(raw=raw)

    @classmethod
    def from_file(cls, path: Path) -> AnchorKey:
        hex_key = path.read_text(encoding="utf-8").strip()
        if len(hex_key) < 64:
            raise ValueError(
                f"Anchor key file must contain at least 64 hex characters (32 bytes): {path}"
            )
        try:
            raw = bytes.fromhex(hex_key)
        except ValueError as error:
            raise ValueError(
                f"Anchor key file must be hex-encoded: {path}: {error}"
            ) from error
        if len(raw) < 32:
            raise ValueError(
                f"Anchor key file decodes to only {len(raw)} bytes; "
                f"must be at least 32 (hex string may contain whitespace): {path}"
            )
        return cls(raw=raw)

    def sign(self, payload: bytes) -> str:
        return hmac.new(self.raw, payload, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class SpendAttestation:
    """Tamper-evident record of a pre-authorised production run.

    Issued by the Anchor Custodian before any model call.  The HMAC binds
    spec_hash, nonce, issued_at_unix, and budget_enforcement_mode so that
    post-run verification can detect any substitution.
    """

    schema_version: int
    spec_hash: str
    nonce: str
    issued_at_unix: int
    budget_enforcement_mode: str
    hmac_sha256: str
    issuer_role: str = SPEND_ROLE
    key_id: str = DEFAULT_SPEND_KEY_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "spec_hash": self.spec_hash,
            "nonce": self.nonce,
            "issued_at_unix": self.issued_at_unix,
            "budget_enforcement_mode": self.budget_enforcement_mode,
            "hmac_sha256": self.hmac_sha256,
            "issuer_role": self.issuer_role,
            "key_id": self.key_id,
        }


def _attestation_payload(
    spec_hash: str,
    nonce: str,
    issued_at_unix: int,
    budget_enforcement_mode: str,
    issuer_role: str,
    key_id: str,
) -> bytes:
    return _canonical_bytes(
        {
            "schema_version": _SCHEMA_VERSION,
            "spec_hash": spec_hash,
            "nonce": nonce,
            "issued_at_unix": issued_at_unix,
            "budget_enforcement_mode": budget_enforcement_mode,
            "issuer_role": issuer_role,
            "key_id": key_id,
        }
    )


def prepare_attestation(
    spec_hash: str,
    nonce: str,
    expires_at_unix: int,
    key: AnchorKey,
    *,
    budget_enforcement_mode: str = "client-process-kill",
    now_unix: int | None = None,
    issuer_role: str = SPEND_ROLE,
    key_id: str = DEFAULT_SPEND_KEY_ID,
) -> SpendAttestation:
    """Issue a signed SpendAttestation for the given run spec fields.

    Args:
        spec_hash: The canonical SHA-256 of the ProductionRunSpecV1.
        nonce: The nonce from the run spec (binds attestation to the spec).
        expires_at_unix: Spec expiry; must be in the future relative to now_unix.
        key: The Anchor Custodian key (out-of-band, never from the bundle).
        budget_enforcement_mode: "provider" or "client-process-kill".
        now_unix: Current Unix time (defaults to time.time()).

    Raises:
        ValueError: If any argument is invalid or the spec is already expired.
    """
    if issuer_role != SPEND_ROLE:
        raise ValueError(f"issuer_role must be {SPEND_ROLE!r}")
    if not key_id:
        raise ValueError("key_id must be non-empty")
    if budget_enforcement_mode not in _VALID_ENFORCEMENT_MODES:
        raise ValueError(
            f"budget_enforcement_mode must be one of {sorted(_VALID_ENFORCEMENT_MODES)}"
        )
    if not spec_hash or len(spec_hash) != 64:
        raise ValueError("spec_hash must be a 64-character hex digest")
    if not nonce:
        raise ValueError("nonce must be non-empty")
    issued_at = int(time.time()) if now_unix is None else now_unix
    if expires_at_unix <= issued_at:
        raise ValueError("run spec has expired; cannot issue attestation")
    payload = _attestation_payload(
        spec_hash, nonce, issued_at, budget_enforcement_mode, issuer_role, key_id
    )
    signature = key.sign(payload)
    return SpendAttestation(
        schema_version=_SCHEMA_VERSION,
        spec_hash=spec_hash,
        nonce=nonce,
        issued_at_unix=issued_at,
        budget_enforcement_mode=budget_enforcement_mode,
        hmac_sha256=signature,
        issuer_role=issuer_role,
        key_id=key_id,
    )


def verify_attestation(
    attestation: SpendAttestation,
    key: AnchorKey,
    expected_spec_hash: str,
    expected_nonce: str,
    expires_at_unix: int,
    *,
    now_unix: int,
) -> None:
    """Verify a SpendAttestation against the run spec and anchor key.

    Raises:
        ValueError: If any check fails (HMAC, spec binding, expiry, etc.).
    """
    if not isinstance(attestation, SpendAttestation):
        raise ValueError("attestation must be a SpendAttestation")
    if attestation.schema_version != _SCHEMA_VERSION:
        raise ValueError(
            f"attestation schema_version {attestation.schema_version} is not supported"
        )
    if attestation.spec_hash != expected_spec_hash:
        raise ValueError("attestation spec_hash does not match run spec")
    if attestation.nonce != expected_nonce:
        raise ValueError("attestation nonce does not match run spec")
    if attestation.issued_at_unix > now_unix:
        raise ValueError("attestation claims to be issued in the future")
    if expires_at_unix <= now_unix:
        raise ValueError("run spec has expired")
    if attestation.budget_enforcement_mode not in _VALID_ENFORCEMENT_MODES:
        raise ValueError(
            f"unknown budget_enforcement_mode: {attestation.budget_enforcement_mode!r}"
        )
    if attestation.issuer_role != SPEND_ROLE:
        raise ValueError("attestation issuer role is not spend-authorizer")
    if not attestation.key_id:
        raise ValueError("attestation key_id is empty")
    payload = _attestation_payload(
        attestation.spec_hash,
        attestation.nonce,
        attestation.issued_at_unix,
        attestation.budget_enforcement_mode,
        attestation.issuer_role,
        attestation.key_id,
    )
    expected_hmac = key.sign(payload)
    if not hmac.compare_digest(expected_hmac, attestation.hmac_sha256):
        raise ValueError("attestation HMAC verification failed")
