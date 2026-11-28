"""RFC-0042 P1b: renew the certified lease before its TTL while the server is active.

The snapshot registry drops a lease 35 s after its last capture, so the next
query after an idle gap captures again (334 ms on ``rich``). The loader renews
the lease shortly before the TTL ends, with the same capture a request would
run, but only while a request arrived in the last ``ACTIVE_SECONDS``; an idle
server stops spending CPU and resumes on the next request. These tests use a
fake load and a fake renewal; the real lease is in
``tests/integration/test_resident_lease_renewal.py``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import index_snapshot
from tree_sitter_analyzer.resident import loader


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(loader.ENV_VAR, raising=False)
    monkeypatch.setattr(index_snapshot, "_TTL_SECONDS", 0.4)
    monkeypatch.setattr(loader, "RENEW_MARGIN_SECONDS", 0.2)
    monkeypatch.setattr(loader, "MIN_RENEW_SECONDS", 0.05)
    loader.reset()
    loader.enable()
    yield
    loader.shutdown(timeout=10)
    loader.reset()


class _Renewals:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail
        self._lock = threading.Lock()

    def __call__(self, _root: str) -> str | None:
        with self._lock:
            self.calls += 1
        if self.fail:
            raise OSError("capture failed")
        return None

    def count(self) -> int:
        with self._lock:
            return self.calls


def _certified_load(_root: str) -> dict[str, Any]:
    return {"state": "ready", "certified": None, "lease_seconds": 0.0}


def _install(
    monkeypatch: pytest.MonkeyPatch, renewals: _Renewals, load: Any = None
) -> None:
    monkeypatch.setattr(loader, "load", load or _certified_load)
    monkeypatch.setattr(loader, "_renew_once", renewals)


def _until(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_the_lease_is_renewed_before_the_ttl_while_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renewals = _Renewals()
    _install(monkeypatch, renewals)
    assert loader.start(str(tmp_path)) is True
    assert loader.wait(str(tmp_path), timeout=5)  # the load, not the renewal loop
    assert _until(
        lambda: renewals.count() >= 3
    )  # ratchet: nondeterministic timer count
    status = loader.status(str(tmp_path))
    assert status["state"] == "ready"
    assert status["renewals"] >= 3  # ratchet: nondeterministic timer count
    assert status["renewal"] == "renewed"


def test_an_idle_server_stops_renewing_and_resumes_on_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loader, "ACTIVE_SECONDS", 0.5)
    renewals = _Renewals()
    _install(monkeypatch, renewals)
    assert loader.start(str(tmp_path)) is True
    time.sleep(1.2)  # past the active window
    idle = renewals.count()
    time.sleep(0.8)
    assert renewals.count() == idle, "an idle server must not renew"

    def active_again() -> bool:
        loader.touch(str(tmp_path))  # requests arrive again
        return renewals.count() > idle

    assert _until(active_again)


def test_no_renewal_when_the_load_did_not_certify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renewals = _Renewals()

    def uncertified(_root: str) -> dict[str, Any]:
        return {"state": "ready", "certified": "CALL_GRAPH_INCOMPLETE"}

    _install(monkeypatch, renewals, uncertified)
    assert loader.start(str(tmp_path)) is True
    assert loader.wait(str(tmp_path), timeout=5)
    time.sleep(0.6)
    assert renewals.count() == 0


@pytest.mark.parametrize("state", ["skipped", "failed"])
def test_no_renewal_after_a_skipped_or_failed_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    renewals = _Renewals()
    _install(monkeypatch, renewals, lambda _r: {"state": state, "reason": "X"})
    assert loader.start(str(tmp_path)) is True
    assert loader.wait(str(tmp_path), timeout=5)
    time.sleep(0.6)
    assert renewals.count() == 0


def test_a_failing_renewal_is_reported_and_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renewals = _Renewals(fail=True)
    _install(monkeypatch, renewals)
    assert loader.start(str(tmp_path)) is True
    assert _until(
        lambda: renewals.count() >= 2
    )  # ratchet: nondeterministic timer count
    assert loader.status(str(tmp_path))["renewal"] == "failed:OSError"


def test_shutdown_stops_the_renewal_loop_promptly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(index_snapshot, "_TTL_SECONDS", 60.0)
    renewals = _Renewals()
    _install(monkeypatch, renewals)
    assert loader.start(str(tmp_path)) is True
    assert loader.wait(str(tmp_path), timeout=5)
    started = time.perf_counter()
    assert loader.shutdown(timeout=5) is True
    assert time.perf_counter() - started < 2
    assert renewals.count() == 0


def test_touch_before_start_and_for_unknown_roots_is_harmless(tmp_path: Path) -> None:
    loader.touch(None)
    loader.touch("")
    loader.touch(str(tmp_path))
    assert loader.status(str(tmp_path)) is None


def test_every_server_entry_point_counts_as_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("mcp")
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

    touched: list[str | None] = []
    monkeypatch.setattr(loader, "touch", touched.append)
    monkeypatch.setattr(loader, "start", lambda _root: False)
    TreeSitterAnalyzerMCPServer(str(tmp_path)).start_resident()
    assert touched == [str(tmp_path)]


def test_the_renewal_interval_leaves_room_for_the_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(index_snapshot, "_TTL_SECONDS", 35.0)
    monkeypatch.setattr(loader, "RENEW_MARGIN_SECONDS", 5.0)
    monkeypatch.setattr(loader, "MIN_RENEW_SECONDS", 1.0)
    assert loader._renew_interval(0.0) == pytest.approx(30.0)
    assert loader._renew_interval(2.5) == pytest.approx(27.5)
    assert loader._renew_interval(100.0) == pytest.approx(1.0)  # never a busy loop
