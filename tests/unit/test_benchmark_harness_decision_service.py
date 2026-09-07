"""Issue #1376：test_benchmark_harness_decision_service 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import os
import sys
from functools import partial
from pathlib import Path

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


def test_decision_consumer_recomputes_ordered_exact14_config_plan_binding():
    # PR #1249 review 3744261026: 直接消费者也必须执行 root 配置中的计划约束。
    from benchmarks.codegraph_compare.decision_consumer_service import (
        verify_configured_plan_set,
    )
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes
    from benchmarks.codegraph_compare.setup_qualification_plan import EXPECTED_CELLS

    hashes = [f"{ordinal:064x}" for ordinal in range(1, 15)]
    plan_set_hash = hashlib.sha256(canonical_json_bytes(hashes)).hexdigest()
    contract = {
        "plan_set_hash": plan_set_hash,
        "cells": [
            {"repo_id": repo, "arm_id": arm, "plan_sha256": digest}
            for (repo, arm), digest in zip(EXPECTED_CELLS, hashes, strict=True)
        ],
    }
    config = {
        "trusted": {
            "plan_set_hash": plan_set_hash,
            "plan_hashes": {
                f"{repo}/{arm}": digest
                for (repo, arm), digest in zip(EXPECTED_CELLS, hashes, strict=True)
            },
        }
    }

    verify_configured_plan_set(contract, config)
    contract["cells"][13]["plan_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="root-config authorized"):
        verify_configured_plan_set(contract, config)


def test_decision_consumer_contains_four_malformed_connections_and_recovers(
    monkeypatch,
):
    # PR #1249 review 3744358507: 单连接失败不能耗尽工作线程。
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    class Connection:
        def __init__(self, send_error=False):
            self.closed = False
            self.sent = []
            self.send_error = send_error

        def sendall(self, payload):
            if self.send_error:
                raise BrokenPipeError("peer disconnected")
            self.sent.append(payload)

        def close(self):
            self.closed = True

    key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x11" * 32)
    connections = [
        Connection(),
        Connection(),
        Connection(),
        Connection(send_error=True),
    ]
    read_results = iter(
        (
            EOFError("truncated header"),
            ValueError("oversized frame"),
            ValueError("malformed JSON"),
            {"operation": "query-decision"},
        )
    )
    monkeypatch.setattr(consumer, "peer_allowed", lambda *_args: None)

    def read_request(*_args):
        result = next(read_results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(consumer, "read_frame", read_request)
    monkeypatch.setattr(consumer, "consume_request", lambda *_args: {"ok": True})
    for connection in connections:
        consumer._serve_connection(connection, 901, {}, object(), key, {})

    healthy = Connection()
    monkeypatch.setattr(consumer, "read_frame", lambda *_args: {"operation": "query"})
    consumer._serve_connection(healthy, 901, {}, object(), key, {})

    assert [connection.closed for connection in connections] == [True, True, True, True]
    assert healthy.closed is True
    assert len(healthy.sent) == 1


def test_decision_consumer_contains_peer_and_handler_errors(monkeypatch):
    # PR #1249 review 3744358507: SO_PEERCRED 和处理器错误必须仅影响当前连接。
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    class Connection:
        def __init__(self):
            self.closed = False
            self.sent = []

        def sendall(self, payload):
            self.sent.append(payload)

        def close(self):
            self.closed = True

    key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x12" * 32)
    denied = Connection()
    monkeypatch.setattr(
        consumer,
        "peer_allowed",
        lambda *_args: (_ for _ in ()).throw(PermissionError("wrong UID")),
    )
    consumer._serve_connection(denied, 901, {}, object(), key, {})

    handled = Connection()
    monkeypatch.setattr(consumer, "peer_allowed", lambda *_args: None)
    monkeypatch.setattr(consumer, "read_frame", lambda *_args: {})
    monkeypatch.setattr(
        consumer,
        "consume_request",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad decision")),
    )
    consumer._serve_connection(handled, 901, {}, object(), key, {})

    assert denied.closed is True
    assert denied.sent == []
    assert handled.closed is True
    assert len(handled.sent) == 1


def test_decision_consumer_rejects_wrong_private_key_before_ledger_or_listener(
    tmp_path: Path, monkeypatch
):
    # PR #1249 review 3744358513: 错误密钥不能污染一次性账本。
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    public = tmp_path / "public.json"
    public.write_bytes(b"{}")
    launch_attestation = tmp_path / "launch.json"
    launch_attestation.write_bytes(b"{}")
    configured_key = __import__(
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        fromlist=["Ed25519PrivateKey"],
    ).Ed25519PrivateKey.from_private_bytes(b"\x66" * 32)
    monkeypatch.setattr(consumer.os, "geteuid", lambda: 904)
    monkeypatch.setattr(
        consumer,
        "parse_public_config",
        lambda _raw: {
            "decision_consumer": {
                "peer_uid": 904,
                "public_key_hex": configured_key.public_key().public_bytes_raw().hex(),
            },
            "trusted": {"decision_consumer_runtime": {"measurement": {}}},
        },
    )
    monkeypatch.setattr(consumer, "measure_runtime", lambda _value: {})
    monkeypatch.setattr(consumer, "wait_for_launch_release", lambda *_args: b"{}")
    monkeypatch.setattr(
        consumer, "verify_service_launch_attestation", lambda *_args: {}
    )
    descriptor = os.open(os.devnull, os.O_RDONLY)
    monkeypatch.setattr(
        consumer, "secure_key", lambda *_args: (descriptor, b"\x65" * 32)
    )
    monkeypatch.setattr(
        consumer,
        "DecisionLedger",
        lambda *_args: (_ for _ in ()).throw(AssertionError("ledger opened")),
    )

    with pytest.raises(SystemExit, match="does not match public config"):
        consumer.main(
            [
                "--socket",
                str(tmp_path / "decision.sock"),
                "--private-key",
                str(tmp_path / "key"),
                "--public-config",
                str(public),
                "--ledger",
                str(tmp_path / "ledger.sqlite"),
                "--launch-attestation",
                str(launch_attestation),
                "--launch-release",
                str(tmp_path / "RELEASE"),
                "--allowed-client-uid",
                "901",
            ]
        )


def test_decision_consumer_rejects_stale_verifier_runtime_identity():
    # PR #1249 review 3744516428: verdict 的运行时身份必须匹配 root 签名配置。
    from benchmarks.codegraph_compare import decision_consumer_service as consumer

    config = _qualification_v3_public_config()
    contract = {"decision_id": "d" * 64}
    envelope = {
        "manifest_sha256": "a" * 64,
        "decision_id": "d" * 64,
        "decision_contract_sha256": hashlib.sha256(
            consumer.canonical_json_bytes(contract)
        ).hexdigest(),
        "challenge": "b" * 64,
        "ledger_counter": 1,
        "ledger_prev_hash": "0" * 64,
        "issued_at_ns": 1,
        "verdict": {},
        "service_identity": {"stale": True},
        "consumption_record": {},
        "ledger_head": {},
        "key_id": config["verifier"]["key_id"],
        "algorithm": "Ed25519",
        "signature": "0" * 128,
    }

    with pytest.raises(ValueError, match="verifier identity mismatch"):
        consumer.verify_verdict_envelope(envelope, contract, config)


_mark_posix_qualification_section_tests()
