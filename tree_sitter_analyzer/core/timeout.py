#!/usr/bin/env python3
"""
Timeout protection for analysis operations.

Provides async timeout context manager and decorator to prevent
analysis operations from hanging indefinitely on large or complex files.
"""

import asyncio
import functools
import logging
import signal
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

DEFAULT_ANALYSIS_TIMEOUT = 30.0
DEFAULT_PARSE_TIMEOUT = 10.0


class AnalysisTimeoutError(Exception):
    """Raised when an analysis operation exceeds its time limit."""

    def __init__(self, operation: str, timeout_seconds: float) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Operation '{operation}' timed out after {timeout_seconds:.1f}s"
        )


class TimeoutGuard:
    """
    Async-compatible timeout guard for analysis operations.

    Usage as context manager:
        async with TimeoutGuard("parse_file", timeout=10.0):
            await slow_operation()

    Usage as decorator:
        @TimeoutGuard.decorate(timeout=30.0)
        async def analyze_file(...):
            ...
    """

    def __init__(
        self,
        operation: str = "unknown",
        timeout: float = DEFAULT_ANALYSIS_TIMEOUT,
    ) -> None:
        self._operation = operation
        self._timeout = timeout
        self._task: asyncio.Task[Any] | None = None
        self._timed_out = False

    @property
    def timed_out(self) -> bool:
        return self._timed_out

    async def __aenter__(self) -> "TimeoutGuard":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        if self._timed_out and exc_type is None:
            raise AnalysisTimeoutError(self._operation, self._timeout)
        if isinstance(exc_val, asyncio.TimeoutError):
            self._timed_out = True
            raise AnalysisTimeoutError(self._operation, self._timeout) from exc_val
        return False

    def wrap_coroutine(self, coro: Any) -> Any:
        """Wrap a coroutine with asyncio.wait_for, raising AnalysisTimeoutError."""
        return self._wrap(coro)

    async def _wrap(self, coro: Any) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=self._timeout)
        except asyncio.TimeoutError as err:
            self._timed_out = True
            raise AnalysisTimeoutError(self._operation, self._timeout) from err

    @classmethod
    def decorate(
        cls,
        operation: str | None = None,
        timeout: float = DEFAULT_ANALYSIS_TIMEOUT,
    ) -> Callable[..., Any]:
        """
        Decorator that wraps an async function with timeout protection.

        Args:
            operation: Name of the operation (defaults to function name)
            timeout: Maximum seconds before timeout
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            op_name = operation or func.__name__

            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await asyncio.wait_for(
                        func(*args, **kwargs), timeout=timeout
                    )
                except asyncio.TimeoutError as err:
                    logger.warning(
                        "Timeout: %s exceeded %.1fs", op_name, timeout
                    )
                    raise AnalysisTimeoutError(op_name, timeout) from err

            return wrapper

        return decorator


def with_sync_timeout(
    operation: str | None = None,
    timeout: float = DEFAULT_ANALYSIS_TIMEOUT,
) -> Callable[..., Any]:
    """
    Decorator for synchronous functions using signal-based timeout (Unix only).

    Falls back gracefully on Windows — no timeout enforcement, just runs normally.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        op_name = operation or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import sys

            if sys.platform == "win32":
                return func(*args, **kwargs)

            def _handler(signum: int, frame: Any) -> None:
                raise AnalysisTimeoutError(op_name, timeout)

            old_handler = signal.signal(signal.SIGALRM, _handler)
            signal.setitimer(signal.ITIMER_REAL, timeout)
            try:
                return func(*args, **kwargs)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper

    return decorator


F = TypeVar("F", bound=Callable[..., Any])
