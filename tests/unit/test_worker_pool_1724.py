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

import pytest

from tree_sitter_analyzer.cache import worker_pool


def _rpc(process: subprocess.Popen, message: dict) -> None:
    assert process.stdin is not None
    process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
    process.stdin.flush()


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
        assert process.stdout is not None
        for line in process.stdout:
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
