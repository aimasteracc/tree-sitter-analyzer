#!/usr/bin/env python3
"""
Cache Prewarming Service

Preloads frequently accessed files into cache to improve initial performance.
Analyzes access patterns to predict which files should be preloaded.

Phase 3 Performance Enhancement.
"""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..utils import log_debug, log_info


@dataclass
class FileAccessPattern:
    """
    Tracks file access patterns for prewarming predictions.

    Attributes:
        file_path: Path to the file
        access_count: Number of times accessed
        last_accessed: Timestamp of last access
        avg_load_time_ms: Average load time in milliseconds
        priority_score: Calculated priority score
    """
    file_path: str
    access_count: int = 0
    last_accessed: datetime | None = None
    avg_load_time_ms: float = 0.0
    total_load_time_ms: float = 0.0
    priority_score: float = 0.0


@dataclass
class PrewarmingStats:
    """Statistics for cache prewarming operations."""
    files_prewarmed: int = 0
    cache_hits_from_prewarmed: int = 0
    total_prewarming_time_ms: float = 0.0
    bytes_prewarmed: int = 0
    prewarming_errors: int = 0


class CachePrewarmer:
    """
    Cache prewarming service for predictive cache loading.

    Analyzes file access patterns and preloads frequently accessed files
    into cache before they are requested, reducing initial load latency.

    Attributes:
        _access_patterns: Dictionary tracking file access patterns
        _stats: Prewarming statistics
        _lock: Thread lock for statistics
        _max_prewarm_files: Maximum files to prewarm at once
        _min_access_count: Minimum accesses to consider for prewarming
    """

    def __init__(
        self,
        max_prewarm_files: int = 50,
        min_access_count: int = 3,
        prewarm_on_startup: bool = True,
    ) -> None:
        """
        Initialize cache prewarmer.

        Args:
            max_prewarm_files: Maximum number of files to prewarm
            min_access_count: Minimum access count to qualify for prewarming
            prewarm_on_startup: Whether to prewarm on initialization
        """
        self._access_patterns: dict[str, FileAccessPattern] = {}
        self._stats = PrewarmingStats()
        self._lock = threading.Lock()
        self._max_prewarm_files = max_prewarm_files
        self._min_access_count = min_access_count
        self._prewarm_callback: Callable[[str], Any] | None = None

        log_debug(
            f"CachePrewarmer initialized: max_files={max_prewarm_files}, "
            f"min_access={min_access_count}"
        )

    def set_prewarm_callback(self, callback: Callable[[str], Any]) -> None:
        """
        Set callback function for prewarming files.

        Args:
            callback: Async function that loads a file and returns result
        """
        self._prewarm_callback = callback

    def record_access(
        self, file_path: str, load_time_ms: float = 0.0
    ) -> None:
        """
        Record a file access for pattern analysis.

        Args:
            file_path: Path to the accessed file
            load_time_ms: Time taken to load the file in milliseconds
        """
        with self._lock:
            if file_path not in self._access_patterns:
                self._access_patterns[file_path] = FileAccessPattern(
                    file_path=file_path
                )

            pattern = self._access_patterns[file_path]
            pattern.access_count += 1
            pattern.last_accessed = datetime.now()
            pattern.total_load_time_ms += load_time_ms
            pattern.avg_load_time_ms = (
                pattern.total_load_time_ms / pattern.access_count
            )

            # Update priority score
            self._update_priority_score(pattern)

    def _update_priority_score(self, pattern: FileAccessPattern) -> None:
        """
        Calculate priority score for a file pattern.

        Higher score = higher priority for prewarming.

        Args:
            pattern: File access pattern to update
        """
        # Factors: access count, recency, load time
        recency_hours = 0.0
        if pattern.last_accessed:
            delta = datetime.now() - pattern.last_accessed
            recency_hours = delta.total_seconds() / 3600

        # Score formula:
        # - More accesses = higher score
        # - More recent = higher score (exponential decay)
        # - Longer load time = higher score (more benefit from caching)
        recency_factor = 1.0 / (1.0 + recency_hours / 24.0)  # Decay over 24 hours
        load_time_factor = min(pattern.avg_load_time_ms / 100.0, 3.0)  # Cap at 3x

        pattern.priority_score = (
            pattern.access_count * 10.0 *  # Base weight for frequency
            recency_factor *                # Recency weight
            load_time_factor                # Load time weight
        )

    def get_prewarm_candidates(self, limit: int | None = None) -> list[str]:
        """
        Get list of files to prewarm based on access patterns.

        Args:
            limit: Maximum number of files to return (default: _max_prewarm_files)

        Returns:
            List of file paths sorted by priority
        """
        limit = limit or self._max_prewarm_files

        with self._lock:
            # Filter files that meet minimum access count
            candidates = [
                pattern
                for pattern in self._access_patterns.values()
                if pattern.access_count >= self._min_access_count
            ]

            # Sort by priority score (descending)
            candidates.sort(key=lambda p: p.priority_score, reverse=True)

            return [p.file_path for p in candidates[:limit]]

    async def prewarm_cache(
        self, file_paths: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Prewarm cache by loading specified or predicted files.

        Args:
            file_paths: Specific files to prewarm, or None to use predictions

        Returns:
            Dictionary with prewarming results
        """
        if not self._prewarm_callback:
            log_debug("No prewarm callback set, skipping prewarming")
            return {"status": "no_callback", "files_prewarmed": 0}

        files_to_prewarm = file_paths or self.get_prewarm_candidates()

        if not files_to_prewarm:
            log_debug("No files to prewarm")
            return {"status": "no_candidates", "files_prewarmed": 0}

        start_time = time.time()
        files_prewarmed = 0
        bytes_loaded = 0
        errors: list[str] = []

        log_info(f"Starting cache prewarming for {len(files_to_prewarm)} files")

        for file_path in files_to_prewarm:
            try:
                # Check if file exists
                if not os.path.exists(file_path):
                    continue

                # Get file size
                file_size = os.path.getsize(file_path)

                # Load file via callback
                await self._prewarm_callback(file_path)

                files_prewarmed += 1
                bytes_loaded += file_size

                with self._lock:
                    self._stats.files_prewarmed += 1
                    self._stats.bytes_prewarmed += file_size

            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")
                with self._lock:
                    self._stats.prewarming_errors += 1
                log_debug(f"Prewarming error for {file_path}: {e}")

        elapsed_ms = (time.time() - start_time) * 1000

        with self._lock:
            self._stats.total_prewarming_time_ms += elapsed_ms

        log_info(
            f"Cache prewarming complete: {files_prewarmed} files, "
            f"{bytes_loaded / 1024:.1f}KB in {elapsed_ms:.1f}ms"
        )

        return {
            "status": "success",
            "files_prewarmed": files_prewarmed,
            "errors": errors,
            "bytes_loaded": bytes_loaded,
            "elapsed_ms": elapsed_ms,
        }

    def get_stats(self) -> dict[str, Any]:
        """
        Get prewarming statistics.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            return {
                "files_prewarmed": self._stats.files_prewarmed,
                "cache_hits_from_prewarmed": self._stats.cache_hits_from_prewarmed,
                "total_prewarming_time_ms": self._stats.total_prewarming_time_ms,
                "bytes_prewarmed": self._stats.bytes_prewarmed,
                "prewarming_errors": self._stats.prewarming_errors,
                "tracked_files": len(self._access_patterns),
                "candidates_count": len(self.get_prewarm_candidates()),
            }

    def clear_patterns(self) -> None:
        """Clear all access patterns."""
        with self._lock:
            self._access_patterns.clear()
        log_debug("Access patterns cleared")
