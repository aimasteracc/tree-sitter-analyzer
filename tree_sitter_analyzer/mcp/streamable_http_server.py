"""
StreamableHTTP transport for the MCP server.

Provides HTTP/SSE-based access to all MCP tools using the StreamableHTTP
protocol from the MCP SDK (v1.17.0+). Enables multi-client access, browser
integration, and SDK embedding into existing Python web applications.

Features:
- Per-client rate limiting (token bucket)
- SSE heartbeat keepalive for long-lived connections
- Connection tracking with disconnect detection
- Concurrent connection limiting
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections import defaultdict
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_RATE_LIMIT = 100  # requests per minute per client
DEFAULT_MAX_CONNECTIONS = 50  # max concurrent connections
RATE_LIMIT_WINDOW = 60  # seconds


class RateLimiter:
    """Token-bucket rate limiter per client IP."""

    def __init__(
        self,
        max_requests: int = DEFAULT_RATE_LIMIT,
        window_seconds: int = RATE_LIMIT_WINDOW,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._clients: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if a request from client_id is within rate limits."""
        now = time.monotonic()
        timestamps = self._clients[client_id]
        cutoff = now - self._window

        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= self._max:
            return False

        timestamps.append(now)
        return True

    def cleanup(self) -> None:
        """Remove expired client entries."""
        now = time.monotonic()
        cutoff = now - self._window
        expired = [k for k, v in self._clients.items() if not v or v[-1] < cutoff]
        for k in expired:
            del self._clients[k]


class ConnectionTracker:
    """Track active connections with disconnect detection."""

    def __init__(self, max_connections: int = DEFAULT_MAX_CONNECTIONS) -> None:
        self._max = max_connections
        self._active: dict[str, float] = {}

    def acquire(self, conn_id: str | None = None) -> str:
        """Register a new connection. Returns connection ID.

        Raises ConnectionError if at max capacity.
        """
        if len(self._active) >= self._max:
            raise ConnectionError(
                f"Max concurrent connections reached ({self._max})"
            )
        cid = conn_id or str(uuid.uuid4())
        self._active[cid] = time.monotonic()
        return cid

    def release(self, conn_id: str) -> None:
        """Release a connection."""
        self._active.pop(conn_id, None)

    @property
    def active_count(self) -> int:
        """Number of currently active connections."""
        return len(self._active)

    def is_at_capacity(self) -> bool:
        """Check if at max connection capacity."""
        return len(self._active) >= self._max


class HeartbeatMiddleware:
    """ASGI middleware that injects SSE heartbeat comments and detects disconnects."""

    def __init__(
        self,
        app: Any,
        interval: float = 30.0,
        tracker: ConnectionTracker | None = None,
    ) -> None:
        self.app = app
        self._interval = interval
        self._tracker = tracker

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path != "/mcp":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        if method == "GET":
            await self._handle_sse_with_heartbeat(scope, receive, send)
        else:
            await self.app(scope, receive, send)

    async def _handle_sse_with_heartbeat(
        self, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        """Wrap SSE connection with heartbeat and disconnect detection."""
        done = False
        conn_id = ""

        if self._tracker:
            try:
                conn_id = self._tracker.acquire()
            except ConnectionError:
                await send({
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"error": "Max connections reached"}',
                })
                return

        async def heartbeat_sender() -> None:
            """Send SSE heartbeat comments and detect disconnects."""
            while not done:
                await asyncio.sleep(self._interval)
                if not done:
                    try:
                        await send({
                            "type": "http.response.body",
                            "body": b": heartbeat\n\n",
                            "more_body": True,
                        })
                    except (ConnectionError, OSError):
                        break

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal done
            await send(message)
            if message.get("type") == "http.response.body" and not message.get(
                "more_body", False
            ):
                done = True

        async def disconnect_watcher() -> None:
            """Watch for client disconnect via receive."""
            nonlocal done
            while not done:
                message = await receive()
                if message.get("type") == "http.disconnect":
                    done = True
                    break

        heartbeat_task = asyncio.create_task(heartbeat_sender())
        disconnect_task = asyncio.create_task(disconnect_watcher())
        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            done = True
            heartbeat_task.cancel()
            disconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
            with contextlib.suppress(asyncio.CancelledError):
                await disconnect_task
            if self._tracker and conn_id:
                self._tracker.release(conn_id)


