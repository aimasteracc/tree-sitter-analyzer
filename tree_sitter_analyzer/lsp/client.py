"""LSP client for TSA — asyncio JSON-RPC over stdio.

Supported servers (detected by extension / language):
  pyright-langserver   — Python 语言服务，不是 pyright 检查器
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
from urllib.parse import urlsplit
from urllib.request import url2pathname

logger = logging.getLogger(__name__)

_LSP_TIMEOUT = 10.0  # seconds per request
_MAX_LSP_MESSAGE_BYTES = 4 * 1024 * 1024

# Maps language names (from ast_symbol_rows.language) to LSP server commands.
_SERVER_COMMANDS: dict[str, list[str]] = {
    "python": ["pyright-langserver", "--stdio"],
    "typescript": ["typescript-language-server", "--stdio"],
    "javascript": ["typescript-language-server", "--stdio"],
    "rust": ["rust-analyzer"],
}


class LspServerUnavailableError(RuntimeError):
    """Raised when the required LSP server binary is not found."""


class LspTimeoutError(RuntimeError):
    """Raised when an LSP request times out."""


class LspProtocolError(RuntimeError):
    """对端协议错误、断流或错误响应，不能视为成功的空结果。"""


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

    async def __aenter__(self) -> LspClient:
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
            raise LspServerUnavailableError(f"LSP server '{cmd[0]}' not found on PATH")

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        self._reader_task = asyncio.create_task(self._reader_loop())
        try:
            await self._initialize()
        except BaseException:
            # __aenter__ 失败时不会自动进入 __aexit__，必须在此回收进程。
            await self._stop()
            raise

    async def _stop(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    # terminate 等待超时与 kill 之间，对端仍可能自行退出。
                    pass
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, message: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        body = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._proc.stdin.write(header.encode("ascii") + body)

    async def _request(self, method: str, params: Any) -> Any:
        req_id = self._next_id()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req_id] = fut
        try:
            self._send(
                {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            )
            return await asyncio.wait_for(fut, timeout=_LSP_TIMEOUT)
        except asyncio.TimeoutError:
            raise LspTimeoutError(
                f"LSP request '{method}' timed out after {_LSP_TIMEOUT}s"
            ) from None
        finally:
            self._pending.pop(req_id, None)
            if not fut.done():
                fut.cancel()

    def _notify(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _reader_loop(self) -> None:
        assert self._proc and self._proc.stdout
        failure = LspProtocolError("LSP reader stopped")
        try:
            while True:
                content_length = None
                header_bytes = 0
                # LSP 允许 Content-Type 等附加头；读到空行才开始读取正文。
                while True:
                    header_line = await self._proc.stdout.readline()
                    if not header_line:
                        raise LspProtocolError("stream closed")
                    header_bytes += len(header_line)
                    if header_bytes > 8192:
                        raise LspProtocolError("header too large")
                    if header_line in (b"\r\n", b"\n"):
                        break
                    key, value = header_line.split(b":", 1)
                    if key.lower() == b"content-length":
                        content_length = int(value.strip())
                if (
                    content_length is None
                    or not 0 <= content_length <= _MAX_LSP_MESSAGE_BYTES
                ):
                    raise LspProtocolError("invalid Content-Length")
                raw = await self._proc.stdout.readexactly(content_length)
                msg = json.loads(raw)
                msg_id = msg.get("id")
                if msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(
                                LspProtocolError(f"LSP request failed: {msg['error']}")
                            )
                        else:
                            fut.set_result(msg.get("result"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = LspProtocolError(f"LSP reader failed: {exc}")
            logger.debug("LspClient reader error: %s", exc)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(failure)
            self._pending.clear()

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
        # 同时支持 Location 和 LocationLink，优先取定义标识符的选区。
        loc = result[0] if isinstance(result, list) else result
        if not loc:
            return None
        target_uri = loc.get("targetUri", loc.get("uri", ""))
        rng = loc.get("targetSelectionRange", loc.get("range", {})).get("start", {})
        uri = urlsplit(target_uri)
        if uri.scheme != "file" or not uri.path or "line" not in rng:
            return None
        path = (
            uri.path if uri.netloc in ("", "localhost") else f"//{uri.netloc}{uri.path}"
        )
        target_path = url2pathname(path)
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
        resolved_line:  LSP 零基定义行号；展示为 TSA 坐标时才转换，缺失为 None。
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
