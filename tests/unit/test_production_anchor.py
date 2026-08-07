"""Tests for the NO1-002D Anchor Custodian (production_anchor.py)."""

from __future__ import annotations

import pytest

from benchmarks.codegraph_compare.production_anchor import (
    AnchorKey,
    SpendAttestation,
    prepare_attestation,
    verify_attestation,
)

_GOOD_KEY = "a" * 32
_SPEC_HASH = "b" * 64
_NONCE = "judge-nonce-001"
_EXPIRES = 2_000_000_000
_NOW = 1_900_000_000


def _key() -> AnchorKey:
    return AnchorKey(raw=_GOOD_KEY.encode("utf-8"))


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
    def test_from_env_loads_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANARY_ANCHOR_KEY", "x" * 32)
        key = AnchorKey.from_env()
        assert key.raw == b"x" * 32

    def test_from_env_rejects_short_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANARY_ANCHOR_KEY", "short")
        with pytest.raises(ValueError, match="at least 32 characters"):
            AnchorKey.from_env()

    def test_from_env_rejects_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANARY_ANCHOR_KEY", raising=False)
        with pytest.raises(ValueError, match="at least 32 characters"):
            AnchorKey.from_env()

    def test_from_file_loads_key(self, tmp_path) -> None:
        key_file = tmp_path / "anchor.key"
        key_file.write_text("y" * 48, encoding="utf-8")
        key = AnchorKey.from_file(key_file)
        assert key.raw == b"y" * 48

    def test_from_file_rejects_short_content(self, tmp_path) -> None:
        key_file = tmp_path / "anchor.key"
        key_file.write_text("short", encoding="utf-8")
        with pytest.raises(ValueError, match="too short"):
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
        assert len(att.hmac_sha256) == 64

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
        verify_attestation(att, _key(), _SPEC_HASH, _NONCE, _EXPIRES, now_unix=_NOW)

    def test_wrong_spec_hash_rejected(self) -> None:
        att = _attestation()
        with pytest.raises(ValueError, match="spec_hash"):
            verify_attestation(att, _key(), "c" * 64, _NONCE, _EXPIRES, now_unix=_NOW)

    def test_wrong_nonce_rejected(self) -> None:
        att = _attestation()
        with pytest.raises(ValueError, match="nonce"):
            verify_attestation(att, _key(), _SPEC_HASH, "wrong-nonce", _EXPIRES, now_unix=_NOW)

    def test_wrong_key_rejected(self) -> None:
        att = _attestation()
        wrong_key = AnchorKey(raw=b"z" * 32)
        with pytest.raises(ValueError, match="HMAC"):
            verify_attestation(att, wrong_key, _SPEC_HASH, _NONCE, _EXPIRES, now_unix=_NOW)

    def test_expired_spec_rejected_at_verify_time(self) -> None:
        att = _attestation()
        with pytest.raises(ValueError, match="expired"):
            verify_attestation(att, _key(), _SPEC_HASH, _NONCE, _EXPIRES, now_unix=_EXPIRES)

    def test_future_issued_at_rejected(self) -> None:
        att = _attestation(now_unix=_NOW + 1000)
        with pytest.raises(ValueError, match="future"):
            verify_attestation(
                att, _key(), _SPEC_HASH, _NONCE, _EXPIRES, now_unix=_NOW
            )

    def test_non_attestation_object_rejected(self) -> None:
        with pytest.raises(ValueError, match="SpendAttestation"):
            verify_attestation("not-an-attestation", _key(), _SPEC_HASH, _NONCE, _EXPIRES, now_unix=_NOW)  # type: ignore[arg-type]

    def test_tampered_hmac_rejected(self) -> None:
        att = _attestation()
        tampered = SpendAttestation(
            schema_version=att.schema_version,
            spec_hash=att.spec_hash,
            nonce=att.nonce,
            issued_at_unix=att.issued_at_unix,
            budget_enforcement_mode=att.budget_enforcement_mode,
            hmac_sha256="0" * 64,
        )
        with pytest.raises(ValueError, match="HMAC"):
            verify_attestation(tampered, _key(), _SPEC_HASH, _NONCE, _EXPIRES, now_unix=_NOW)