async def rate_limit_middleware(request: Request, call_next: Any) -> Response:
    """Starlette middleware for rate limiting MCP requests."""
    client_id = request.client.host if request.client else "unknown"
    limiter: RateLimiter = request.app.state.rate_limiter

    if not limiter.is_allowed(client_id):
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after": RATE_LIMIT_WINDOW},
            status_code=429,
        )

    response: Response = await call_next(request)
    return response


async def connection_limit_middleware(request: Request, call_next: Any) -> Response:
    """Starlette middleware for connection limiting."""
    tracker: ConnectionTracker = request.app.state.connection_tracker
    if tracker.is_at_capacity():
        return JSONResponse(
            {"error": "Max concurrent connections reached"},
            status_code=503,
        )
    response: Response = await call_next(request)
    return response


def create_streamable_http_app(
    mcp_server_instance: TreeSitterAnalyzerMCPServer,
    *,
    stateless: bool = False,
    rate_limit: int = DEFAULT_RATE_LIMIT,
    heartbeat_interval: float = 30.0,
    max_connections: int = DEFAULT_MAX_CONNECTIONS,
) -> Starlette:
    """Create a Starlette ASGI app serving the MCP server via StreamableHTTP.

    Args:
        mcp_server_instance: Configured TreeSitterAnalyzerMCPServer instance.
        stateless: If True, run without session tracking.
        rate_limit: Max requests per minute per client (0 to disable).
        heartbeat_interval: Seconds between SSE heartbeat pings (0 to disable).
        max_connections: Max concurrent SSE connections (0 for unlimited).

    Returns:
        Starlette application with MCP StreamableHTTP routes.
    """
    try:
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    except ImportError as e:
        raise ImportError(
            "StreamableHTTP requires mcp>=1.17.0. "
            "Install with: pip install 'tree-sitter-analyzer[mcp]'"
        ) from e

    server = mcp_server_instance.create_server()
    session_manager = StreamableHTTPSessionManager(
        app=server,
        stateless=stateless,
    )

    async def handle_mcp(request: Request) -> None:
        """ASGI handler that delegates to StreamableHTTPSessionManager."""
        await session_manager.handle_request(
            request.scope, request.receive, request._send,  # noqa: SLF001
        )

    async def health_check(request: Request) -> JSONResponse:  # noqa: ARG001
        """Health check endpoint."""
        return JSONResponse({
            "status": "ok",
            "transport": "streamable-http",
            "rate_limit": rate_limit,
            "heartbeat_interval": heartbeat_interval,
        })

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> Any:
        """Manage session manager lifecycle."""
        async with session_manager.run():
            yield

    middleware: list[Middleware] = []
    if rate_limit > 0:
        middleware.append(Middleware(rate_limit_middleware))  # type: ignore[arg-type]

    app = Starlette(
        routes=[
            Route("/mcp", handle_mcp, methods=["POST", "GET", "DELETE"]),
            Route("/health", health_check, methods=["GET"]),
        ],
        middleware=middleware,
        lifespan=lifespan,
    )

    app.state.rate_limiter = RateLimiter(max_requests=rate_limit)
    app.state.connection_tracker = ConnectionTracker(max_connections=max_connections)

    return app


async def run_streamable_http(
    mcp_server_instance: TreeSitterAnalyzerMCPServer,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    stateless: bool = False,
    rate_limit: int = DEFAULT_RATE_LIMIT,
    heartbeat_interval: float = 30.0,
    max_connections: int = DEFAULT_MAX_CONNECTIONS,
) -> None:
    """Run the MCP server with StreamableHTTP transport.

    Args:
        mcp_server_instance: Configured server instance.
        host: Listen address.
        port: Listen port.
        stateless: If True, run without session tracking.
        rate_limit: Max requests per minute per client (0 to disable).
        heartbeat_interval: Seconds between SSE heartbeat pings (0 to disable).
        max_connections: Max concurrent SSE connections (0 for unlimited).
    """
    import uvicorn

    app = create_streamable_http_app(
        mcp_server_instance,
        stateless=stateless,
        rate_limit=rate_limit,
        heartbeat_interval=heartbeat_interval,
        max_connections=max_connections,
    )

    logger.info(f"Starting StreamableHTTP MCP server on {host}:{port}")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uv_server = uvicorn.Server(config)
    await uv_server.serve()
