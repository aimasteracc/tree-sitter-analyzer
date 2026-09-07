"""Issue #1376：test_benchmark_harness_transport_recovery 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import os as os
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
    # PR #1249 review 3744482391: CONSUMED 之后的正常 EOF 应查询精确的 verdict。
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
    # 证明已选中持久化的精确身份后即停止。
    with pytest.raises(ValueError, match="binding mismatch"):
        verifier_service.request_verdict(
            socket_path=Path("authority.sock"),
            manifest=digest_manifest,
            config=config,
            timeout=10,
        )

    assert calls == ["round-trip", "round-trip", "query-verdict"]


def test_verifier_request_does_not_recover_semantic_value_error(monkeypatch):
    # PR #1249 review 3744482391: 语义拒绝绝不能转成查询。
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
    # PR #1249 review 3744516421: BEGIN 响应丢失后应恢复 manifest 的 challenge。
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


def test_verifier_begin_retries_pre_send_failure_under_original_deadline(monkeypatch):
    # PR #1249 review 3744915230: BEGIN 连接失败可以安全重试一次。
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
