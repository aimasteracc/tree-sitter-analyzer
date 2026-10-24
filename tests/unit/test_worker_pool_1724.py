"""#1724: the extraction pool must not hang in an MCP stdio server.

A full re-extraction inside a long-lived MCP server on Windows started 12
spawn-pool workers that never ran a task. Each one was blocked in
``Py_InitializeFromConfig`` → ``lseek`` → ``NtQueryInformationFile`` on the
stdin pipe it inherited, because the server's reader thread had a synchronous
read pending on that same pipe. Workers now get a ``NUL`` stdin, and the parent
waits for results only up to a bound, so a stall raises a typed error instead
of hanging the call.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from multiprocessing import get_context
from typing import IO, cast

import pytest

from tree_sitter_analyzer.cache import worker_pool


def _rpc(process: subprocess.Popen, message: dict) -> None:
    stdin = cast(IO[bytes], process.stdin)
    stdin.write((json.dumps(message) + "\n").encode("utf-8"))
    stdin.flush()


@pytest.mark.slow_ok
@pytest.mark.skipif(
    os.name != "nt", reason="the inherited-pipe deadlock is Windows-only"
)
def test_mcp_stdio_server_index_with_a_worker_pool_returns(tmp_path) -> None:
    # The real shape: an MCP stdio server whose stdin is the client's pipe runs a
    # project index that uses the spawn pool (TSA_INDEX_WORKERS=2).
    project = tmp_path / "project"
    project.mkdir()
    for index in range(12):
        (project / f"m{index}.py").write_text(
            f"def f{index}():\n    return {index}\n", encoding="utf-8"
        )
    env = {
        **os.environ,
        "TSA_INDEX_WORKERS": "2",
        "TSA_TOOL_DEFINITION_CACHE_DIR": "off",
    }
    env.pop("PYTHONPATH", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from tree_sitter_analyzer.mcp.server import main_sync; main_sync()",
            "--project-root",
            str(project),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=str(project),
        env=env,
    )
    replies: list[dict] = []

    def read() -> None:
        for line in cast(IO[bytes], process.stdout):
            try:
                replies.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        _rpc(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-1724", "version": "1"},
                },
            },
        )
        _rpc(
            process,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        _rpc(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "index",
                    "arguments": {"action": "cache", "mode": "index"},
                },
            },
        )
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline and not any(
            r.get("id") == 2 for r in replies
        ):
            time.sleep(0.2)
        answer = next((r for r in replies if r.get("id") == 2), None)
        assert answer is not None, "index call hung behind the worker pool (#1724)"
        assert "error" not in answer
    finally:
        process.kill()
        process.wait(timeout=30)


def test_stalled_pool_fails_loudly_within_its_bound() -> None:
    began = time.monotonic()
    with pytest.raises(
        worker_pool.WorkerPoolStalled, match="INDEX_WORKER_POOL_STALLED"
    ):
        worker_pool.run_pool(
            get_context("spawn"), 1, None, time.sleep, [60], first_result_seconds=3
        )
    # Bounded (spawn start-up plus the 3 s bound), not the 60 s task.
    assert time.monotonic() - began < 45


def test_pool_returns_every_result() -> None:
    results = worker_pool.run_pool(get_context("spawn"), 2, None, abs, [-3, -1, -2])

    assert sorted(results) == [1, 2, 3]


class _FakeWorker:
    def __init__(self, pid: int, fail: bool = False) -> None:
        self._pid = pid
        self._fail = fail
        self.pid: int | None = None

    def start(self) -> None:
        if self._fail:
            raise OSError("CreateProcess failed")
        self.pid = self._pid


def test_concurrent_start_starts_every_worker() -> None:
    workers = [_FakeWorker(pid) for pid in (11, 12, 13)]

    started, error = worker_pool._start_concurrently(workers)

    assert error is None
    assert [w.pid for w in started] == [11, 12, 13]


def test_concurrent_start_returns_started_workers_and_the_failure() -> None:
    workers = [_FakeWorker(21), _FakeWorker(22, fail=True), _FakeWorker(23)]

    started, error = worker_pool._start_concurrently(workers)

    assert isinstance(error, OSError)
    assert [w.pid for w in started] == [21, 23]


def test_concurrent_start_failure_leaves_started_workers_in_the_pool() -> None:
    pool: list = []
    created = iter([_FakeWorker(31), _FakeWorker(32, fail=True)])

    def factory(ctx, target, args):  # mirrors ``Pool.Process(ctx, ...)``
        worker = next(created)
        worker.name = "Process-1"
        worker.daemon = False
        return worker

    with pytest.raises(OSError):
        worker_pool._ConcurrentStartPool._repopulate_pool_static(
            None, factory, 2, pool, None, None, None, (), None, False
        )

    # Pool.__init__ terminates and joins whatever is in ``pool`` on failure.
    assert [w.pid for w in pool] == [31]
    assert pool[0].daemon is True
    assert pool[0].name == "PoolWorker-1"


def test_non_context_objects_still_build_their_own_pool() -> None:
    calls: list = []

    class _Ctx:
        def Pool(self, processes, initializer):  # noqa: N802 - mirrors the API
            calls.append((processes, initializer))
            return "pool"

    assert worker_pool._make_pool(_Ctx(), 3, None) == "pool"
    assert calls == [(3, None)]


def test_real_context_gets_concurrently_started_daemon_workers() -> None:
    pool = worker_pool._make_pool(get_context("spawn"), 2, None)
    try:
        assert isinstance(pool, worker_pool._ConcurrentStartPool)
        workers = list(pool._pool)  # type: ignore[attr-defined]
        assert len(workers) == 2
        assert all(w.daemon and "PoolWorker" in w.name for w in workers)
        assert sorted(pool.map(abs, [-1, -2])) == [1, 2]
    finally:
        pool.terminate()
        pool.join()


def test_bounds_from_environment(monkeypatch) -> None:
    monkeypatch.setenv(worker_pool.ENV_VAR, "7.5")
    assert worker_pool._bounds() == (7.5, 7.5)
    monkeypatch.setenv(worker_pool.ENV_VAR, "not-a-number")
    assert worker_pool._bounds() == (
        worker_pool.FIRST_RESULT_SECONDS,
        worker_pool.RESULT_SECONDS,
    )


@pytest.mark.skipif(os.name != "nt", reason="standard handles are swapped on Windows")
def test_std_handles_are_restored_after_the_pool_starts() -> None:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    before = (
        kernel32.GetStdHandle(-10 & 0xFFFFFFFF),
        kernel32.GetStdHandle(-11 & 0xFFFFFFFF),
    )
    with worker_pool.isolated_std_handles():
        inside = kernel32.GetStdHandle(-10 & 0xFFFFFFFF)
    after = (
        kernel32.GetStdHandle(-10 & 0xFFFFFFFF),
        kernel32.GetStdHandle(-11 & 0xFFFFFFFF),
    )

    assert inside != before[0]
    assert after == before
