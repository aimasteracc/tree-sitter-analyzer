"""
TDD tests for StreamableHTTP transport.

Tests the transport selection, HTTP server creation, and ASGI app
for the StreamableHTTP-based MCP server.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestTransportSelection:
    """CLI argument parsing for --transport flag."""

    def test_default_transport_is_stdio(self) -> None:
        """Without --transport, server uses stdio."""
        from tree_sitter_analyzer.mcp.server import parse_mcp_args

        args = parse_mcp_args([])
        assert args.transport == "stdio"

    def test_transport_streamable_http(self) -> None:
        from tree_sitter_analyzer.mcp.server import parse_mcp_args

        args = parse_mcp_args(["--transport", "streamable-http"])
        assert args.transport == "streamable-http"

    def test_transport_with_host_and_port(self) -> None:
        from tree_sitter_analyzer.mcp.server import parse_mcp_args

        args = parse_mcp_args([
            "--transport", "streamable-http",
            "--host", "0.0.0.0",
            "--port", "3000",
        ])
        assert args.transport == "streamable-http"
        assert args.host == "0.0.0.0"
        assert args.port == 3000

    def test_invalid_transport_rejected(self) -> None:
        from tree_sitter_analyzer.mcp.server import parse_mcp_args

        with pytest.raises(SystemExit):
            parse_mcp_args(["--transport", "websocket"])


class TestStreamableHTTPServer:
    """StreamableHTTP server creation and ASGI app."""

    def test_create_asgi_app(self) -> None:
        """ASGI app is created with Starlette routes."""
        from tree_sitter_analyzer.mcp.streamable_http_server import (
            create_streamable_http_app,
        )

        mock_mcp_server = MagicMock()
        app = create_streamable_http_app(mock_mcp_server)
        assert app is not None
        # Starlette app has routes
        assert hasattr(app, "routes")

    def test_create_asgi_app_with_stateless(self) -> None:
        """Stateless mode creates app without session tracking."""
        from tree_sitter_analyzer.mcp.streamable_http_server import (
            create_streamable_http_app,
        )

        mock_mcp_server = MagicMock()
        app = create_streamable_http_app(mock_mcp_server, stateless=True)
        assert app is not None

    def test_default_host_and_port(self) -> None:
        """Defaults are localhost:8080."""
        from tree_sitter_analyzer.mcp.streamable_http_server import (
            DEFAULT_HOST,
            DEFAULT_PORT,
        )

        assert DEFAULT_HOST == "127.0.0.1"
        assert DEFAULT_PORT == 8080
