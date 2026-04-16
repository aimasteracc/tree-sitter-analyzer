"""
Tests for StreamableHTTP transport: rate limiting, heartbeat, and connection tracking.
"""

from __future__ import annotations

import time

import pytest

from tree_sitter_analyzer.mcp.streamable_http_server import (
    DEFAULT_RATE_LIMIT,
    ConnectionTracker,
    HeartbeatMiddleware,
    RateLimiter,
)


async def _noop() -> None:
    pass


class TestRateLimiter:
    """Test the token-bucket rate limiter."""

    def test_allows_requests_under_limit(self) -> None:
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed("client-a") is True

    def test_blocks_requests_over_limit(self) -> None:
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.is_allowed("client-b") is True
        assert limiter.is_allowed("client-b") is False

    def test_separate_clients_independent(self) -> None:
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-1") is True
        assert limiter.is_allowed("client-2") is True
        assert limiter.is_allowed("client-1") is False
        assert limiter.is_allowed("client-2") is True

    def test_window_expiry_allows_new_requests(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=1)
        assert limiter.is_allowed("client-c") is True
        assert limiter.is_allowed("client-c") is False
        time.sleep(1.1)
        assert limiter.is_allowed("client-c") is True

    def test_cleanup_removes_expired_entries(self) -> None:
        limiter = RateLimiter(max_requests=5, window_seconds=1)
        limiter.is_allowed("expired-client")
        time.sleep(1.1)
        limiter.cleanup()
        assert "expired-client" not in limiter._clients

    def test_default_rate_limit_value(self) -> None:
        assert DEFAULT_RATE_LIMIT == 100


class TestConnectionTracker:
    """Test connection tracking and limiting."""

    def test_acquire_returns_connection_id(self) -> None:
        tracker = ConnectionTracker(max_connections=10)
        conn_id = tracker.acquire()
        assert isinstance(conn_id, str)
        assert len(conn_id) > 0

    def test_acquire_with_custom_id(self) -> None:
        tracker = ConnectionTracker(max_connections=10)
        result = tracker.acquire("my-conn-id")
        assert result == "my-conn-id"

    def test_release_removes_connection(self) -> None:
        tracker = ConnectionTracker(max_connections=10)
        conn_id = tracker.acquire()
        assert tracker.active_count == 1
        tracker.release(conn_id)
        assert tracker.active_count == 0

    def test_release_unknown_id_is_noop(self) -> None:
        tracker = ConnectionTracker(max_connections=10)
        tracker.release("nonexistent")

    def test_max_connections_enforced(self) -> None:
        tracker = ConnectionTracker(max_connections=2)
        tracker.acquire()
        tracker.acquire()
        with pytest.raises(ConnectionError, match="Max concurrent"):
            tracker.acquire()

    def test_is_at_capacity(self) -> None:
        tracker = ConnectionTracker(max_connections=2)
        assert tracker.is_at_capacity() is False
        tracker.acquire()
        assert tracker.is_at_capacity() is False
        tracker.acquire()
        assert tracker.is_at_capacity() is True

    def test_release_allows_new_connection(self) -> None:
        tracker = ConnectionTracker(max_connections=1)
        conn_id = tracker.acquire()
        tracker.release(conn_id)
        tracker.acquire()
        assert tracker.active_count == 1

    def test_active_count_tracks_multiple(self) -> None:
        tracker = ConnectionTracker(max_connections=10)
        ids = [tracker.acquire() for _ in range(5)]
        assert tracker.active_count == 5
        tracker.release(ids[0])
        tracker.release(ids[2])
        assert tracker.active_count == 3


class TestHeartbeatMiddleware:
    """Test the SSE heartbeat ASGI middleware."""

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self) -> None:
        """Non-HTTP scope (e.g., lifespan) passes through unchanged."""
        called = False

        async def inner_app(scope: dict, receive: object, send: object) -> None:
            nonlocal called
            called = True

        mw = HeartbeatMiddleware(inner_app, interval=1.0)
        await mw({"type": "lifespan"}, None, None)
        assert called is True

    @pytest.mark.asyncio
    async def test_non_mcp_path_passthrough(self) -> None:
        """Non-/mcp paths pass through without heartbeat."""
        received_scope: dict = {}

        async def inner_app(scope: dict, receive: object, send: object) -> None:
            received_scope.update(scope)

        mw = HeartbeatMiddleware(inner_app, interval=1.0)
        await mw({"type": "http", "path": "/health", "method": "GET"}, None, None)
        assert received_scope.get("path") == "/health"

    @pytest.mark.asyncio
    async def test_post_passthrough(self) -> None:
        """POST requests to /mcp pass through without heartbeat injection."""
        received_method = ""

        async def inner_app(scope: dict, receive: object, send: object) -> None:
            nonlocal received_method
            received_method = scope.get("method", "")

        mw = HeartbeatMiddleware(inner_app, interval=1.0)
        await mw(
            {"type": "http", "path": "/mcp", "method": "POST"},
            None,
            None,
        )
        assert received_method == "POST"

    @pytest.mark.asyncio
    async def test_get_sse_wraps_send(self) -> None:
        """GET /mcp wraps the send function for heartbeat injection."""
        messages: list[dict] = []

        async def inner_app(scope: dict, receive: object, send: object) -> None:
            await send({
                "type": "http.response.body",
                "body": b"data: test\n\n",
                "more_body": False,
            })

        async def capture_send(msg: dict) -> None:
            messages.append(msg)

        mw = HeartbeatMiddleware(inner_app, interval=0.1)
        await mw(
            {"type": "http", "path": "/mcp", "method": "GET"},
            None,
            capture_send,
        )
        data_msgs = [m for m in messages if m.get("body") == b"data: test\n\n"]
        assert len(data_msgs) == 1
        assert data_msgs[0].get("more_body") is False

    @pytest.mark.asyncio
    async def test_sse_rejects_at_capacity(self) -> None:
        """GET /mcp returns 503 when connection tracker is at capacity."""
        tracker = ConnectionTracker(max_connections=1)
        tracker.acquire("existing")

        messages: list[dict] = []

        async def capture_send(msg: dict) -> None:
            messages.append(msg)

        async def noop_receive() -> dict:
            return {"type": "http.request"}

        mw = HeartbeatMiddleware(
            app=lambda s, r, send: None,
            interval=1.0,
            tracker=tracker,
        )
        await mw(
            {"type": "http", "path": "/mcp", "method": "GET"},
            noop_receive,
            capture_send,
        )
        status_msgs = [m for m in messages if m.get("type") == "http.response.start"]
        assert len(status_msgs) == 1
        assert status_msgs[0]["status"] == 503

    @pytest.mark.asyncio
    async def test_sse_tracks_connection_lifecycle(self) -> None:
        """GET /mcp acquires and releases a connection tracker slot."""
        tracker = ConnectionTracker(max_connections=10)

        async def inner_app(scope: dict, receive: object, send: object) -> None:
            assert tracker.active_count == 1
            await send({
                "type": "http.response.body",
                "body": b"data: done\n\n",
                "more_body": False,
            })

        async def noop_receive() -> dict:
            return {"type": "http.request"}

        mw = HeartbeatMiddleware(inner_app, interval=1.0, tracker=tracker)
        await mw(
            {"type": "http", "path": "/mcp", "method": "GET"},
            noop_receive,
            lambda msg: _noop(),
        )
        assert tracker.active_count == 0
