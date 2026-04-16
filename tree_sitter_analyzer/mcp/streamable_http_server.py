"""
StreamableHTTP transport for the MCP server.

Provides HTTP/SSE-based access to all MCP tools using the StreamableHTTP
protocol from the MCP SDK (v1.17.0+). Enables multi-client access, browser
integration, and SDK embedding into existing Python web applications.
"""
from __future__ import annotations

import contextlib
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def create_streamable_http_app(
    mcp_server_instance: TreeSitterAnalyzerMCPServer,
    *,
    stateless: bool = False,
) -> Starlette:
    """Create a Starlette ASGI app serving the MCP server via StreamableHTTP.

    Args:
        mcp_server_instance: Configured TreeSitterAnalyzerMCPServer instance.
        stateless: If True, run without session tracking.

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
        return JSONResponse({"status": "ok", "transport": "streamable-http"})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> Any:
        """Manage session manager lifecycle."""
        async with session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/mcp", handle_mcp, methods=["POST", "GET", "DELETE"]),
            Route("/health", health_check, methods=["GET"]),
        ],
        lifespan=lifespan,
    )

    return app


async def run_streamable_http(
    mcp_server_instance: TreeSitterAnalyzerMCPServer,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    stateless: bool = False,
) -> None:
    """Run the MCP server with StreamableHTTP transport.

    Args:
        mcp_server_instance: Configured server instance.
        host: Listen address.
        port: Listen port.
        stateless: If True, run without session tracking.
    """
    import uvicorn

    app = create_streamable_http_app(
        mcp_server_instance,
        stateless=stateless,
    )

    logger.info(f"Starting StreamableHTTP MCP server on {host}:{port}")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uv_server = uvicorn.Server(config)
    await uv_server.serve()
