"""Issue #1376：transport_recovery 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import hashlib
import json
import os as os
import struct
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_service_helpers import (
    _qualification_v3_public_config,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_verifier_request_recovers_only_post_send_truncated_frame(monkeypatch):
    # PR #1249 review 3744482391: clean EOF after CONSUMED queries the exact verdict.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import verifier_service
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    key = Ed25519PrivateKey.from_private_bytes(b"\x55" * 32)
    config = _qualification_v3_public_config()
    digest_manifest = {
        "cells": [
            {
                "contract": {
                    "decision_id": "a" * 64,
                    "decision_contract_sha256": "b" * 64,
                }
            }
        ]
    }
    raw = canonical_json_bytes(digest_manifest)
    digest = hashlib.sha256(raw).hexdigest()
    challenge = "c" * 64
    measurement = config["trusted"]["verifier_runtime"]["measurement"]
    begin_signed = {
        "manifest_sha256": digest,
        "challenge": challenge,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 7,
        "service_identity": measurement,
    }
    begin = {
        **begin_signed,
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(
            verifier_service.CHALLENGE_DOMAIN + canonical_json_bytes(begin_signed)
        ).hex(),
    }
    calls = []

    def round_trip(*_args, **_kwargs):
        calls.append("round-trip")
        if len(calls) == 1:
            return begin
        raise verifier_service._PostSendTransportError("frame truncated")

    recovered = {"manifest_sha256": digest, "challenge": challenge}
    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)
    monkeypatch.setattr(
        verifier_service,
        "query_verdict",
        lambda **_kwargs: calls.append("query-verdict") or recovered,
    )
    # Stop after proving selection of the persisted exact identity.
    with pytest.raises(ValueError, match="binding mismatch"):
        verifier_service.request_verdict(
            socket_path=Path("authority.sock"),
            manifest=digest_manifest,
            config=config,
            timeout=10,
        )

    assert calls == ["round-trip", "round-trip", "query-verdict"]


def test_verifier_request_does_not_recover_semantic_value_error(monkeypatch):
    # PR #1249 review 3744482391: semantic rejection is never converted into a query.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import verifier_service
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    key = Ed25519PrivateKey.from_private_bytes(b"\x55" * 32)
    config = _qualification_v3_public_config()
    manifest = {"cells": [{"contract": {}}]}
    digest = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
    begin_signed = {
        "manifest_sha256": digest,
        "challenge": "c" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 7,
        "service_identity": config["trusted"]["verifier_runtime"]["measurement"],
    }
    begin = {
        **begin_signed,
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(
            verifier_service.CHALLENGE_DOMAIN + canonical_json_bytes(begin_signed)
        ).hex(),
    }
    replies = iter((begin, ValueError("manifest frame must be a JSON object")))

    def round_trip(*_args, **_kwargs):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)
    monkeypatch.setattr(
        verifier_service,
        "query_verdict",
        lambda **_kwargs: pytest.fail("semantic error queried persisted verdict"),
    )

    with pytest.raises(ValueError, match="manifest frame must be a JSON object"):
        verifier_service.request_verdict(
            socket_path=Path("authority.sock"),
            manifest=manifest,
            config=config,
            timeout=10,
        )


def test_verifier_begin_retries_one_lost_response(monkeypatch):
    # PR #1249 review 3744516421: BEGIN response loss recovers the manifest challenge.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import verifier_service
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    key = Ed25519PrivateKey.from_private_bytes(b"\x55" * 32)
    config = _qualification_v3_public_config()
    manifest = {"cells": [{"contract": {}}]}
    digest = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
    signed = {
        "manifest_sha256": digest,
        "challenge": "c" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 7,
        "service_identity": config["trusted"]["verifier_runtime"]["measurement"],
    }
    begin = {
        **signed,
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(
            verifier_service.CHALLENGE_DOMAIN + canonical_json_bytes(signed)
        ).hex(),
    }
    replies = iter(
        (
            verifier_service._PostSendTransportError("response lost"),
            begin,
            ValueError("semantic stop"),
        )
    )
    requests = []

    def round_trip(_path, request, _config, _timeout):
        requests.append(request["operation"])
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)

    with pytest.raises(ValueError, match="semantic stop"):
        verifier_service.request_verdict(
            socket_path=Path("verifier.sock"),
            manifest=manifest,
            config=config,
            timeout=10,
        )

    assert requests == ["begin-exact-14", "begin-exact-14", "verify-exact-14"]


def test_receipt_client_retries_one_lost_response(monkeypatch):
    # PR #1249 review 3744516423: immutable stateless signing survives response loss.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from benchmarks.codegraph_compare import receipt_v3_service as service
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    config = _qualification_v3_public_config()
    key = Ed25519PrivateKey.from_private_bytes(b"\x11" * 32)
    response = {
        "job_id": "7" * 64,
        "receipt": {"signed": True},
        "service_identity": config["trusted"]["executor_runtime"]["measurement"],
    }
    reply = {
        "response": response,
        "key_id": config["executor"]["key_id"],
        "algorithm": "Ed25519",
        "signature": key.sign(
            service.SERVICE_RESPONSE_DOMAIN + canonical_json_bytes(response)
        ).hex(),
    }
    frames = iter((ValueError("frame truncated"), reply))
    sockets = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        item = FakeSocket()
        sockets.append(item)
        return item

    def frame(*_args):
        value = next(frames)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    monkeypatch.setattr(service, "_frame", frame)

    receipt = service.request_receipt(
        role="executor",
        socket_path=Path("executor.sock"),
        authority_response={"response": {"job_id": "7" * 64}},
        config=config,
        timeout=10,
    )

    assert receipt == {"signed": True}
    assert len(sockets) == 2


def test_receipt_client_does_not_retry_semantic_rejection(monkeypatch):
    # PR #1249 review 3744516423: service semantic errors remain terminal.
    from benchmarks.codegraph_compare import receipt_v3_service as service

    config = _qualification_v3_public_config()
    sockets = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    monkeypatch.setattr(
        service, "_frame", lambda *_args: {"error": "ValueError", "reason": "bad job"}
    )

    with pytest.raises(ValueError, match="service rejected job: bad job"):
        service.request_receipt(
            role="executor",
            socket_path=Path("executor.sock"),
            authority_response={"response": {"job_id": "7" * 64}},
            config=config,
            timeout=10,
        )

    assert len(sockets) == 1


def test_receipt_client_bounds_response_loss_retry(monkeypatch):
    # PR #1249 review 3744516423: persistent response loss gets only one retry.
    from benchmarks.codegraph_compare import receipt_v3_service as service

    config = _qualification_v3_public_config()
    sockets = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    monkeypatch.setattr(
        service,
        "_frame",
        lambda *_args: (_ for _ in ()).throw(ValueError("frame truncated")),
    )

    with pytest.raises(service._PostSendTransportError):
        service.request_receipt(
            role="executor",
            socket_path=Path("executor.sock"),
            authority_response={"response": {"job_id": "7" * 64}},
            config=config,
            timeout=10,
        )

    assert len(sockets) == 2


def test_receipt_client_retries_connect_failure_with_original_deadline(monkeypatch):
    # PR #1249 review 3744853007: transient pre-send failures get one bounded retry.
    from benchmarks.codegraph_compare import receipt_v3_service as service

    config = _qualification_v3_public_config()
    sockets = []
    observed_timeouts = []
    ticks = iter((100.0, 101.0, 102.0, 103.0, 104.0))

    class FakeSocket:
        def settimeout(self, timeout):
            observed_timeouts.append(timeout)

        def connect(self, _path):
            if len(sockets) == 1:
                raise ConnectionRefusedError("not listening")

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            pass

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(service, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    monkeypatch.setattr(
        service, "_frame", lambda *_args: {"error": "ValueError", "reason": "bad job"}
    )

    with pytest.raises(ValueError, match="service rejected job: bad job"):
        service.request_receipt(
            role="executor",
            socket_path=Path("executor.sock"),
            authority_response={"response": {"job_id": "7" * 64}},
            config=config,
            timeout=10,
        )

    assert observed_timeouts == [9.0, 7.0]
    assert len(sockets) == 2


def test_receipt_client_retries_ambiguous_send_failure_once(monkeypatch):
    # PR #1249 review 3744853007: stateless signing makes a partial send retry safe.
    from benchmarks.codegraph_compare import receipt_v3_service as service

    config = _qualification_v3_public_config()
    sockets = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 123, config["executor"]["peer_uid"], 123)

        def sendall(self, _payload):
            raise BrokenPipeError("partial frame")

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def socket_factory(*_args):
        sockets.append(FakeSocket())
        return sockets[-1]

    monkeypatch.setattr(service.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(service.socket, "socket", socket_factory)
    with pytest.raises(service._SendTransportError, match="transmission failed"):
        service.request_receipt(
            role="executor",
            socket_path=Path("executor.sock"),
            authority_response={"response": {"job_id": "7" * 64}},
            config=config,
            timeout=10,
        )

    assert len(sockets) == 2


def test_decision_client_retries_one_presend_failure(monkeypatch):
    # PR #1249 review 3744776122: a zero-byte failure cannot imply consumption.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    attempts = []
    reply = {"durable": True}

    class FakeSocket:
        def __init__(self):
            self.number = len(attempts)
            attempts.append(self.number)

        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            if self.number == 0:
                raise ConnectionRefusedError("not listening")

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 1, config["decision_consumer"]["peer_uid"], 1)

        def send(self, payload):
            return len(payload)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", lambda *_args: reply)
    monkeypatch.setattr(
        consumer, "_verify_decision_receipt", lambda value, *_args: value
    )

    result = consumer.request_decision(
        socket_path=Path("/unused"),
        contract={"decision_id": "a" * 64},
        envelope={},
        config=config,
        timeout=1,
    )

    assert result == reply
    assert attempts == [0, 1]


def test_decision_client_queries_ambiguous_send_before_retrying_consume(monkeypatch):
    # PR #1249 review 3744776122: not-found recovery permits one bounded retry.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    operations = []
    replies = iter(
        (
            EOFError("lost consume response"),
            {"status": "not-found"},
            {"durable": True},
        )
    )

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 1, config["decision_consumer"]["peer_uid"], 1)

        def send(self, framed):
            operations.append(json.loads(framed[4:])["operation"])
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def read_reply(*_args):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)
    monkeypatch.setattr(
        consumer, "_verify_decision_receipt", lambda value, *_args: value
    )

    result = consumer.request_decision(
        socket_path=Path("/unused"),
        contract={"decision_id": "a" * 64},
        envelope={},
        config=config,
        timeout=1,
    )

    assert result == {"durable": True}
    assert operations == ["consume-decision", "query-decision", "consume-decision"]


def test_decision_client_polls_in_progress_ambiguous_consume(monkeypatch):
    # PR #1249 review 3745125493: a delivered consume may still be verifying.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    operations = []
    replies = iter(
        (
            EOFError("lost consume response"),
            {"status": "in-progress"},
            {"status": "consumed", "receipt": {"durable": True}},
        )
    )

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 1, config["decision_consumer"]["peer_uid"], 1)

        def send(self, framed):
            operations.append(json.loads(framed[4:])["operation"])
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def read_reply(*_args):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)
    monkeypatch.setattr(consumer.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        consumer, "_verify_decision_receipt", lambda value, *_args: value
    )

    result = consumer.request_decision(
        socket_path=Path("/unused"),
        contract={"decision_id": "a" * 64},
        envelope={},
        config=config,
        timeout=1,
    )

    assert result == {"durable": True}
    assert operations == ["consume-decision", "query-decision", "query-decision"]


def test_decision_client_recovers_receipt_after_retry_reports_consumed(monkeypatch):
    # PR #1249 review 3745125493: replay races must never lose a durable receipt.
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    operations = []
    replies = iter(
        (
            EOFError("lost consume response"),
            {"status": "not-found"},
            {"error": "ValueError", "reason": "decision already consumed"},
            {"status": "in-progress"},
            {"status": "consumed", "receipt": {"durable": True}},
        )
    )

    class FakeSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def getsockopt(self, _level, _option, _size):
            return struct.pack("3i", 1, config["decision_consumer"]["peer_uid"], 1)

        def send(self, framed):
            operations.append(json.loads(framed[4:])["operation"])
            return len(framed)

        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def read_reply(*_args):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(consumer.socket, "SO_PEERCRED", 1, raising=False)
    monkeypatch.setattr(consumer.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(consumer, "read_frame", read_reply)
    monkeypatch.setattr(consumer.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        consumer, "_verify_decision_receipt", lambda value, *_args: value
    )

    result = consumer.request_decision(
        socket_path=Path("/unused"),
        contract={"decision_id": "a" * 64},
        envelope={},
        config=config,
        timeout=1,
    )

    assert result == {"durable": True}
    assert operations == [
        "consume-decision",
        "query-decision",
        "consume-decision",
        "query-decision",
        "query-decision",
    ]


def test_verifier_begin_retries_pre_send_failure_under_original_deadline(monkeypatch):
    # PR #1249 review 3744915230: BEGIN connect failure is safe to retry once.
    from benchmarks.codegraph_compare import verifier_service

    requests: list[tuple[str, float]] = []
    ticks = iter((100.0, 101.0, 105.0))
    monkeypatch.setattr(
        verifier_service, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )

    def round_trip(_path, request, _config, timeout):
        requests.append((request["operation"], timeout))
        if len(requests) == 1:
            raise verifier_service._PreSendTransportError("not connected")
        raise RuntimeError("bounded retry observed")

    monkeypatch.setattr(verifier_service, "_round_trip", round_trip)

    with pytest.raises(RuntimeError, match="bounded retry observed"):
        verifier_service.request_verdict(
            socket_path=Path("/verifier.sock"),
            manifest={"cells": []},
            config={},
            timeout=10,
        )

    assert requests == [("begin-exact-14", 9.0), ("begin-exact-14", 5.0)]


_mark_posix_qualification_section_tests()
