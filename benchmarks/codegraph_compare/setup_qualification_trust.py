"""Pinned external trust roots for NO1-008A qualification evidence."""

from __future__ import annotations

import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Public verification keys are pinned here; private keys belong only to the external
# approver and independent harness executor and are never supplied to a producer.
TRUSTED_APPROVER_KEY_ID = "no1-008a-approver-v1"
TRUSTED_APPROVER_PUBLIC_KEY = bytes.fromhex(
    "a33cb8e2b153f77bf55c362653dbaba3868f0788946e60eca4d43ed4be12146a"  # pragma: allowlist secret
)
TRUSTED_EXECUTOR_KEY_ID = "no1-008a-executor-v1"
TRUSTED_EXECUTOR_PUBLIC_KEY = bytes.fromhex(
    "fe4578b0f66e41092a3e14a09b14b651ce2b9b04d92a952d5de2d4fe742d155c"  # pragma: allowlist secret
)


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
