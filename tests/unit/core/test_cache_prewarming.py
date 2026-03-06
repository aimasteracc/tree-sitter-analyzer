#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.core.cache_prewarming module.

Phase 3 Performance Enhancement Tests.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tree_sitter_analyzer.core.cache_prewarming import (
    CachePrewarmer,
    FileAccessPattern,
    PrewarmingStats,
)


class TestFileAccessPattern:
    """Test cases for FileAccessPattern dataclass."""

    def test_creation(self) -> None:
        """Test pattern creation."""
        pattern = FileAccessPattern(file_path="/test/file.py")
        
        assert pattern.file_path == "/test/file.py"
        assert pattern.access_count == 0
        assert pattern.last_accessed is None
        assert pattern.avg_load_time_ms == 0.0

    def test_priority_score_update(self) -> None:
        """Test that priority score is calculated."""
        pattern = FileAccessPattern(
            file_path="/test/file.py",
            access_count=5,
            avg_load_time_ms=100.0,
        )
        
        # Priority score should be non-negative
        assert pattern.priority_score >= 0


class TestPrewarmingStats:
    """Test cases for PrewarmingStats dataclass."""

    def test_defaults(self) -> None:
        """Test default values."""
        stats = PrewarmingStats()
        
        assert stats.files_prewarmed == 0
        assert stats.cache_hits_from_prewarmed == 0
        assert stats.total_prewarming_time_ms == 0.0
        assert stats.bytes_prewarmed == 0
        assert stats.prewarming_errors == 0


