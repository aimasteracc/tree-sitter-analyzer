"""Tests for tree_sitter_analyzer.lsp.client.

Covers: LspClient._start() error paths (unknown language, missing binary),
_reader_loop() happy path, go_to_definition() None results,
cache_lsp_resolution() DB insertion.
Target coverage: ~35-45% of lsp/client.py.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.lsp.client import (
    LspClient,
    LspServerUnavailableError,
    cache_lsp_resolution,
)

# ---------------------------------------------------------------------------
# _start() error paths
# ---------------------------------------------------------------------------


async def test_start_unknown_language():
    """Unsupported language → LspServerUnavailableError before binary lookup."""
    client = LspClient("cobol", "/tmp")
    with pytest.raises(LspServerUnavailableError, match="cobol"):
        await client._start()


async def test_start_missing_binary():
    """Known language but binary not on PATH → LspServerUnavailableError."""
    client = LspClient("python", "/tmp")
    with patch("shutil.which", return_value=None):
        with pytest.raises(LspServerUnavailableError):
            await client._start()


# ---------------------------------------------------------------------------
# _reader_loop() — happy path
# ---------------------------------------------------------------------------


async def test_reader_loop_happy_path(fake_lsp_process):
    """_reader_loop resolves a pending Future when a complete response arrives."""
    client = LspClient("python", "/tmp")
    client._proc = fake_lsp_process

    req_id = 1
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    client._pending[req_id] = fut

    payload = {"jsonrpc": "2.0", "id": req_id, "result": {"data": "ok"}}
    body = json.dumps(payload).encode()
    header = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n"
    fake_lsp_process.stdout.feed_data(header + body)
    fake_lsp_process.stdout.feed_eof()

    await client._reader_loop()
    assert fut.done()
    assert fut.result() == {"data": "ok"}


# ---------------------------------------------------------------------------
# go_to_definition() — returns None for empty results
# ---------------------------------------------------------------------------


async def test_go_to_definition_returns_none_for_none(tmp_path):
    """_request returns None → go_to_definition returns None."""
    client = LspClient("python", str(tmp_path))
    client._request = AsyncMock(return_value=None)
    result = await client.go_to_definition(str(tmp_path / "a.py"), 0, 0)
    assert result is None


async def test_go_to_definition_returns_none_for_empty_list(tmp_path):
    """_request returns [] → go_to_definition returns None."""
    client = LspClient("python", str(tmp_path))
    client._request = AsyncMock(return_value=[])
    result = await client.go_to_definition(str(tmp_path / "a.py"), 0, 0)
    assert result is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_edge(conn) -> int:
    """Insert a minimal edges row and return its rowid."""
    cur = conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, kind) VALUES (?, ?, ?)",
        ("src::a.py::1", "tgt::b.py::1", "calls"),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# cache_lsp_resolution — DB insertion
# ---------------------------------------------------------------------------


def test_cache_lsp_resolution_insert_and_retrieve(ast_cache_conn):
    """cache_lsp_resolution inserts a row into lsp_resolution_cache."""
    edge_id = _seed_edge(ast_cache_conn)
    cache_lsp_resolution(
        ast_cache_conn,
        edge_id=edge_id,
        symbol_id=None,
        resolved_type="str",
        resolved_file="a.py",
        resolved_line=1,
        lsp_server="pyright",
    )
    count = ast_cache_conn.execute(
        "SELECT COUNT(*) FROM lsp_resolution_cache WHERE lsp_server = 'pyright'"
    ).fetchone()[0]
    assert count == 1


class _ProtocolPeer:
    """可控的内存协议对端，仅替换进程传输边界，不替换客户端协议实现。"""

    def __init__(self, target, mode="reply", extra_header=False):
        from types import SimpleNamespace

        self.stdout = asyncio.StreamReader()
        self.stdin = SimpleNamespace(write=self.write)
        self.target = target
        self.mode = mode
        self.extra_header = extra_header
        self.messages = []
        self.returncode = None
        self.terminated = 0
        self.killed = 0

    def write(self, raw):
        header, _, body = raw.partition(b"\r\n\r\n")
        assert int(header.split(b":")[1]) == len(body)
        message = json.loads(body)
        self.messages.append(message)
        if "id" not in message or self.mode == "silent":
            return
        if self.mode == "eof":
            self.stdout.feed_eof()
            return
        if self.mode == "malformed":
            self.stdout.feed_data(b"Content-Length: 1\r\n\r\n{")
            return
        response = {"jsonrpc": "2.0", "id": message["id"]}
        if self.mode == "error":
            response["error"] = {"code": -32603, "message": "peer refused"}
        else:
            response["result"] = (
                {"capabilities": {}}
                if message["method"] == "initialize"
                else {
                    "uri": self.target.as_uri(),
                    "range": {"start": {"line": 0, "character": 2}},
                }
            )
        payload = json.dumps(response).encode()
        extra = (
            b"Content-Type: application/vscode-jsonrpc; charset=utf-8\r\n"
            if self.extra_header
            else b""
        )
        self.stdout.feed_data(
            f"Content-Length: {len(payload)}\r\n".encode() + extra + b"\r\n" + payload
        )

    def terminate(self):
        self.terminated += 1
        self.returncode = -15

    def kill(self):
        self.killed += 1
        self.returncode = -9

    async def wait(self):
        return self.returncode


@pytest.mark.parametrize("extra_header", [False, True])
async def test_protocol_initialize_definition_and_close(
    tmp_path, monkeypatch, extra_header
):
    # PR #1352：初始化、通知、定义查询走真实帧编解码，关闭后没有存活任务/进程。
    import tree_sitter_analyzer.lsp.client as module

    peer = _ProtocolPeer(tmp_path / "target.py", extra_header=extra_header)
    monkeypatch.setattr("shutil.which", lambda _: "fake-lsp")
    monkeypatch.setattr(
        module.asyncio, "create_subprocess_exec", AsyncMock(return_value=peer)
    )
    monkeypatch.setattr(module, "_LSP_TIMEOUT", 0.1)
    client = LspClient("python", str(tmp_path))
    try:
        async with client:
            result = await client.go_to_definition(str(tmp_path / "source.py"), 3, 4)
            assert result == {
                "file": str(tmp_path / "target.py"),
                "line": 0,
                "character": 2,
            }
        assert [m["method"] for m in peer.messages] == [
            "initialize",
            "initialized",
            "textDocument/definition",
        ]
        assert peer.messages[0]["params"]["rootUri"] == tmp_path.as_uri()
        assert peer.messages[2]["params"]["position"] == {"line": 3, "character": 4}
        assert peer.terminated == 1
        assert client._pending == {}
        assert client._reader_task is None or client._reader_task.done()
    finally:
        await client._stop()


async def test_initialize_timeout_cleans_up_started_peer(tmp_path, monkeypatch):
    # PR #1352：__aenter__ 失败也必须回收已经启动的对端。
    import tree_sitter_analyzer.lsp.client as module

    peer = _ProtocolPeer(tmp_path / "target.py", mode="silent")
    monkeypatch.setattr("shutil.which", lambda _: "fake-lsp")
    monkeypatch.setattr(
        module.asyncio, "create_subprocess_exec", AsyncMock(return_value=peer)
    )
    monkeypatch.setattr(module, "_LSP_TIMEOUT", 0.01)
    client = LspClient("python", str(tmp_path))
    try:
        with pytest.raises(module.LspTimeoutError, match="initialize"):
            await client.__aenter__()
        assert peer.terminated == 1
        assert client._pending == {}
        assert client._reader_task is None or client._reader_task.done()
    finally:
        await client._stop()


@pytest.mark.parametrize(
    "mode,error",
    [
        ("eof", "reader failed"),
        ("malformed", "reader failed"),
        ("error", "peer refused"),
    ],
)
async def test_reader_failure_is_not_a_successful_empty_result(
    tmp_path, monkeypatch, mode, error
):
    # PR #1352：EOF、损坏帧和 JSON-RPC error 均不能解析为成功的 None。
    import tree_sitter_analyzer.lsp.client as module

    client = LspClient("python", str(tmp_path))
    client._proc = _ProtocolPeer(tmp_path / "target.py", mode=mode)
    monkeypatch.setattr(module, "_LSP_TIMEOUT", 0.02)
    client._reader_task = asyncio.create_task(client._reader_loop())
    try:
        with pytest.raises(RuntimeError, match=error):
            await client._request("textDocument/definition", {})
        assert client._pending == {}
    finally:
        await client._stop()


async def test_send_failure_does_not_leak_pending_request(tmp_path):
    # PR #1352：发送本身失败时，注册的 Future 也必须撤销。
    client = LspClient("python", str(tmp_path))
    client._proc = _ProtocolPeer(tmp_path / "target.py", mode="silent")

    def broken_write(_):
        raise BrokenPipeError("closed stdin")

    client._proc.stdin.write = broken_write
    with pytest.raises(BrokenPipeError, match="closed stdin"):
        await client._request("initialize", {})
    assert client._pending == {}


async def test_stop_kills_peer_that_ignores_termination(tmp_path):
    # PR #1352：terminate 超时后仍须 kill 并等待回收，不能吞错后留下进程。
    client = LspClient("python", str(tmp_path))
    peer = _ProtocolPeer(tmp_path / "target.py")
    peer.wait = AsyncMock(side_effect=[asyncio.TimeoutError(), -9])
    client._proc = peer
    await client._stop()
    assert peer.terminated == 1
    assert peer.killed == 1
    assert peer.wait.call_count == 2


@pytest.mark.parametrize("length", [-1, 4 * 1024 * 1024 + 1])
async def test_reader_rejects_invalid_size_before_waiting_for_body(tmp_path, length):
    # PR #1352：非法/超大长度不能触发等待正文或分配无界缓冲区。
    client = LspClient("python", str(tmp_path))
    peer = _ProtocolPeer(tmp_path / "target.py", mode="silent")
    client._proc = peer
    peer.stdout.feed_data(f"Content-Length: {length}\r\n\r\n".encode())
    client._reader_task = asyncio.create_task(client._reader_loop())
    try:
        with pytest.raises(RuntimeError, match="invalid Content-Length"):
            await client._request("initialize", {})
        assert client._pending == {}
    finally:
        await client._stop()


async def test_close_cancels_inflight_request(tmp_path):
    # PR #1352：关闭客户端不能留下等到超时才退出的请求。
    client = LspClient("python", str(tmp_path))
    client._proc = _ProtocolPeer(tmp_path / "target.py", mode="silent")
    request = asyncio.create_task(client._request("initialize", {}))
    await asyncio.sleep(0)
    assert len(client._pending) == 1
    await client._stop()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert client._pending == {}


@pytest.mark.parametrize("location_link", [False, True])
async def test_definition_location_shapes_and_uri_decoding(tmp_path, location_link):
    # PR #1352：LocationLink 使用 targetSelectionRange；路径必须解码转义。
    target = tmp_path / "with space.py"
    start = {"line": 0, "character": 3}
    if location_link:
        location = {
            "targetUri": target.as_uri(),
            "targetRange": {"start": {"line": 8, "character": 0}},
            "targetSelectionRange": {"start": start},
        }
    else:
        location = {"uri": target.as_uri(), "range": {"start": start}}
    client = LspClient("python", str(tmp_path))
    client._request = AsyncMock(return_value=[location])
    assert await client.go_to_definition(str(tmp_path / "source.py"), 1, 2) == {
        "file": str(target),
        "line": 0,
        "character": 3,
    }


def test_cache_lsp_resolution_idempotent(ast_cache_conn):
    """INSERT OR REPLACE: calling twice for same (edge_id, lsp_server) gives 1 row."""
    edge_id = _seed_edge(ast_cache_conn)
    for _ in range(2):
        cache_lsp_resolution(
            ast_cache_conn,
            edge_id=edge_id,
            symbol_id=None,
            resolved_type="str",
            resolved_file="b.py",
            resolved_line=5,
            lsp_server="pyright",
        )
    count = ast_cache_conn.execute(
        "SELECT COUNT(*) FROM lsp_resolution_cache WHERE edge_id = ?", (edge_id,)
    ).fetchone()[0]
    assert count == 1
