"""Issue #1376：test_benchmark_harness_receipt_transport 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

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


def test_receipt_client_retries_one_lost_response(monkeypatch):
    # PR #1249 review 3744516423: 不可变的无状态签名可承受响应丢失。
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
    # PR #1249 review 3744516423: 服务语义错误仍属于终态。
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
    # PR #1249 review 3744516423: 持续响应丢失只能重试一次。
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
    # PR #1249 review 3744853007: 发送前的瞬态失败只允许一次受限重试。
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
    # PR #1249 review 3744853007: 无状态签名使部分发送后的重试保持安全。
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


_mark_posix_qualification_section_tests()
