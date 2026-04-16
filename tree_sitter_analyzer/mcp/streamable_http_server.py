"""
StreamableHTTP transport for the MCP server.

Provides HTTP/SSE-based access to all MCP tools using the StreamableHTTP
protocol from the MCP SDK (v1.17.0+). Enables multi-client access, browser
integration, and SDK embedding into existing Python web applications.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
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

        # Evict old entries
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


class HeartbeatMiddleware:
    """ASGI middleware that injects SSE heartbeat comments for long-lived connections."""

    def __init__(self, app: Any, interval: float = 30.0) -> None:
        self.app = app
        self._interval = interval

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path != "/mcp":
            await self.app(scope, receive, send)
            return

        # For GET requests (SSE streams), inject heartbeat pings
        method = scope.get("method", "")
        if method == "GET":
            await self._handle_sse_with_heartbeat(scope, receive, send)
        else:
            await self.app(scope, receive, send)

    async def _handle_sse_with_heartbeat(
        self, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        """Wrap SSE connection with periodic heartbeat comments."""
        done = False

        async def heartbeat_sender() -> None:
            """Send SSE heartbeat comments periodically."""
            while not done:
                await asyncio.sleep(self._interval)
                if not done:
                    try:
                        await send({
                            "type": "http.response.body",
                            "body": b": heartbeat\n\n",
                            "more_body": True,
                        })
                    except Exception:
                        break

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal done
            await send(message)
            if message.get("type") == "http.response.body" and not message.get(
                "more_body", False
            ):
                done = True

        heartbeat_task = asyncio.create_task(heartbeat_sender())
        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            done = True
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task


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


def create_streamable_http_app(
    mcp_server_instance: TreeSitterAnalyzerMCPServer,
    *,
    stateless: bool = False,
    rate_limit: int = DEFAULT_RATE_LIMIT,
    heartbeat_interval: float = 30.0,
) -> Starlette:
    """Create a Starlette ASGI app serving the MCP server via StreamableHTTP.

    Args:
        mcp_server_instance: Configured TreeSitterAnalyzerMCPServer instance.
        stateless: If True, run without session tracking.
        rate_limit: Max requests per minute per client (0 to disable).
        heartbeat_interval: Seconds between SSE heartbeat pings (0 to disable).

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

    # Heartbeat middleware is applied via ASGI wrapping when heartbeat_interval > 0
    return app


async def run_streamable_http(
    mcp_server_instance: TreeSitterAnalyzerMCPServer,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    stateless: bool = False,
    rate_limit: int = DEFAULT_RATE_LIMIT,
    heartbeat_interval: float = 30.0,
) -> None:
    """Run the MCP server with StreamableHTTP transport.

    Args:
        mcp_server_instance: Configured server instance.
        host: Listen address.
        port: Listen port.
        stateless: If True, run without session tracking.
        rate_limit: Max requests per minute per client (0 to disable).
        heartbeat_interval: Seconds between SSE heartbeat pings (0 to disable).
    """
    import uvicorn

    app = create_streamable_http_app(
        mcp_server_instance,
        stateless=stateless,
        rate_limit=rate_limit,
        heartbeat_interval=heartbeat_interval,
    )

    logger.info(f"Starting StreamableHTTP MCP server on {host}:{port}")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uv_server = uvicorn.Server(config)
    await uv_server.serve()
