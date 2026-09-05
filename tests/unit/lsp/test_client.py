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
