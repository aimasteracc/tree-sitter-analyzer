#!/usr/bin/env python3
"""Tests for timeout protection module."""

import asyncio
import sys

import pytest

from tree_sitter_analyzer.core.timeout import (
    AnalysisTimeoutError,
    TimeoutGuard,
    with_sync_timeout,
)


class TestAnalysisTimeoutError:
    def test_message_format(self) -> None:
        err = AnalysisTimeoutError("parse_file", 10.0)
        assert "parse_file" in str(err)
        assert "10.0" in str(err)
        assert err.operation == "parse_file"
        assert err.timeout_seconds == 10.0


class TestTimeoutGuard:
    @pytest.mark.asyncio
    async def test_normal_completion_within_timeout(self) -> None:
        async with TimeoutGuard("test_op", timeout=5.0) as guard:
            await asyncio.sleep(0.01)
        assert not guard.timed_out

    @pytest.mark.asyncio
    async def test_timeout_raises_error(self) -> None:
        guard = TimeoutGuard("slow_op", timeout=0.05)

        async def slow() -> None:
            await asyncio.sleep(10.0)

        with pytest.raises(AnalysisTimeoutError) as exc_info:
            await guard.wrap_coroutine(slow())
        assert exc_info.value.operation == "slow_op"
        assert guard.timed_out

    @pytest.mark.asyncio
    async def test_wrap_coroutine_success(self) -> None:
        async def quick_task() -> str:
            return "done"

        guard = TimeoutGuard("quick", timeout=5.0)
        result = await guard.wrap_coroutine(quick_task())
        assert result == "done"

    @pytest.mark.asyncio
    async def test_wrap_coroutine_timeout(self) -> None:
        async def slow_task() -> str:
            await asyncio.sleep(10.0)
            return "never"

        guard = TimeoutGuard("slow", timeout=0.05)
        with pytest.raises(AnalysisTimeoutError):
            await guard.wrap_coroutine(slow_task())

    @pytest.mark.asyncio
    async def test_timed_out_property_default_false(self) -> None:
        guard = TimeoutGuard("test", timeout=1.0)
        assert not guard.timed_out


class TestTimeoutGuardDecorator:
    @pytest.mark.asyncio
    async def test_decorator_normal_flow(self) -> None:
        @TimeoutGuard.decorate(timeout=5.0)
        async def fast_func() -> int:
            return 42

        result = await fast_func()
        assert result == 42

    @pytest.mark.asyncio
    async def test_decorator_timeout(self) -> None:
        @TimeoutGuard.decorate(operation="slow_func", timeout=0.05)
        async def slow_func() -> int:
            await asyncio.sleep(10.0)
            return 0

        with pytest.raises(AnalysisTimeoutError) as exc_info:
            await slow_func()
        assert exc_info.value.operation == "slow_func"

    @pytest.mark.asyncio
    async def test_decorator_uses_function_name(self) -> None:
        @TimeoutGuard.decorate(timeout=0.05)
        async def my_operation() -> None:
            await asyncio.sleep(10.0)

        with pytest.raises(AnalysisTimeoutError) as exc_info:
            await my_operation()
        assert exc_info.value.operation == "my_operation"

    @pytest.mark.asyncio
    async def test_decorator_preserves_return_value(self) -> None:
        @TimeoutGuard.decorate(timeout=5.0)
        async def compute() -> dict[str, int]:
            return {"a": 1, "b": 2}

        result = await compute()
        assert result == {"a": 1, "b": 2}


class TestSyncTimeoutDecorator:
    def test_normal_completion(self) -> None:
        @with_sync_timeout(timeout=5.0)
        def fast_sync() -> str:
            return "ok"

        assert fast_sync() == "ok"

    def test_preserves_return_value(self) -> None:
        @with_sync_timeout(timeout=5.0)
        def compute() -> list[int]:
            return [1, 2, 3]

        assert compute() == [1, 2, 3]

    @pytest.mark.skipif(sys.platform == "win32", reason="No SIGALRM on Windows")
    def test_timeout_raises(self) -> None:
        import time

        @with_sync_timeout(operation="blocked", timeout=0.1)
        def blocked() -> str:
            time.sleep(10.0)
            return "never"

        with pytest.raises(AnalysisTimeoutError) as exc_info:
            blocked()
        assert exc_info.value.operation == "blocked"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows fallback")
    def test_windows_fallback_no_timeout(self) -> None:
        import time

        @with_sync_timeout(timeout=0.01)
        def will_run() -> str:
            time.sleep(0.1)
            return "done"

        assert will_run() == "done"


class TestTimeoutWithAnalysisRequest:
    @pytest.mark.asyncio
    async def test_request_default_timeout(self) -> None:
        from tree_sitter_analyzer.core.request import AnalysisRequest

        req = AnalysisRequest(file_path="test.py")
        assert req.timeout_seconds == 30.0

    @pytest.mark.asyncio
    async def test_request_custom_timeout(self) -> None:
        from tree_sitter_analyzer.core.request import AnalysisRequest

        req = AnalysisRequest(file_path="test.py", timeout_seconds=5.0)
        assert req.timeout_seconds == 5.0
