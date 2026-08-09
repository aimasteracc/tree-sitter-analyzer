"""Tests for the NO1-002D Anchor Custodian (production_anchor.py)."""

from __future__ import annotations

import pytest

from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    SpendAttestation,
    prepare_attestation,
    verify_attestation,
)

# 64-char hex string encodes 32 bytes; all characters must be valid hex.
_GOOD_KEY_HEX = "ab" * 32  # 64 hex chars = 32 bytes
_SPEC_HASH = "b" * 64
_NONCE = "judge-nonce-001"
_EXPIRES = 2_000_000_000
_NOW = 1_900_000_000


def _key() -> AnchorKey:
    return AnchorKey(raw=bytes.fromhex(_GOOD_KEY_HEX))


def _attestation(
    *,
    budget_enforcement_mode: str = "client-process-kill",
    now_unix: int = _NOW,
) -> SpendAttestation:
    return prepare_attestation(
        _SPEC_HASH,
        _NONCE,
        _EXPIRES,
        _key(),
        budget_enforcement_mode=budget_enforcement_mode,
        now_unix=now_unix,
    )


class TestAnchorKey:
    def test_from_env_loads_key_and_hex_decodes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hex_key = "cd" * 32  # 64 hex chars
        monkeypatch.setenv("CANARY_ANCHOR_KEY", hex_key)
        key = AnchorKey.from_env()
        assert key.raw == bytes.fromhex(hex_key)

    def test_from_env_rejects_short_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANARY_ANCHOR_KEY", "ab" * 16)  # only 32 chars
        with pytest.raises(ValueError, match="at least 64 hex characters"):
            AnchorKey.from_env()

    def test_from_env_rejects_missing_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CANARY_ANCHOR_KEY", raising=False)
        with pytest.raises(ValueError, match="at least 64 hex characters"):
            AnchorKey.from_env()

    def test_from_env_rejects_non_hex(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANARY_ANCHOR_KEY", "z" * 64)  # 'z' is not hex
        with pytest.raises(ValueError, match="hex-encoded"):
            AnchorKey.from_env()

    def test_from_env_rejects_whitespace_padded_key_with_too_few_bytes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "aa" + 64 spaces + "bb" has 68 chars (>= 64 char check passes),
        # but bytes.fromhex ignores whitespace and decodes to only 2 bytes.
        monkeypatch.setenv("CANARY_ANCHOR_KEY", "aa" + " " * 64 + "bb")
        with pytest.raises(ValueError, match="decodes to only"):
            AnchorKey.from_env()

    def test_from_file_loads_key_and_hex_decodes(self, tmp_path) -> None:
        hex_key = "ef" * 32  # 64 hex chars
        key_file = tmp_path / "anchor.key"
        key_file.write_text(hex_key, encoding="utf-8")
        key = AnchorKey.from_file(key_file)
        assert key.raw == bytes.fromhex(hex_key)

    def test_from_file_rejects_short_content(self, tmp_path) -> None:
        key_file = tmp_path / "anchor.key"
        key_file.write_text("ab" * 16, encoding="utf-8")  # 32 chars, not 64
        with pytest.raises(ValueError, match="at least 64 hex characters"):
            AnchorKey.from_file(key_file)

    def test_sign_is_deterministic(self) -> None:
        key = _key()
        sig1 = key.sign(b"payload")
        sig2 = key.sign(b"payload")
        assert sig1 == sig2

    def test_different_keys_produce_different_signatures(self) -> None:
        key1 = AnchorKey(raw=b"a" * 32)
        key2 = AnchorKey(raw=b"b" * 32)
        assert key1.sign(b"payload") != key2.sign(b"payload")


class TestPrepareAttestation:
    def test_returns_spend_attestation(self) -> None:
        att = _attestation()
        assert isinstance(att, SpendAttestation)
        assert att.schema_version == 1
        assert att.spec_hash == _SPEC_HASH
        assert att.nonce == _NONCE
        assert att.issued_at_unix == _NOW
        assert att.budget_enforcement_mode == "client-process-kill"
        assert len(att.signature_ed25519) == 128

    def test_provider_mode_accepted(self) -> None:
        att = _attestation(budget_enforcement_mode="provider")
        assert att.budget_enforcement_mode == "provider"

    def test_unknown_enforcement_mode_rejected(self) -> None:
        with pytest.raises(ValueError, match="budget_enforcement_mode"):
            prepare_attestation(
                _SPEC_HASH,
                _NONCE,
                _EXPIRES,
                _key(),
                budget_enforcement_mode="unknown-mode",
            )

    def test_expired_spec_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="expired"):
            prepare_attestation(
                _SPEC_HASH,
                _NONCE,
                _EXPIRES,
                _key(),
                now_unix=_EXPIRES,  # now == expires → expired
            )

    def test_short_spec_hash_rejected(self) -> None:
        with pytest.raises(ValueError, match="spec_hash"):
            prepare_attestation("short", _NONCE, _EXPIRES, _key(), now_unix=_NOW)

    def test_empty_nonce_rejected(self) -> None:
        with pytest.raises(ValueError, match="nonce"):
            prepare_attestation(_SPEC_HASH, "", _EXPIRES, _key(), now_unix=_NOW)


