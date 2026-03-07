#!/usr/bin/env python3
"""
Async File Reader

Provides asynchronous file reading capabilities with:
- Non-blocking file I/O
- Connection pooling
- Timeout handling
- Progress callbacks

Phase 3 Performance Enhancement.
"""

import asyncio
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils import log_debug, log_warning


@dataclass
class AsyncReadResult:
    """Result of an async file read operation."""
    file_path: str
    content: str
    size_bytes: int
    read_time_ms: float
    encoding: str
    success: bool = True
    error: str | None = None


@dataclass
class AsyncReaderStats:
    """Statistics for async file reading."""
    files_read: int = 0
    total_bytes_read: int = 0
    total_read_time_ms: float = 0.0
    cache_hits: int = 0
    errors: int = 0
    active_reads: int = 0


class AsyncFileReader:
    """
    Asynchronous file reader with connection pooling.

    Provides non-blocking file reading using a thread pool executor,
    enabling concurrent file reads without blocking the main event loop.

    Attributes:
        _executor: Thread pool for file I/O
        _max_workers: Maximum concurrent file reads
        _stats: Reading statistics
        _lock: Thread lock for statistics
    """

    def __init__(
        self,
        max_workers: int = 4,
        default_encoding: str = "utf-8",
        default_timeout: float = 30.0,
    ) -> None:
        """
        Initialize async file reader.

        Args:
            max_workers: Maximum concurrent file reads
            default_encoding: Default file encoding
            default_timeout: Default read timeout in seconds
        """
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_workers = max_workers
        self._default_encoding = default_encoding
        self._default_timeout = default_timeout
        self._stats = AsyncReaderStats()
        self._lock = threading.Lock()

        log_debug(
            f"AsyncFileReader initialized: max_workers={max_workers}, "
            f"timeout={default_timeout}s"
        )

    async def read_file(
        self,
        file_path: str | Path,
        encoding: str | None = None,
        timeout: float | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> AsyncReadResult:
        """
        Read file asynchronously.

        Args:
            file_path: Path to file
            encoding: File encoding (default: utf-8)
            timeout: Read timeout in seconds
            progress_callback: Callback(bytes_read, total_bytes)

        Returns:
            AsyncReadResult with content and metadata
        """
        import time

        file_path = Path(file_path)
        encoding = encoding or self._default_encoding
        timeout = timeout or self._default_timeout

        with self._lock:
            self._stats.active_reads += 1

        start_time = time.time()

        try:
            # Run file read in thread pool
            loop = asyncio.get_event_loop()

            def _read_sync() -> tuple[str, int]:
                """Synchronous file read for thread pool."""
                size = os.path.getsize(file_path)

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(0, size)

                with open(file_path, encoding=encoding) as f:
                    content = f.read()

                if progress_callback:
                    progress_callback(size, size)

                return content, size

            # Execute with timeout
            try:
                content, size = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, _read_sync),
                    timeout=timeout,
                )
            except asyncio.TimeoutError as timeout_error:
                raise TimeoutError(
                    f"File read timed out after {timeout}s: {file_path}"
                ) from timeout_error

            read_time_ms = (time.time() - start_time) * 1000

            # Update statistics
            with self._lock:
                self._stats.files_read += 1
                self._stats.total_bytes_read += size
                self._stats.total_read_time_ms += read_time_ms
                self._stats.active_reads -= 1

            return AsyncReadResult(
                file_path=str(file_path),
                content=content,
                size_bytes=size,
                read_time_ms=read_time_ms,
                encoding=encoding,
                success=True,
            )

        except Exception as e:
            read_time_ms = (time.time() - start_time) * 1000

            with self._lock:
                self._stats.errors += 1
                self._stats.active_reads -= 1

            log_warning(f"Async read error for {file_path}: {e}")

            return AsyncReadResult(
                file_path=str(file_path),
                content="",
                size_bytes=0,
                read_time_ms=read_time_ms,
                encoding=encoding,
                success=False,
                error=str(e),
            )

    async def read_files(
        self,
        file_paths: list[str | Path],
        encoding: str | None = None,
        timeout: float | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> list[AsyncReadResult]:
        """
        Read multiple files concurrently.

        Args:
            file_paths: List of file paths
            encoding: File encoding
            timeout: Per-file timeout
            progress_callback: Callback(file_path, index, total)

        Returns:
            List of AsyncReadResult objects
        """
        total = len(file_paths)

        async def _read_with_progress(index: int, path: str | Path) -> AsyncReadResult:
            result = await self.read_file(
                path,
                encoding=encoding,
                timeout=timeout,
            )

            if progress_callback:
                progress_callback(str(path), index, total)

            return result

        # Read all files concurrently
        tasks = [
            _read_with_progress(i, path)
            for i, path in enumerate(file_paths)
        ]

        gathered_results: list[AsyncReadResult | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        # Convert exceptions to error results
        final_results: list[AsyncReadResult] = []
        for i, result in enumerate(gathered_results):
            if isinstance(result, BaseException):
                final_results.append(AsyncReadResult(
                    file_path=str(file_paths[i]),
                    content="",
                    size_bytes=0,
                    read_time_ms=0,
                    encoding=encoding or self._default_encoding,
                    success=False,
                    error=str(result),
                ))
            else:
                final_results.append(result)

        return final_results

    async def read_file_chunked(
        self,
        file_path: str | Path,
        chunk_size: int = 1024 * 1024,  # 1MB chunks
        encoding: str | None = None,
        chunk_callback: Callable[[str, int, int], None] | None = None,
    ) -> AsyncReadResult:
        """
        Read file in chunks for progress reporting.

        Args:
            file_path: Path to file
            chunk_size: Size of each chunk
            encoding: File encoding
            chunk_callback: Callback(chunk_content, chunk_num, total_chunks)

        Returns:
            AsyncReadResult with complete content
        """
        import time

        file_path = Path(file_path)
        encoding = encoding or self._default_encoding

        start_time = time.time()

        try:
            content_parts: list[str] = []

            def _read_chunked_sync() -> str:
                """Read file in chunks synchronously."""
                with open(file_path, encoding=encoding) as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        content_parts.append(chunk)
                return "".join(content_parts)

            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(self._executor, _read_chunked_sync)

            read_time_ms = (time.time() - start_time) * 1000

            with self._lock:
                self._stats.files_read += 1
                self._stats.total_bytes_read += len(content.encode(encoding))
                self._stats.total_read_time_ms += read_time_ms

            return AsyncReadResult(
                file_path=str(file_path),
                content=content,
                size_bytes=len(content.encode(encoding)),
                read_time_ms=read_time_ms,
                encoding=encoding,
                success=True,
            )

        except Exception as e:
            read_time_ms = (time.time() - start_time) * 1000

            with self._lock:
                self._stats.errors += 1

            return AsyncReadResult(
                file_path=str(file_path),
                content="",
                size_bytes=0,
                read_time_ms=read_time_ms,
                encoding=encoding,
                success=False,
                error=str(e),
            )

    def get_stats(self) -> dict[str, Any]:
        """
        Get reading statistics.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            avg_read_time = (
                self._stats.total_read_time_ms / self._stats.files_read
                if self._stats.files_read > 0
                else 0.0
            )

            return {
                "files_read": self._stats.files_read,
                "total_bytes_read": self._stats.total_bytes_read,
                "total_mb_read": self._stats.total_bytes_read / (1024 * 1024),
                "total_read_time_ms": self._stats.total_read_time_ms,
                "avg_read_time_ms": avg_read_time,
                "cache_hits": self._stats.cache_hits,
                "errors": self._stats.errors,
                "active_reads": self._stats.active_reads,
                "max_workers": self._max_workers,
            }

    def shutdown(self) -> None:
        """Shutdown the executor."""
        self._executor.shutdown(wait=True)
        log_debug("AsyncFileReader shutdown complete")

    def __del__(self) -> None:
        """Destructor - ensure cleanup."""
        try:
            self.shutdown()
        except Exception:
            pass


# Singleton instance
_reader: AsyncFileReader | None = None
_reader_lock = threading.Lock()


def get_async_file_reader(
    max_workers: int = 4,
    **kwargs: Any,
) -> AsyncFileReader:
    """
    Get or create async file reader singleton.

    Args:
        max_workers: Maximum concurrent reads
        **kwargs: Additional arguments

    Returns:
        AsyncFileReader instance
    """
    global _reader

    with _reader_lock:
        if _reader is None:
            _reader = AsyncFileReader(max_workers=max_workers, **kwargs)
        return _reader
