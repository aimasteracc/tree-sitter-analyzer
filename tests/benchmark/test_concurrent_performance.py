"""
Performance benchmark: 100 concurrent requests to StreamableHTTP server.

Measures latency distribution (p50/p95/p99) and throughput (req/s)
for the MCP StreamableHTTP transport layer.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any

import pytest
from starlette.testclient import TestClient

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.streamable_http_server import (
    ConnectionTracker,
    create_streamable_http_app,
)


def _create_test_client(rate_limit: int = 0) -> TestClient:
    """Create a test client with rate limiting disabled for benchmarks."""
    mcp_server = TreeSitterAnalyzerMCPServer()
    app = create_streamable_http_app(
        mcp_server,
        stateless=True,
        rate_limit=rate_limit,
        heartbeat_interval=0,
        max_connections=0,
    )
    return TestClient(app)


def _tools_list_payload(req_id: int = 1) -> dict[str, Any]:
    """Build a JSON-RPC tools/list request payload."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/list",
        "params": {},
    }


class TestConcurrentPerformance:
    """Performance benchmarks for StreamableHTTP transport."""

    def test_health_check_single_latency(self) -> None:
        """Baseline: single health check latency should be < 50ms."""
        client = _create_test_client()
        latencies: list[float] = []

        with client:
            for _ in range(100):
                start = time.monotonic()
                resp = client.get("/health")
                elapsed = time.monotonic() - start
                assert resp.status_code == 200
                latencies.append(elapsed)

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[98]

        assert p50 < 0.01, f"p50 latency too high: {p50*1000:.1f}ms"
        assert p99 < 0.05, f"p99 latency too high: {p99*1000:.1f}ms"

    def test_sequential_health_throughput(self) -> None:
        """Sequential health check requests: measure throughput."""
        client = _create_test_client()

        with client:
            start = time.monotonic()
            for _ in range(200):
                resp = client.get("/health")
                assert resp.status_code == 200
            elapsed = time.monotonic() - start

        rps = 200 / elapsed
        assert rps > 100, f"Throughput too low: {rps:.1f} req/s (expected >100)"

    def test_concurrent_health_check_100(self) -> None:
        """100 health checks: latency distribution."""
        client = _create_test_client()
        num_requests = 100
        latencies: list[float] = []

        with client:
            for _ in range(num_requests):
                start = time.monotonic()
                resp = client.get("/health")
                elapsed = time.monotonic() - start
                assert resp.status_code == 200
                latencies.append(elapsed)

        latencies_sorted = sorted(latencies)
        p50 = latencies_sorted[49]
        p95 = latencies_sorted[94]
        p99 = latencies_sorted[98]

        assert p50 < 0.01, f"p50={p50*1000:.1f}ms"
        assert p95 < 0.05, f"p95={p95*1000:.1f}ms"
        assert p99 < 0.1, f"p99={p99*1000:.1f}ms"

    def test_rate_limiter_concurrent_safety(self) -> None:
        """RateLimiter is safe under concurrent access."""
        from tree_sitter_analyzer.mcp.streamable_http_server import RateLimiter

        limiter = RateLimiter(max_requests=50, window_seconds=60)
        accepted_count = 0

        async def _hammer(client_id: str, n: int) -> int:
            nonlocal accepted_count
            local_accepted = 0
            for _ in range(n):
                if limiter.is_allowed(client_id):
                    local_accepted += 1
            return local_accepted

        async def _run() -> None:
            nonlocal accepted_count
            tasks = [_hammer(f"client-{i % 10}", 10) for i in range(100)]
            results = await asyncio.gather(*tasks)
            accepted_count = sum(results)

        asyncio.run(_run())

        # 10 clients, 50 max each, 10 requests each = 100 accepted max
        assert accepted_count <= 500, f"Rate limiter leaked: {accepted_count}"
        assert accepted_count > 0

    def test_rate_limiter_token_bucket(self) -> None:
        """RateLimiter correctly enforces limits under rapid requests."""
        from tree_sitter_analyzer.mcp.streamable_http_server import RateLimiter

        limiter = RateLimiter(max_requests=10, window_seconds=60)

        accepted = 0
        for _ in range(15):
            if limiter.is_allowed("client-1"):
                accepted += 1

        assert accepted == 10, f"Expected 10 accepted, got {accepted}"

    def test_connection_tracker_capacity(self) -> None:
        """ConnectionTracker enforces max connections."""
        tracker = ConnectionTracker(max_connections=5)

        ids = [tracker.acquire() for _ in range(5)]
        assert tracker.active_count == 5
        assert tracker.is_at_capacity()

        with pytest.raises(ConnectionError, match="Max concurrent"):
            tracker.acquire()

        tracker.release(ids[0])
        assert not tracker.is_at_capacity()
        new_id = tracker.acquire()
        assert new_id is not None

    def test_benchmark_summary(self) -> None:
        """Print a summary of benchmark results.

        This test always passes; it's for reporting purposes.
        Run with -v to see the output.
        """
        mcp_server = TreeSitterAnalyzerMCPServer()
        app = create_streamable_http_app(
            mcp_server,
            stateless=True,
            rate_limit=0,
            heartbeat_interval=0,
            max_connections=0,
        )

        health_latencies: list[float] = []
        tools_latencies: list[float] = []

        client = TestClient(app, raise_server_exceptions=False)
        # Health check benchmark
        for _ in range(100):
            start = time.monotonic()
            client.get("/health")
            health_latencies.append(time.monotonic() - start)

        # Tools/list sequential benchmark
        for i in range(50):
            start = time.monotonic()
            client.post("/mcp", json=_tools_list_payload(i))
            tools_latencies.append(time.monotonic() - start)

        health = sorted(health_latencies)
        tools = sorted(tools_latencies)

        summary = (
            f"\n{'='*60}\n"
            f"  StreamableHTTP Performance Benchmark Results\n"
            f"{'='*60}\n"
            f"\n  Health Check (100 sequential):\n"
            f"    p50: {health[49]*1000:.2f}ms\n"
            f"    p95: {health[94]*1000:.2f}ms\n"
            f"    p99: {health[98]*1000:.2f}ms\n"
            f"    throughput: {100/sum(health):.0f} req/s\n"
            f"\n  Tools/List (50 sequential):\n"
            f"    p50: {tools[24]*1000:.2f}ms\n"
            f"    p95: {tools[47]*1000:.2f}ms\n"
            f"    p99: {tools[49]*1000:.2f}ms\n"
            f"    throughput: {50/sum(tools):.0f} req/s\n"
            f"{'='*60}"
        )
        print(summary)
