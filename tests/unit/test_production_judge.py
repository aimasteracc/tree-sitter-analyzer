"""Tests for the NO1-002D Judge record (production_judge.py)."""

from __future__ import annotations

import pytest

from benchmarks.codegraph_compare.production_anchor import AnchorKey
from benchmarks.codegraph_compare.production_judge import (
    VALID_VERDICTS,
    JudgeRecord,
    submit_verdict,
    verify_judge_record,
)

_EVIDENCE_DIGEST = "a" * 64
_SPEC_HASH = "b" * 64
_NOW = 1_900_000_000


def _key() -> AnchorKey:
    return AnchorKey(raw=b"k" * 32)


def _record(verdict: str = "ACCEPT", **kwargs) -> JudgeRecord:
    return submit_verdict(
        verdict,
        _EVIDENCE_DIGEST,
        _SPEC_HASH,
        _key(),
        now_unix=kwargs.get("now_unix", _NOW),
        judge_note=kwargs.get("judge_note", ""),
    )


class TestSubmitVerdict:
    def test_accept_verdict_creates_valid_record(self) -> None:
        record = _record("ACCEPT")
        assert isinstance(record, JudgeRecord)
        assert record.verdict == "ACCEPT"
        assert record.evidence_digest == _EVIDENCE_DIGEST
        assert record.recorded_at_unix == _NOW
        assert len(record.signature_ed25519) == 128

    @pytest.mark.parametrize("verdict", sorted(VALID_VERDICTS))
    def test_all_valid_verdicts_accepted(self, verdict: str) -> None:
        record = _record(verdict)
        assert record.verdict == verdict

    def test_unknown_verdict_rejected(self) -> None:
        with pytest.raises(ValueError, match="verdict must be one of"):
            submit_verdict("PASS", _EVIDENCE_DIGEST, _SPEC_HASH, _key(), now_unix=_NOW)

    def test_malformed_evidence_digest_rejected(self) -> None:
        with pytest.raises(ValueError, match="evidence_digest"):
            submit_verdict("ACCEPT", "short", _SPEC_HASH, _key(), now_unix=_NOW)

    def test_uppercase_hex_evidence_digest_rejected(self) -> None:
        with pytest.raises(ValueError, match="evidence_digest"):
            submit_verdict("ACCEPT", "A" * 64, _SPEC_HASH, _key(), now_unix=_NOW)

    def test_malformed_spec_hash_rejected(self) -> None:
        with pytest.raises(ValueError, match="spec_hash"):
            submit_verdict("ACCEPT", _EVIDENCE_DIGEST, "short", _key(), now_unix=_NOW)

    def test_judge_note_is_preserved(self) -> None:
        record = _record("REJECT", judge_note="transcript missing MCP receipt")
        assert record.judge_note == "transcript missing MCP receipt"

    def test_hmac_differs_between_verdicts(self) -> None:
        accept = _record("ACCEPT")
        reject = _record("REJECT")
        assert accept.signature_ed25519 != reject.signature_ed25519

    def test_hmac_differs_between_evidence_digests(self) -> None:
        r1 = submit_verdict("ACCEPT", "a" * 64, _SPEC_HASH, _key(), now_unix=_NOW)
        r2 = submit_verdict("ACCEPT", "b" * 64, _SPEC_HASH, _key(), now_unix=_NOW)
        assert r1.signature_ed25519 != r2.signature_ed25519

    def test_hmac_differs_between_spec_hashes(self) -> None:
        r1 = submit_verdict("ACCEPT", _EVIDENCE_DIGEST, "c" * 64, _key(), now_unix=_NOW)
        r2 = submit_verdict("ACCEPT", _EVIDENCE_DIGEST, "d" * 64, _key(), now_unix=_NOW)
        assert r1.signature_ed25519 != r2.signature_ed25519


class TestVerifyJudgeRecord:
    def test_valid_record_passes(self) -> None:
        record = _record()
        verify_judge_record(record, _key().public_bytes())

    def test_wrong_key_rejected(self) -> None:
        record = _record()
        wrong = AnchorKey(raw=b"z" * 32)
        with pytest.raises(ValueError, match="Ed25519"):
            verify_judge_record(record, wrong.public_bytes())

    def test_tampered_verdict_rejected(self) -> None:
        record = _record("ACCEPT")
        tampered = JudgeRecord(
            schema_version=record.schema_version,
            verdict="REJECT",
            evidence_digest=record.evidence_digest,
            spec_hash=record.spec_hash,
            recorded_at_unix=record.recorded_at_unix,
            judge_note=record.judge_note,
            signature_ed25519=record.signature_ed25519,
        )
        with pytest.raises(ValueError, match="Ed25519"):
            verify_judge_record(tampered, _key().public_bytes())

    def test_tampered_evidence_digest_rejected(self) -> None:
        record = _record()
        tampered = JudgeRecord(
            schema_version=record.schema_version,
            verdict=record.verdict,
            evidence_digest="b" * 64,
            spec_hash=record.spec_hash,
            recorded_at_unix=record.recorded_at_unix,
            judge_note=record.judge_note,
            signature_ed25519=record.signature_ed25519,
        )
        with pytest.raises(ValueError, match="Ed25519"):
            verify_judge_record(tampered, _key().public_bytes())

    def test_tampered_spec_hash_rejected(self) -> None:
        record = _record()
        tampered = JudgeRecord(
            schema_version=record.schema_version,
            verdict=record.verdict,
            evidence_digest=record.evidence_digest,
            spec_hash="e" * 64,
            recorded_at_unix=record.recorded_at_unix,
            judge_note=record.judge_note,
            signature_ed25519=record.signature_ed25519,
        )
        with pytest.raises(ValueError, match="Ed25519"):
            verify_judge_record(tampered, _key().public_bytes())

    def test_non_record_object_rejected(self) -> None:
        with pytest.raises(ValueError, match="JudgeRecord"):
            verify_judge_record("not-a-record", _key())  # type: ignore[arg-type]

    def test_wrong_schema_version_rejected(self) -> None:
        record = _record()
        tampered = JudgeRecord(
            schema_version=99,
            verdict=record.verdict,
            evidence_digest=record.evidence_digest,
            spec_hash=record.spec_hash,
            recorded_at_unix=record.recorded_at_unix,
            judge_note=record.judge_note,
            signature_ed25519=record.signature_ed25519,
        )
        with pytest.raises(ValueError, match="schema_version"):
            verify_judge_record(tampered, _key().public_bytes())
