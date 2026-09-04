"""LSP client for TSA — asyncio JSON-RPC over stdio.

Supported servers (detected by extension / language):
  pyright              — Python
  typescript-language-server — TypeScript / JavaScript
  rust-analyzer        — Rust

Protocol:
  Each server is spawned as a subprocess with stdio transport.
  The client implements the minimum LSP subset needed for go-to-definition:
    initialize / initialized / textDocument/definition

Graceful degradation:
  - If the server binary is not on PATH → LspServerUnavailableError
  - If the server crashes or times out   → LspTimeoutError
  - All errors are caught in cache_lsp_resolution; callers never crash.

Cache:
  Results are persisted to the lsp_resolution_cache table (schema V15)
  so repeated queries for the same (edge_id, lsp_server) are free.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LSP_TIMEOUT = 10.0  # seconds per request

# Maps language names (from ast_symbol_rows.language) to LSP server commands.
_SERVER_COMMANDS: dict[str, list[str]] = {
    "python": ["pyright", "--stdio"],
    "typescript": ["typescript-language-server", "--stdio"],
    "javascript": ["typescript-language-server", "--stdio"],
    "rust": ["rust-analyzer"],
}


class LspServerUnavailableError(RuntimeError):
    """Raised when the required LSP server binary is not found."""


class LspTimeoutError(RuntimeError):
    """Raised when an LSP request times out."""


class LspClient:
    """Minimal async LSP client over stdio transport.

    Usage::

        async with LspClient(language="python", workspace_root="/path/to/project") as client:
            result = await client.go_to_definition(file_path="/abs/path/to/file.py", line=10, character=5)

    ``result`` is a dict with keys ``file``, ``line``, ``character``, or None if
    the server could not resolve the definition.
    """

    def __init__(self, language: str, workspace_root: str) -> None:
        self.language = language
        self.workspace_root = workspace_root
        self._proc: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._reader_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "LspClient":
        await self._start()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self._stop()

    async def _start(self) -> None:
        cmd = _SERVER_COMMANDS.get(self.language)
        if cmd is None:
            raise LspServerUnavailableError(
                f"No LSP server configured for language '{self.language}'"
            )

        import shutil
        if not shutil.which(cmd[0]):
            raise LspServerUnavailableError(
                f"LSP server '{cmd[0]}' not found on PATH"
            )

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        self._reader_task = asyncio.create_task(self._reader_loop())
        await self._initialize()

    async def _stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except Exception:
                pass

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, message: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._proc.stdin.write((header + body).encode())

    async def _request(self, method: str, params: Any) -> Any:
        req_id = self._next_id()
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req_id] = fut
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=_LSP_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise LspTimeoutError(f"LSP request '{method}' timed out after {_LSP_TIMEOUT}s")

    def _notify(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _reader_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            try:
                header_line = await self._proc.stdout.readline()
                if not header_line:
                    break
                if not header_line.startswith(b"Content-Length:"):
                    continue
                content_length = int(header_line.split(b":")[1].strip())
                # Consume blank line separator.
                await self._proc.stdout.readline()
                raw = await self._proc.stdout.readexactly(content_length)
                msg = json.loads(raw)
                msg_id = msg.get("id")
                if msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg.get("result"))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("LspClient reader error: %s", exc)
                break

    async def _initialize(self) -> None:
        workspace_uri = Path(self.workspace_root).as_uri()
        await self._request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": workspace_uri,
                "capabilities": {
                    "textDocument": {
                        "definition": {"dynamicRegistration": False},
                    }
                },
                "initializationOptions": {},
            },
        )
        self._notify("initialized", {})

    async def go_to_definition(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> dict[str, Any] | None:
        """Request go-to-definition for a position in a file.

        Args:
            file_path:  Absolute path to the file.
            line:       0-indexed line number.
            character:  0-indexed character offset.

        Returns:
            dict with keys file, line, character on success, or None.
        """
        file_uri = Path(file_path).as_uri()
        result = await self._request(
            "textDocument/definition",
            {
                "textDocument": {"uri": file_uri},
                "position": {"line": line, "character": character},
            },
        )
        if not result:
            return None
        # result can be a Location or a list of Location.
        loc = result[0] if isinstance(result, list) else result
        if not loc:
            return None
        target_uri = loc.get("uri", "")
        rng = loc.get("range", {}).get("start", {})
        try:
            target_path = str(Path(target_uri.replace("file://", "")))
        except Exception:
            target_path = target_uri
        return {
            "file": target_path,
            "line": rng.get("line", 0),
            "character": rng.get("character", 0),
        }


def cache_lsp_resolution(
    conn: sqlite3.Connection,
    *,
    edge_id: int | None,
    symbol_id: int | None,
    resolved_type: str | None,
    resolved_file: str | None,
    resolved_line: int | None,
    lsp_server: str,
) -> None:
    """Persist an LSP resolution result to lsp_resolution_cache.

    Uses INSERT OR REPLACE so repeated calls for the same (edge_id, lsp_server)
    are idempotent (updates cached_at).

    Args:
        conn:           Open SQLite connection (must have lsp_resolution_cache table).
        edge_id:        Edge ID this resolution is for (may be None).
        symbol_id:      Symbol ID (may be None when edge_id is used).
        resolved_type:  Fully-qualified type string, or None if unresolved.
        resolved_file:  Absolute path of the definition file, or None.
        resolved_line:  Line number in resolved_file, or None.
        lsp_server:     Name of the LSP server that produced this result
                        (e.g. "pyright", "typescript-language-server").
    """
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO lsp_resolution_cache
                (symbol_id, edge_id, resolved_type, resolved_file, resolved_line, lsp_server, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol_id,
                edge_id,
                resolved_type,
                resolved_file,
                resolved_line,
                lsp_server,
                int(time.time()),
            ),
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        logger.warning("cache_lsp_resolution: insert failed: %s", exc)