class TestVerifyAttestation:
    def test_valid_attestation_passes(self) -> None:
        att = _attestation()
        verify_attestation(
            att, _key().public_bytes(), _SPEC_HASH, _NONCE, _EXPIRES, now_unix=_NOW
        )

    def test_wrong_spec_hash_rejected(self) -> None:
        att = _attestation()
        with pytest.raises(ValueError, match="spec_hash"):
            verify_attestation(
                att, _key().public_bytes(), "c" * 64, _NONCE, _EXPIRES, now_unix=_NOW
            )

    def test_wrong_nonce_rejected(self) -> None:
        att = _attestation()
        with pytest.raises(ValueError, match="nonce"):
            verify_attestation(
                att,
                _key().public_bytes(),
                _SPEC_HASH,
                "wrong-nonce",
                _EXPIRES,
                now_unix=_NOW,
            )

    def test_wrong_key_rejected(self) -> None:
        att = _attestation()
        wrong_key = AnchorKey(raw=b"z" * 32)
        with pytest.raises(ValueError, match="Ed25519"):
            verify_attestation(
                att,
                wrong_key.public_bytes(),
                _SPEC_HASH,
                _NONCE,
                _EXPIRES,
                now_unix=_NOW,
            )

    def test_expired_spec_rejected_at_verify_time(self) -> None:
        att = _attestation()
        with pytest.raises(ValueError, match="expired"):
            verify_attestation(
                att,
                _key().public_bytes(),
                _SPEC_HASH,
                _NONCE,
                _EXPIRES,
                now_unix=_EXPIRES,
            )

    def test_future_issued_at_rejected(self) -> None:
        att = _attestation(now_unix=_NOW + 1000)
        with pytest.raises(ValueError, match="future"):
            verify_attestation(att, _key(), _SPEC_HASH, _NONCE, _EXPIRES, now_unix=_NOW)

    def test_non_attestation_object_rejected(self) -> None:
        with pytest.raises(ValueError, match="SpendAttestation"):
            verify_attestation(
                "not-an-attestation",
                _key(),
                _SPEC_HASH,
                _NONCE,
                _EXPIRES,
                now_unix=_NOW,
            )  # type: ignore[arg-type]

    def test_tampered_hmac_rejected(self) -> None:
        att = _attestation()
        tampered = SpendAttestation(
            schema_version=att.schema_version,
            spec_hash=att.spec_hash,
            nonce=att.nonce,
            issued_at_unix=att.issued_at_unix,
            budget_enforcement_mode=att.budget_enforcement_mode,
            signature_ed25519="0" * 64,
        )
        with pytest.raises(ValueError, match="Ed25519"):
            verify_attestation(
                tampered,
                _key().public_bytes(),
                _SPEC_HASH,
                _NONCE,
                _EXPIRES,
                now_unix=_NOW,
            )
