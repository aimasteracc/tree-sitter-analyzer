"""Issue #1376：test_benchmark_harness_decision_transport 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
import os as os
import struct
import sys
from functools import partial
from pathlib import Path

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


def test_decision_client_retries_one_presend_failure(monkeypatch):
    # PR #1249 review 3744776122: 零字节失败不能暗示请求已被消耗。
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
    # PR #1249 review 3744776122: not-found 恢复允许一次受限重试。
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
    # PR #1249 review 3745125493: 已经送达的 consume 请求可能仍在验证。
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
    # PR #1249 review 3745125493: 重放竞争绝不能丢失已持久化的 receipt。
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


_mark_posix_qualification_section_tests()
