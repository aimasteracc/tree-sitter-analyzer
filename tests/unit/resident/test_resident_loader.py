"""RFC-0042 P1: the resident loader's switch, lifecycle and thread rules.

The loader runs in a daemon thread after the MCP ``initialize`` answer. It must
never block its caller, start at most one load per project root, survive any
failure of the load (requests then take today's path), and stop with the server.
These tests replace the load itself with a controllable fake; the end-to-end
behaviour on a real index is in ``test_resident_identity.py``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.resident import loader


@pytest.fixture(autouse=True)
def _fresh_loader(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(loader.ENV_VAR, raising=False)
    loader.reset()
    loader.enable()
    yield
    loader.shutdown(timeout=10)
    loader.reset()


class _Gate:
    """A fake ``load`` that blocks until released and counts its calls."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.release = threading.Event()
        self.entered = threading.Event()
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self.result = result or {"state": "ready"}

    def __call__(self, project_root: str) -> dict[str, Any]:
        with self._lock:
            self.calls.append(project_root)
        self.entered.set()
        assert self.release.wait(10), "test never released the fake load"
        return dict(self.result)


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, "background"),
        ("", "background"),
        ("background", "background"),
        ("  Background ", "background"),
        ("first-use", "first-use"),
        ("off", "off"),
        ("OFF", "off"),
        ("0", "off"),
        ("false", "off"),
        ("no", "off"),
        ("bogus", "background"),
    ],
)
def test_mode_reads_the_switch(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: str
) -> None:
    if value is None:
        monkeypatch.delenv(loader.ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(loader.ENV_VAR, value)
    assert loader.mode() == expected


@pytest.mark.parametrize("value", ["off", "first-use"])
def test_only_background_mode_starts_a_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    gate = _Gate()
    gate.release.set()
    monkeypatch.setattr(loader, "load", gate)
    monkeypatch.setenv(loader.ENV_VAR, value)
    assert loader.start(str(tmp_path)) is False
    assert loader.wait(timeout=5)
    assert gate.calls == []
    assert loader.status(str(tmp_path)) == {"state": value}


def test_a_process_that_never_enabled_the_loader_never_starts_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One-shot processes (CLI, embedders, tests) keep today's lazy behaviour."""
    gate = _Gate()
    gate.release.set()
    monkeypatch.setattr(loader, "load", gate)
    loader.reset()  # not enabled
    assert loader.start(str(tmp_path)) is False
    assert gate.calls == []


def test_start_without_a_root_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = _Gate()
    monkeypatch.setattr(loader, "load", gate)
    assert loader.start(None) is False
    assert loader.start("") is False
    assert gate.calls == []


def test_start_returns_at_once_while_the_load_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _Gate()
    monkeypatch.setattr(loader, "load", gate)
    started = time.perf_counter()
    assert loader.start(str(tmp_path)) is True
    elapsed = time.perf_counter() - started
    assert gate.entered.wait(5)
    assert elapsed < 0.5, "start() must never wait for the load"
    assert loader.status(str(tmp_path))["state"] == "loading"
    gate.release.set()
    assert loader.wait(str(tmp_path), timeout=10)
    status = loader.status(str(tmp_path))
    assert status["state"] == "ready"
    assert isinstance(status["seconds"], float)


def test_concurrent_starts_run_one_load_per_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _Gate()
    monkeypatch.setattr(loader, "load", gate)
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    barrier = threading.Barrier(16)
    outcomes: list[bool] = []
    lock = threading.Lock()

    def racer(root: Path) -> None:
        barrier.wait()
        started = loader.start(str(root))
        with lock:
            outcomes.append(started)

    threads = [
        threading.Thread(target=racer, args=(root_a if i % 2 else root_b,))
        for i in range(16)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    gate.release.set()
    assert loader.wait(timeout=10)
    assert sorted(gate.calls) == sorted([str(root_a), str(root_b)])
    assert outcomes.count(True) == 2


def test_a_finished_load_is_not_repeated_by_a_later_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``initialized``, ``tools/list`` and every ``tools/call`` call start(); one load."""
    gate = _Gate()
    gate.release.set()
    monkeypatch.setattr(loader, "load", gate)
    assert loader.start(str(tmp_path)) is True
    assert loader.wait(timeout=10)
    for _ in range(5):
        assert loader.start(str(tmp_path)) is False
    assert loader.wait(timeout=10)
    assert len(gate.calls) == 1


def test_a_failing_load_is_reported_and_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_root: str) -> dict[str, Any]:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(loader, "load", broken)
    assert loader.start(str(tmp_path)) is True
    assert loader.wait(timeout=10)
    status = loader.status(str(tmp_path))
    assert status["state"] == "failed"
    assert status["reason"] == "RuntimeError"


def test_shutdown_refuses_new_loads_and_waits_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _Gate()
    monkeypatch.setattr(loader, "load", gate)
    assert loader.start(str(tmp_path)) is True
    assert gate.entered.wait(5)
    started = time.perf_counter()
    assert loader.shutdown(timeout=0.2) is False  # still loading: abandoned
    assert time.perf_counter() - started < 2
    other = tmp_path / "other"
    other.mkdir()
    assert loader.start(str(other)) is False
    gate.release.set()
    assert loader.wait(timeout=10)
    assert gate.calls == [str(tmp_path)]


def test_the_loader_thread_is_a_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[threading.Thread] = []

    def record(_root: str) -> dict[str, Any]:
        seen.append(threading.current_thread())
        return {"state": "ready"}

    monkeypatch.setattr(loader, "load", record)
    assert loader.start(str(tmp_path)) is True
    assert loader.wait(timeout=10)
    assert seen and seen[0].daemon
    assert seen[0] is not threading.main_thread()


# --------------------------------------------------------------------------- #
# Waiting for an in-flight background capture
# --------------------------------------------------------------------------- #


def test_await_capture_is_false_without_a_capture(tmp_path: Path) -> None:
    assert loader.await_capture(str(tmp_path), 1.0) is False


def test_await_capture_waits_for_the_background_capture(tmp_path: Path) -> None:
    root = str(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def capture() -> None:
        with loader.capturing(root):
            entered.set()
            release.wait(10)

    thread = threading.Thread(target=capture, daemon=True)
    thread.start()
    assert entered.wait(5)
    threading.Timer(0.2, release.set).start()
    started = time.perf_counter()
    assert loader.await_capture(root, 5.0) is True
    assert time.perf_counter() - started >= 0.15
    thread.join(5)
    assert loader.await_capture(root, 1.0) is False  # finished: nothing to wait for


def test_await_capture_gives_up_at_the_timeout(tmp_path: Path) -> None:
    root = str(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def capture() -> None:
        with loader.capturing(root):
            entered.set()
            release.wait(10)

    thread = threading.Thread(target=capture, daemon=True)
    thread.start()
    assert entered.wait(5)
    started = time.perf_counter()
    assert loader.await_capture(root, 0.1) is False
    assert time.perf_counter() - started < 2
    release.set()
    thread.join(5)


def test_the_capturing_thread_never_waits_for_itself(tmp_path: Path) -> None:
    root = str(tmp_path)
    with loader.capturing(root):
        started = time.perf_counter()
        assert loader.await_capture(root, 5.0) is False
        assert time.perf_counter() - started < 0.5
