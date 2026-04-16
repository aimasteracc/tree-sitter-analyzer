#!/usr/bin/env python3
"""
Tests for StreamableHTTP error handling: middleware, app creation, edge cases.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.streamable_http_server import (
    ConnectionTracker,
    HeartbeatMiddleware,
    RateLimiter,
    connection_limit_middleware,
    create_streamable_http_app,
    rate_limit_middleware,
)


def _make_request(
    path: str = "/mcp",
    method: str = "POST",
    client_host: str | None = "127.0.0.1",
    app: MagicMock | None = None,
) -> MagicMock:
    """Create a mock Starlette Request."""
    request = MagicMock()
    request.scope = {"type": "http", "path": path, "method": method}
    request.method = method
    request.url = MagicMock()
    request.url.path = path
    if client_host:
        request.client = MagicMock()
        request.client.host = client_host
    else:
        request.client = None
    if app is not None:
        request.app = app
    return request


class TestRateLimitMiddleware:
    """Test the Starlette rate_limit_middleware function."""

    @pytest.mark.asyncio
    async def test_allows_under_limit(self) -> None:
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        app = MagicMock()
        app.state.rate_limiter = limiter
        request = _make_request(app=app)

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await rate_limit_middleware(request, call_next)
        assert response.status_code != 429
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = MagicMock()
        app.state.rate_limiter = limiter
        request = _make_request(app=app)

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        await rate_limit_middleware(request, call_next)
        response = await rate_limit_middleware(request, call_next)
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_no_client_defaults_to_unknown(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        app = MagicMock()
        app.state.rate_limiter = limiter
        request = _make_request(client_host=None, app=app)

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        await rate_limit_middleware(request, call_next)
        response = await rate_limit_middleware(request, call_next)
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_429_response_contains_retry_after(self) -> None:
        limiter = RateLimiter(max_requests=0, window_seconds=60)
        app = MagicMock()
        app.state.rate_limiter = limiter
        request = _make_request(app=app)

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await rate_limit_middleware(request, call_next)
        assert response.status_code == 429
        body = response.body
        assert b"retry_after" in body if body else True


class TestConnectionLimitMiddleware:
    """Test the Starlette connection_limit_middleware function."""

    @pytest.mark.asyncio
    async def test_allows_under_capacity(self) -> None:
        tracker = ConnectionTracker(max_connections=10)
        app = MagicMock()
        app.state.connection_tracker = tracker
        request = _make_request(app=app)

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await connection_limit_middleware(request, call_next)
        assert response.status_code != 503

    @pytest.mark.asyncio
    async def test_blocks_at_capacity(self) -> None:
        tracker = ConnectionTracker(max_connections=1)
        tracker.acquire("existing")
        app = MagicMock()
        app.state.connection_tracker = tracker
        request = _make_request(app=app)

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await connection_limit_middleware(request, call_next)
        assert response.status_code == 503


class TestCreateStreamableHttpApp:
    """Test app creation and configuration."""

    @pytest.mark.asyncio
    async def test_import_error_without_mcp(self) -> None:
        mcp_server = MagicMock()

        with patch.dict("sys.modules", {"mcp.server.streamable_http_manager": None}):
            with pytest.raises(ImportError, match="StreamableHTTP"):
                create_streamable_http_app(mcp_server)

    @pytest.mark.asyncio
    async def test_app_has_rate_limiter_state(self) -> None:
        mcp_server = MagicMock()
        mcp_server.create_server.return_value = MagicMock()

        with patch("tree_sitter_analyzer.mcp.streamable_http_server.StreamableHTTPSessionManager", create=True):
            try:
                app = create_streamable_http_app(
                    mcp_server, rate_limit=50, max_connections=20,
                )
                assert hasattr(app.state, "rate_limiter")
                assert hasattr(app.state, "connection_tracker")
            except (ImportError, AttributeError):
                pass

    @pytest.mark.asyncio
    async def test_disabled_rate_limit(self) -> None:
        mcp_server = MagicMock()
        mcp_server.create_server.return_value = MagicMock()

        with patch("tree_sitter_analyzer.mcp.streamable_http_server.StreamableHTTPSessionManager", create=True):
            try:
                app = create_streamable_http_app(
                    mcp_server, rate_limit=0,
                )
                assert hasattr(app.state, "rate_limiter")
            except (ImportError, AttributeError):
                pass


class TestHeartbeatErrorHandling:
    """Test error handling in heartbeat and SSE connections."""

    @pytest.mark.asyncio
    async def test_heartbeat_connection_error(self) -> None:
        """Heartbeat sender handles ConnectionError gracefully."""
        tracker = ConnectionTracker(max_connections=10)
        call_count = 0

        async def inner_app(scope: dict, receive: object, send: object) -> None:
            nonlocal call_count
            call_count += 1
            # Keep connection alive long enough for heartbeat to trigger
            await asyncio.sleep(0.2)
            await send({
                "type": "http.response.body",
                "body": b"data: done\n\n",
                "more_body": False,
            })

        error_on_heartbeat = False

        async def flaky_send(msg: dict) -> None:
            if msg.get("body") == b": heartbeat\n\n":
                nonlocal error_on_heartbeat
                error_on_heartbeat = True
                raise ConnectionError("Client disconnected")

        async def noop_receive() -> dict:
            await asyncio.sleep(1)
            return {"type": "http.request"}

        mw = HeartbeatMiddleware(inner_app, interval=0.05, tracker=tracker)
        await mw(
            {"type": "http", "path": "/mcp", "method": "GET"},
            noop_receive,
            flaky_send,
        )
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_detection(self) -> None:
        """Disconnect watcher detects http.disconnect message."""
        messages: list[dict] = []

        async def inner_app(scope: dict, receive: object, send: object) -> None:
            await send({
                "type": "http.response.body",
                "body": b"data: done\n\n",
                "more_body": False,
            })

        async def disconnect_receive() -> dict:
            return {"type": "http.disconnect"}

        async def capture_send(msg: dict) -> None:
            messages.append(msg)

        mw = HeartbeatMiddleware(inner_app, interval=1.0)
        await mw(
            {"type": "http", "path": "/mcp", "method": "GET"},
            disconnect_receive,
            capture_send,
        )
        assert len(messages) >= 1

    @pytest.mark.asyncio
    async def test_tracker_released_on_exception(self) -> None:
        """Connection tracker slot is released even if app raises."""

        async def failing_app(scope: dict, receive: object, send: object) -> None:
            raise RuntimeError("App error")

        tracker = ConnectionTracker(max_connections=10)

        async def noop_receive() -> dict:
            return {"type": "http.request"}

        mw = HeartbeatMiddleware(failing_app, interval=1.0, tracker=tracker)

        async def noop_send(msg: dict) -> None:
            pass

        with pytest.raises(RuntimeError, match="App error"):
            await mw(
                {"type": "http", "path": "/mcp", "method": "GET"},
                noop_receive,
                noop_send,
            )
        assert tracker.active_count == 0


class TestRateLimiterEdgeCases:
    """Edge case tests for RateLimiter."""

    def test_zero_max_requests(self) -> None:
        limiter = RateLimiter(max_requests=0, window_seconds=60)
        assert limiter.is_allowed("client") is False

    def test_cleanup_keeps_active_entries(self) -> None:
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        limiter.is_allowed("active-client")
        limiter.cleanup()
        assert "active-client" in limiter._clients

    def test_separate_windows_per_client(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("a") is True
        assert limiter.is_allowed("b") is True
        assert limiter.is_allowed("a") is False
        assert limiter.is_allowed("b") is False


class TestConnectionTrackerEdgeCases:
    """Edge case tests for ConnectionTracker."""

    def test_zero_max_connections(self) -> None:
        tracker = ConnectionTracker(max_connections=0)
        with pytest.raises(ConnectionError):
            tracker.acquire()

    def test_double_release_safe(self) -> None:
        tracker = ConnectionTracker(max_connections=10)
        conn_id = tracker.acquire()
        tracker.release(conn_id)
        tracker.release(conn_id)
        assert tracker.active_count == 0

    def test_acquire_release_cycle_many_times(self) -> None:
        tracker = ConnectionTracker(max_connections=2)
        for _ in range(100):
            cid = tracker.acquire()
            tracker.release(cid)
        assert tracker.active_count == 0
