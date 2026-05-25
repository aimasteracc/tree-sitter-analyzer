"""E2E test framework: spawn a real MCP server, drive it via JSON-RPC.

This module is the single contract every E2E test imports against. Keep
the public surface small and stable — downstream test suites
(``test_today_bugs_regression.py``, ``test_real_repos.py``,
``test_mcp_smoke.py``) all rely on it.

Public fixtures
---------------

``clone_repo_factory`` (session-scoped)
    Shallow-clones a public git repo once per test session and returns its
    local ``Path``. Automatically skips the calling test if the clone fails
    (network unavailable, git not installed, etc.). Safe to call repeatedly
    with the same ``(url, name)`` pair — the clone is cached.

``mcp_server`` (function-scoped)
    Spawns the MCP server as a subprocess against the current TSA
    checkout, parametrised over the project root. Returns an
    :class:`MCPClient` wrapper with methods ``initialize()``,
    ``list_tools()``, ``call(tool_name, arguments)``,
    ``stderr_text()``, ``terminate()``. Tests must call
    ``initialize()`` themselves so they can introspect the handshake
    response.

``mcp_server_factory`` (function-scoped)
    Lower-level factory for tests that need multiple servers,
    custom env vars, or non-default Python executable. Returns a
    callable: ``factory(project_root, env=None) -> MCPClient``.
    Each constructed client is auto-terminated at test teardown.

Design notes
------------

* **stdout is the JSON-RPC channel** — the test framework must NOT
  print to stdout from the server side. TSA's logger defaults to
  stderr; we sanity-check that in ``test_mcp_smoke``.
* **Framing is newline-delimited JSON** — MCP SDK 1.x sends one
  UTF-8 JSON object per line terminated by ``\\n``. Earlier 0.x SDKs
  used LSP Content-Length framing; we require mcp>=1.9 so that is
  not supported here.
* **stderr is drained in a background thread** so the kernel pipe
  buffer never fills and blocks the server. Tests access the
  accumulated stderr via ``stderr_text()``.
* **Each spawn is a clean subprocess** — no shared state between
  tests. Slow but predictable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Default time the test framework will wait for a single JSON-RPC
# response. Tools that legitimately take longer should pass an
# explicit ``timeout`` to ``MCPClient.call``.
DEFAULT_CALL_TIMEOUT_SEC = 30.0

# Time the framework gives the server to send its first response
# after spawn. If the server doesn't respond to ``initialize`` within
# this window, we declare the spawn dead.
DEFAULT_HANDSHAKE_TIMEOUT_SEC = 30.0


# ---------------------------------------------------------------------------
# Wire helpers — MCP 1.x newline-delimited JSON transport
#
# MCP SDK ≥ 1.0 uses one JSON object per line (no Content-Length header).
# Earlier (0.x) SDKs used LSP-style framing; we dropped that since TSA
# requires mcp>=1.9.  The wire format is: send UTF-8 JSON + "\n", receive
# UTF-8 JSON + "\n".  Notifications from the server (method, no id) arrive
# on the same channel and must be consumed/skipped by _recv_response.
# ---------------------------------------------------------------------------


def _frame(payload: bytes) -> bytes:
    """Append a newline to ``payload`` for the MCP 1.x stdio transport."""
    return payload + b"\n"


def _read_line(stream: Any, timeout: float) -> bytes:
    """Read one newline-terminated JSON line from ``stream``.

    Uses ``select`` for non-blocking polling so the deadline is respected
    even when the server is silent. Raises :class:`TimeoutError` if no
    complete line arrives within ``timeout`` seconds.
    """
    import select as _select

    deadline = time.monotonic() + timeout
    buf = b""
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # Poll with a short slice so we re-check the deadline frequently.
        poll_sec = min(remaining, 0.1)
        rlist, _, _ = _select.select([stream], [], [], poll_sec)
        if not rlist:
            continue
        chunk = stream.read(1)
        if not chunk:
            # EOF — server exited before replying.
            raise RuntimeError("MCP server closed stdout before sending a response")
        buf += chunk
        if buf.endswith(b"\n"):
            return buf.rstrip(b"\n")
    raise TimeoutError(
        f"MCP server did not send a complete JSON line within {timeout}s; "
        f"partial buffer: {buf[:200]!r}"
    )


# ---------------------------------------------------------------------------
# Client wrapper
# ---------------------------------------------------------------------------


@dataclass
class MCPClient:
    """Test-side handle on a spawned TSA MCP server subprocess."""

    proc: subprocess.Popen[bytes]
    project_root: Path
    _stderr_buf: bytearray = field(default_factory=bytearray)
    _stderr_lock: threading.Lock = field(default_factory=threading.Lock)
    _stderr_thread: threading.Thread | None = None
    _next_id: int = 1
    _initialized: bool = False

    def __post_init__(self) -> None:
        # Drain stderr in a background thread so the kernel pipe
        # never blocks the server. We deliberately read raw bytes
        # and only decode on access — exactly the contract violated
        # by the cp932 bug (PR #153 errata).
        stderr = self.proc.stderr
        assert stderr is not None

        def drain() -> None:
            try:
                while True:
                    chunk = stderr.read(4096)
                    if not chunk:
                        return
                    with self._stderr_lock:
                        self._stderr_buf.extend(chunk)
            except (ValueError, OSError):
                # Stream closed during shutdown — expected.
                return

        self._stderr_thread = threading.Thread(target=drain, daemon=True)
        self._stderr_thread.start()

    def stderr_text(self) -> str:
        """Return everything the server has written to stderr so far."""
        with self._stderr_lock:
            return self._stderr_buf.decode("utf-8", errors="replace")

    def _send(self, payload: dict[str, Any]) -> None:
        """Serialise and frame a JSON-RPC payload to the server's stdin."""
        stdin = self.proc.stdin
        assert stdin is not None
        encoded = json.dumps(payload).encode("utf-8")
        stdin.write(_frame(encoded))
        stdin.flush()

    def _recv(self, timeout: float) -> dict[str, Any]:
        """Read one JSON-RPC *response* (has an ``id``) from stdout.

        The server may emit notification messages (no ``id``) between
        responses. We loop past notifications and return the first
        message that carries an ``id``.
        """
        stdout = self.proc.stdout
        assert stdout is not None
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"MCP server did not send a response within {timeout}s"
                )
            line = _read_line(stdout, remaining)
            msg = json.loads(line.decode("utf-8"))
            # Skip server-originated notifications (no ``id`` field).
            if "id" in msg:
                return msg

    def initialize(
        self,
        *,
        client_name: str = "tree-sitter-analyzer-e2e",
        client_version: str = "0.0.0",
        timeout: float = DEFAULT_HANDSHAKE_TIMEOUT_SEC,
    ) -> dict[str, Any]:
        """Send ``initialize`` and the ``notifications/initialized`` ack.

        Returns the raw response dict (not just ``result``) so tests
        can inspect both successful responses and JSON-RPC errors.
        """
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": client_name,
                        "version": client_version,
                    },
                },
            }
        )
        response = self._recv(timeout)
        # Per MCP spec, after a successful initialize the client MUST
        # send ``notifications/initialized``. If we skip it, some
        # tools may refuse to operate.
        if "error" not in response:
            self._send(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )
            self._initialized = True
        return response

    def list_tools(
        self, *, timeout: float = DEFAULT_CALL_TIMEOUT_SEC
    ) -> list[dict[str, Any]]:
        """Return the ``tools/list`` array (after a successful initialize)."""
        if not self._initialized:
            raise RuntimeError("call initialize() before list_tools()")
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/list",
                "params": {},
            }
        )
        response = self._recv(timeout)
        if "error" in response:
            raise RuntimeError(f"tools/list failed: {response['error']}")
        return list(response["result"]["tools"])

    def call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float = DEFAULT_CALL_TIMEOUT_SEC,
    ) -> dict[str, Any]:
        """Invoke ``tools/call`` and return the full response dict.

        Returns the raw response so the test can distinguish success
        from JSON-RPC error vs. tool-reported failure. The
        higher-level success convention ("server returned and
        ``response['result']['isError']`` is falsey") is the test
        author's call to enforce.
        """
        if not self._initialized:
            raise RuntimeError("call initialize() before call()")
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments or {},
                },
            }
        )
        return self._recv(timeout)

    def terminate(self, *, timeout: float = 5.0) -> None:
        """Stop the server. Idempotent and best-effort."""
        if self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            try:
                self.proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _spawn_mcp(
    project_root: str | Path,
    env: dict[str, str] | None = None,
    python: str | None = None,
) -> MCPClient:
    """Launch the TSA MCP server for the given project root."""
    root = Path(project_root).resolve()
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    full_env.setdefault("TREE_SITTER_PROJECT_ROOT", str(root))

    python_exe = python or sys.executable
    proc = subprocess.Popen(
        [python_exe, "-m", "tree_sitter_analyzer.mcp.server"],
        cwd=str(REPO_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=full_env,
        bufsize=0,
    )
    return MCPClient(proc=proc, project_root=root)


@pytest.fixture
def mcp_server_factory() -> Iterator[Callable[..., MCPClient]]:
    """Return a factory that lifecycle-manages MCPClient instances.

    Useful for tests that need >1 server (e.g. ``one cold-start +
    one warm-start``) or custom env vars (locale tests).
    """
    clients: list[MCPClient] = []

    def make(
        project_root: str | Path,
        env: dict[str, str] | None = None,
        python: str | None = None,
    ) -> MCPClient:
        client = _spawn_mcp(project_root, env=env, python=python)
        clients.append(client)
        return client

    yield make

    for client in clients:
        client.terminate()


@pytest.fixture
def mcp_server(
    mcp_server_factory: Callable[..., MCPClient],
) -> MCPClient:
    """Default MCP server pointed at the TSA checkout itself.

    For tests that need a different project root or env, prefer
    ``mcp_server_factory`` and call it explicitly.
    """
    return mcp_server_factory(REPO_ROOT)


@pytest.fixture(scope="session")
def clone_repo_factory(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[str, str], Path]:
    """Session-scoped factory: shallow-clone a public git repo once per session.

    Usage::

        def test_something(clone_repo_factory, mcp_server_factory):
            repo_dir = clone_repo_factory("https://github.com/org/repo.git", "repo")
            client = mcp_server_factory(repo_dir)
            ...

    The clone is cached: calling with the same ``name`` a second time returns
    the already-cloned directory without re-cloning. If the clone fails for any
    reason (network unavailable, git not installed, repo gone) the calling test
    is automatically *skipped* rather than erroring, so offline developer
    machines don't break the local test run.
    """
    base: Path = tmp_path_factory.mktemp("real-repos")
    cache: dict[str, Path] = {}

    def _clone(url: str, name: str) -> Path:
        if name in cache:
            return cache[name]

        # Honour a pre-cloned directory supplied by CI to avoid double-cloning.
        env_key = f"E2E_REAL_REPO_{name.upper().replace('-', '_')}"
        pre_cloned = os.environ.get(env_key, "")
        if pre_cloned:
            dest = Path(pre_cloned)
            if dest.is_dir():
                cache[name] = dest
                return dest

        dest = base / name
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", url, str(dest)],
            capture_output=True,
            timeout=120.0,
        )
        if result.returncode != 0:
            pytest.skip(
                f"git clone {url!r} failed — likely offline or repo moved.\n"
                + result.stderr.decode("utf-8", errors="replace")[:300]
            )
        cache[name] = dest
        return dest

    return _clone


# ---------------------------------------------------------------------------
# Convenience helpers (re-exported for test modules)
# ---------------------------------------------------------------------------


def initialized(
    client: MCPClient, *, timeout: float = DEFAULT_HANDSHAKE_TIMEOUT_SEC
) -> MCPClient:
    """Idempotently initialize ``client`` and return it.

    Most tests want the post-handshake state; this saves a line of
    boilerplate. Tests that need to inspect the handshake response
    (e.g. the no-LoggingCapability invariant) still call
    ``client.initialize()`` directly.
    """
    if not client._initialized:
        response = client.initialize(timeout=timeout)
        if "error" in response:
            raise RuntimeError(
                f"MCP initialize failed: {response['error']!r}\n"
                f"stderr so far:\n{client.stderr_text()}"
            )
    return client
