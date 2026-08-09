"""Verification-only wire receipts from external production authorities.

The dispatcher keeps Ed25519 public keys only.  Receipt issuers and their
one-shot/immutable state live outside this process; no private-key or receipt
issuing helper is provided here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchmarks.codegraph_compare.canary_evidence import canonical_sha256
from benchmarks.codegraph_compare.production_run_spec import ProductionRunSpecV1

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_128 = re.compile(r"^[0-9a-f]{128}$")


def _canonical(value: object) -> bytes:
    import json

    return json.dumps(
        value, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def verify_ed25519(public_key: bytes, payload: dict[str, Any], signature: str) -> None:
    """Verify a canonical receipt without ever loading authority private material."""
    if type(public_key) is not bytes or len(public_key) != 32:
        raise ValueError("authority public key must be exactly 32 bytes")
    if type(signature) is not str or _HEX_128.fullmatch(signature) is None:
        raise ValueError("receipt signature must be lowercase Ed25519 hex")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(signature), _canonical(payload)
        )
    except (InvalidSignature, ValueError) as error:
        raise ValueError("authority receipt signature is invalid") from error


def ledger_identity_sha256(spec: ProductionRunSpecV1) -> str:
    fields = {
        "global_nonce_ledger_root": spec.global_nonce_ledger_root,
        **{
            name: getattr(spec, name)
            for name in (
                "ledger_root_device",
                "ledger_root_inode",
                "ledger_root_uid",
                "ledger_root_mode",
                "ledger_parent_device",
                "ledger_parent_inode",
                "ledger_parent_uid",
                "ledger_parent_mode",
            )
        },
    }
    return canonical_sha256(fields)


@dataclass(frozen=True)
class ClaimAuthorityReceiptV1:
    spec_hash: str
    nonce: str
    ledger_identity_sha256: str
    run_expires_at_unix: int
    claim_id: str
    dispatch_challenge: str
    issued_at_unix: int
    issuer_role: str
    key_id: str
    signature_ed25519: str
    schema_version: int = 1

    def signed_fields(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "signature_ed25519"
        }


@dataclass(frozen=True)
class EvidenceAuthorityReceiptV1:
    spec_hash: str
    nonce: str
    evidence_digest: str
    terminal_status: str
    provider_usage_receipt_sha256: str
    run_expires_at_unix: int
    terminal_id: str
    claim_id: str
    issued_at_unix: int
    issuer_role: str
    key_id: str
    signature_ed25519: str
    schema_version: int = 1

    def signed_fields(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "signature_ed25519"
        }


@dataclass(frozen=True)
class ProviderReservationReceiptV1:
    spec_hash: str
    nonce: str
    reservation_id: str
    request_limit: int
    token_limit: int
    budget_ceiling_microusd: int
    run_expires_at_unix: int
    issuer_role: str
    key_id: str
    signature_ed25519: str
    schema_version: int = 1

    def signed_fields(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "signature_ed25519"
        }


@dataclass(frozen=True)
class ProviderUsageReceiptV1:
    spec_hash: str
    nonce: str
    reservation_id: str
    provider_request_count: int
    input_tokens: int
    output_tokens: int
    cost_microusd: int
    termination_reason: str
    run_expires_at_unix: int
    issuer_role: str
    key_id: str
    signature_ed25519: str
    schema_version: int = 1

    def signed_fields(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "signature_ed25519"
        }


def verify_claim_receipt(
    receipt: object,
    *,
    spec: ProductionRunSpecV1,
    public_key: bytes,
    key_id: str,
    now_unix: int,
    dispatch_challenge: str,
) -> None:
    if type(receipt) is not ClaimAuthorityReceiptV1:
        raise ValueError("claim authority receipt has wrong type")
    if type(receipt.schema_version) is not int or receipt.schema_version != 1:
        raise ValueError("claim receipt schema invalid")
    _digest(receipt.spec_hash, "spec_hash")
    _text(receipt.nonce, "nonce")
    _digest(receipt.ledger_identity_sha256, "ledger_identity_sha256")
    _positive(receipt.run_expires_at_unix, "run_expires_at_unix")
    _positive(receipt.issued_at_unix, "issued_at_unix")
    _text(receipt.claim_id, "claim_id")
    _digest(receipt.dispatch_challenge, "dispatch_challenge")
    if receipt.issuer_role != "nonce-claim-authority" or receipt.key_id != key_id:
        raise ValueError("claim authority identity mismatch")
    expected = (
        spec.spec_hash,
        spec.nonce,
        ledger_identity_sha256(spec),
        spec.expires_at_unix,
        dispatch_challenge,
    )
    actual = (
        receipt.spec_hash,
        receipt.nonce,
        receipt.ledger_identity_sha256,
        receipt.run_expires_at_unix,
        receipt.dispatch_challenge,
    )
    if (
        actual != expected
        or receipt.issued_at_unix > now_unix
        or now_unix >= receipt.run_expires_at_unix
    ):
        raise ValueError("claim receipt binding or lifetime mismatch")
    verify_ed25519(public_key, receipt.signed_fields(), receipt.signature_ed25519)


def verify_provider_receipts(
    reservation: object,
    usage: object,
    *,
    spec: ProductionRunSpecV1,
    public_key: bytes,
    key_id: str,
) -> None:
    if (
        type(reservation) is not ProviderReservationReceiptV1
        or type(usage) is not ProviderUsageReceiptV1
    ):
        raise ValueError("provider reservation and usage receipts are both required")
    for receipt in (reservation, usage):
        if (
            type(receipt.schema_version) is not int
            or receipt.schema_version != 1
            or receipt.issuer_role != "provider-budget-gateway"
            or receipt.key_id != key_id
        ):
            raise ValueError("provider receipt identity mismatch")
        _digest(receipt.spec_hash, "provider spec_hash")
        _text(receipt.nonce, "provider nonce")
        _text(receipt.reservation_id, "reservation_id")
        _positive(receipt.run_expires_at_unix, "provider run_expires_at_unix")
        verify_ed25519(public_key, receipt.signed_fields(), receipt.signature_ed25519)
    if any(
        type(value) is not int or value <= 0
        for value in (
            reservation.request_limit,
            reservation.token_limit,
            reservation.budget_ceiling_microusd,
        )
    ):
        raise ValueError("provider reservation limits are invalid")
    budget_micro = round(spec.budget_ceiling_usd * 1_000_000)
    if (
        reservation.spec_hash,
        reservation.nonce,
        reservation.request_limit,
        reservation.token_limit,
        reservation.budget_ceiling_microusd,
        reservation.run_expires_at_unix,
    ) != (
        spec.spec_hash,
        spec.nonce,
        1,
        spec.token_limit,
        budget_micro,
        spec.expires_at_unix,
    ):
        raise ValueError("provider reservation binding mismatch")
    if (
        usage.spec_hash,
        usage.nonce,
        usage.reservation_id,
        usage.run_expires_at_unix,
    ) != (
        spec.spec_hash,
        spec.nonce,
        reservation.reservation_id,
        spec.expires_at_unix,
    ):
        raise ValueError("provider usage binding mismatch")
    if any(
        type(value) is not int or value < 0
        for value in (
            usage.provider_request_count,
            usage.input_tokens,
            usage.output_tokens,
            usage.cost_microusd,
        )
    ):
        raise ValueError("provider usage values are invalid")
    if (
        usage.provider_request_count != 1
        or usage.input_tokens + usage.output_tokens > reservation.token_limit
        or usage.cost_microusd > reservation.budget_ceiling_microusd
    ):
        raise ValueError("provider usage exceeds reservation")
    _text(usage.termination_reason, "termination_reason")


def provider_usage_receipt_sha256(receipt: ProviderUsageReceiptV1) -> str:
    return canonical_sha256(
        {**receipt.signed_fields(), "signature_ed25519": receipt.signature_ed25519}
    )


def verify_evidence_receipt(
    receipt: object,
    *,
    spec: ProductionRunSpecV1,
    evidence_digest: str,
    usage: ProviderUsageReceiptV1,
    claim: ClaimAuthorityReceiptV1,
    public_key: bytes,
    key_id: str,
    now_unix: int,
) -> None:
    if type(receipt) is not EvidenceAuthorityReceiptV1:
        raise ValueError("evidence authority terminal receipt has wrong type")
    if type(receipt.schema_version) is not int or receipt.schema_version != 1:
        raise ValueError("evidence receipt schema invalid")
    if (
        receipt.issuer_role != "immutable-evidence-authority"
        or receipt.key_id != key_id
    ):
        raise ValueError("evidence authority identity mismatch")
    _digest(receipt.spec_hash, "evidence spec_hash")
    _digest(receipt.evidence_digest, "evidence_digest")
    _digest(receipt.provider_usage_receipt_sha256, "provider_usage_receipt_sha256")
    _text(receipt.nonce, "evidence nonce")
    _text(receipt.terminal_id, "terminal_id")
    _text(receipt.claim_id, "claim_id")
    _positive(receipt.issued_at_unix, "issued_at_unix")
    _positive(receipt.run_expires_at_unix, "run_expires_at_unix")
    expected = (
        spec.spec_hash,
        spec.nonce,
        evidence_digest,
        "PASS",
        provider_usage_receipt_sha256(usage),
        spec.expires_at_unix,
        claim.claim_id,
    )
    actual = (
        receipt.spec_hash,
        receipt.nonce,
        receipt.evidence_digest,
        receipt.terminal_status,
        receipt.provider_usage_receipt_sha256,
        receipt.run_expires_at_unix,
        receipt.claim_id,
    )
    if (
        actual != expected
        or receipt.issued_at_unix > now_unix
        or now_unix >= receipt.run_expires_at_unix
    ):
        raise ValueError("evidence receipt binding or lifetime mismatch")
    verify_ed25519(public_key, receipt.signed_fields(), receipt.signature_ed25519)
