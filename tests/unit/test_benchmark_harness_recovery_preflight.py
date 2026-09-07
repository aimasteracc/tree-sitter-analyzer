"""Issue #1376：recovery_preflight 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit._benchmark_harness_qualification_helpers import (
    _disable_verifier_signature_checks,
    _verifier_recovery_fixture,
)


def test_verifier_retries_definitely_unsent_verification_request(monkeypatch):
    # PR #1249 review 3744975446: the issued challenge remains safe pre-send.
    from benchmarks.codegraph_compare import verifier_service

    manifest, config, begin, envelope = _verifier_recovery_fixture()
    _disable_verifier_signature_checks(monkeypatch, verifier_service)
    operations = []

    def round_trip(_path, request, _config, _timeout):
        operations.append(request["operation"])
        if request["operation"] == "begin-exact-14":
            return begin
        if operations.count("verify-exact-14") == 1:
            raise verifier_service._PreSendTransportError("unsent")
        return envelope

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)

    assert (
        verifier_service.request_verdict(
            socket_path=Path("/unused"), manifest=manifest, config=config, timeout=1
        )
        == envelope
    )
    assert operations == ["begin-exact-14", "verify-exact-14", "verify-exact-14"]


def test_verifier_polls_until_ambiguous_request_commits(monkeypatch):
    # PR #1249 review 3744975448: VERIFYING is transient under the original deadline.
    from benchmarks.codegraph_compare import verifier_service

    manifest, config, begin, envelope = _verifier_recovery_fixture()
    _disable_verifier_signature_checks(monkeypatch, verifier_service)
    operations = []

    def round_trip(_path, request, _config, _timeout):
        operations.append(request["operation"])
        if request["operation"] == "begin-exact-14":
            return begin
        raise verifier_service._PostSendTransportError("ambiguous")

    polls = iter(
        (
            verifier_service._VerdictPending("in progress"),
            verifier_service._VerdictPending("not found"),
            envelope,
        )
    )

    def query(**_kwargs):
        value = next(polls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)
    monkeypatch.setattr(verifier_service, "query_verdict", query)
    monkeypatch.setattr(verifier_service.time, "sleep", lambda _delay: None)

    assert (
        verifier_service.request_verdict(
            socket_path=Path("/unused"), manifest=manifest, config=config, timeout=1
        )
        == envelope
    )
    assert operations == ["begin-exact-14", "verify-exact-14"]


def test_operator_rejects_staged_inventory_with_untrusted_digest(monkeypatch):
    # PR #1249 review 3744975449: digest failure must precede authority use.
    from benchmarks.codegraph_compare import qualification_operator as operator
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    payload = canonical_json_bytes({"repo_id": "repo"})
    monkeypatch.setattr(operator, "validate_receipt_inventory", lambda value: value)

    with pytest.raises(ValueError, match="trusted inventory digest"):
        operator._validate_staged_inventory(payload, "repo", "0" * 64)


def test_decision_parser_accepts_payload_above_receipt_parser_ceiling():
    # PR #1249 review 3744975455: decision parsing must honor its 64 MiB frame.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    padding = "x" * (16 * 1024 * 1024)
    payload = ('{"padding":"' + padding + '"}').encode()

    assert consumer._decision_json_loads(payload) == {"padding": padding}


def test_decision_preflight_rejects_final_frame_before_execution(monkeypatch):
    # PR #1249 review 3744975455: bound the final consume envelope pre-execution.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    monkeypatch.setattr(consumer, "DECISION_ENVELOPE_SCHEMA_OVERHEAD", 0)
    monkeypatch.setattr(consumer, "MAX_FRAME", 10)

    with pytest.raises(ValueError, match="upper bound exceeds frame ceiling"):
        consumer.preflight_decision_consume_request(
            {}, 0, {"closure_manifest": "root-signed-runtime"}
        )


def test_staged_plan_path_rejects_parent_traversal():
    # PR #1249 review 3744975460: receipt paths are canonical before reservation.
    from benchmarks.codegraph_compare.setup_qualification_executor import _bounded_path

    with pytest.raises(ValueError, match="artifact path is not canonical"):
        _bounded_path("../artifact", "artifact path")