class TestCachePrewarmer:
    """Test cases for CachePrewarmer class."""

    @pytest.fixture
    def prewarmer(self) -> CachePrewarmer:
        """Create a CachePrewarmer instance."""
        return CachePrewarmer(
            max_prewarm_files=10,
            min_access_count=2,
        )

    @pytest.fixture
    def prewarmer_with_files(self, tmp_path: Path) -> CachePrewarmer:
        """Create a prewarmer with test files."""
        prewarmer = CachePrewarmer(max_prewarm_files=10, min_access_count=1)
        
        # Create test files
        for i in range(5):
            (tmp_path / f"test_{i}.py").write_text(f"# Test file {i}")
        
        return prewarmer

    def test_initialization(self, prewarmer: CachePrewarmer) -> None:
        """Test prewarmer initialization."""
        assert prewarmer._max_prewarm_files == 10
        assert prewarmer._min_access_count == 2
        assert len(prewarmer._access_patterns) == 0

    def test_record_access(self, prewarmer: CachePrewarmer) -> None:
        """Test recording file accesses."""
        prewarmer.record_access("/test/file.py", load_time_ms=50.0)
        prewarmer.record_access("/test/file.py", load_time_ms=100.0)
        
        assert "/test/file.py" in prewarmer._access_patterns
        pattern = prewarmer._access_patterns["/test/file.py"]
        
        assert pattern.access_count == 2
        assert pattern.total_load_time_ms == 150.0
        assert pattern.avg_load_time_ms == 75.0

    def test_get_prewarm_candidates_empty(self, prewarmer: CachePrewarmer) -> None:
        """Test getting candidates when none qualify."""
        # Record single access (below min_access_count=2)
        prewarmer.record_access("/test/file.py")
        
        candidates = prewarmer.get_prewarm_candidates()
        assert len(candidates) == 0

    def test_get_prewarm_candidates_qualified(
        self, prewarmer: CachePrewarmer
    ) -> None:
        """Test getting candidates that qualify."""
        # Record multiple accesses
        for _ in range(3):
            prewarmer.record_access("/test/file1.py")
            prewarmer.record_access("/test/file2.py")
        
        candidates = prewarmer.get_prewarm_candidates()
        assert len(candidates) == 2

    def test_get_prewarm_candidates_sorted(self) -> None:
        """Test candidates are sorted by priority."""
        prewarmer = CachePrewarmer(min_access_count=1)
        
        # File with more accesses should have higher priority
        for _ in range(10):
            prewarmer.record_access("/test/high.py")
        
        for _ in range(2):
            prewarmer.record_access("/test/low.py")
        
        candidates = prewarmer.get_prewarm_candidates()
        
        assert candidates[0] == "/test/high.py"
        assert candidates[1] == "/test/low.py"

    def test_get_stats(self, prewarmer: CachePrewarmer) -> None:
        """Test statistics retrieval."""
        stats = prewarmer.get_stats()
        
        assert "files_prewarmed" in stats
        assert "tracked_files" in stats
        assert "candidates_count" in stats
        assert stats["tracked_files"] == 0

    def test_clear_patterns(self, prewarmer: CachePrewarmer) -> None:
        """Test clearing access patterns."""
        prewarmer.record_access("/test/file.py")
        prewarmer.record_access("/test/file.py")
        
        assert len(prewarmer._access_patterns) == 1
        
        prewarmer.clear_patterns()
        
        assert len(prewarmer._access_patterns) == 0

    @pytest.mark.asyncio
    async def test_prewarm_cache_no_callback(
        self, prewarmer: CachePrewarmer
    ) -> None:
        """Test prewarming without callback."""
        result = await prewarmer.prewarm_cache()
        
        assert result["status"] == "no_callback"
        assert result["files_prewarmed"] == 0

    @pytest.mark.asyncio
    async def test_prewarm_cache_no_candidates(
        self, prewarmer: CachePrewarmer
    ) -> None:
        """Test prewarming with no candidates."""
        callback = AsyncMock()
        prewarmer.set_prewarm_callback(callback)
        
        result = await prewarmer.prewarm_cache()
        
        assert result["status"] == "no_candidates"
        assert result["files_prewarmed"] == 0

    @pytest.mark.asyncio
    async def test_prewarm_cache_success(
        self, tmp_path: Path
    ) -> None:
        """Test successful cache prewarming."""
        prewarmer = CachePrewarmer(min_access_count=1)
        
        # Create test files
        files = []
        for i in range(3):
            file_path = tmp_path / f"test_{i}.py"
            file_path.write_text(f"# Test {i}")
            files.append(str(file_path))
            prewarmer.record_access(str(file_path))
        
        # Set callback
        callback = AsyncMock()
        prewarmer.set_prewarm_callback(callback)
        
        result = await prewarmer.prewarm_cache(files)
        
        assert result["status"] == "success"
        assert result["files_prewarmed"] == 3
        assert callback.call_count == 3

    @pytest.mark.asyncio
    async def test_prewarm_cache_with_errors(
        self, tmp_path: Path
    ) -> None:
        """Test prewarming with some errors."""
        prewarmer = CachePrewarmer(min_access_count=1)
        
        # Create test file
        file_path = tmp_path / "test.py"
        file_path.write_text("# Test")
        prewarmer.record_access(str(file_path))
        
        # Also record non-existent file
        prewarmer.record_access("/nonexistent/file.py")
        
        # Set callback that fails for nonexistent
        async def failing_callback(path: str) -> None:
            if "nonexistent" in path:
                raise FileNotFoundError("File not found")
        
        prewarmer.set_prewarm_callback(failing_callback)
        
        result = await prewarmer.prewarm_cache([
            str(file_path),
            "/nonexistent/file.py",
        ])
        
        assert result["status"] == "success"
        assert result["files_prewarmed"] == 1  # Only existing file
        assert len(result["errors"]) == 1


class TestCachePrewarmerIntegration:
    """Integration tests for CachePrewarmer."""

    def test_thread_safety(self) -> None:
        """Test concurrent access pattern recording."""
        import threading
        
        prewarmer = CachePrewarmer()
        errors = []
        
        def record_accesses():
            try:
                for i in range(100):
                    prewarmer.record_access(f"/test/file_{i % 10}.py")
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=record_accesses) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        stats = prewarmer.get_stats()
        assert stats["tracked_files"] == 10  # 10 unique files


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
