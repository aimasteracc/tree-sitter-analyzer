"""Pure signature verification for externally supplied NO1-008A trust roots."""

from __future__ import annotations

import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


@dataclass(frozen=True)
class VerifierConfigV1:
    """Immutable trust roots supplied to a fresh, trusted verifier process."""

    executor_key_id: str
    executor_public_key: bytes
    approver_key_id: str
    approver_public_key: bytes

    def __post_init__(self) -> None:
        if (
            not self.executor_key_id
            or not self.approver_key_id
            or self.executor_key_id == self.approver_key_id
            or type(self.executor_public_key) is not bytes
            or type(self.approver_public_key) is not bytes
            or len(self.executor_public_key) != 32
            or len(self.approver_public_key) != 32
            or self.executor_public_key == self.approver_public_key
        ):
            raise ValueError("Verifier trust roots must be distinct Ed25519 identities")


def _verify_signature(
    *,
    key_id: object,
    signature: object,
    payload: object,
    expected_key_id: str,
    public_key: bytes,
) -> bool:
    if key_id != expected_key_id or not isinstance(signature, str):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(signature),
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8"),
        )
    except (ValueError, InvalidSignature):
        return False
    return True
