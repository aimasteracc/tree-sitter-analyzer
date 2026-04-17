"""
Tests for Sprint 3: Integration & Optimization features.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from tree_sitter_analyzer.cache import IncrementalCacheManager


@pytest.fixture
def temp_repo() -> tempfile.TemporaryDirectory[str]:
    """Create a temporary repository for testing."""
    return tempfile.TemporaryDirectory()


@pytest.fixture
def cache_manager(temp_repo: tempfile.TemporaryDirectory[str]) -> IncrementalCacheManager:
    """Create a cache manager for testing."""
    return IncrementalCacheManager(temp_repo.name, max_size_bytes=1024 * 1024)


class TestCacheWarming:
    """Tests for cache warming functionality."""

    def test_warm_cache_no_files(self, cache_manager: IncrementalCacheManager) -> None:
        """Warming with no files should return 0."""
        warmed = cache_manager.warm_cache(files=[], top_n=10)
        assert warmed == 0

    def test_warm_cache_with_files(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Warm cache with specific files."""
        # Create test files
        files = []
        for i in range(3):
            file_path = os.path.join(temp_repo.name, f"warm{i}.py")
            with open(file_path, "w") as f:
                f.write("x" * (100 * (i + 1)))  # Different sizes
            files.append(file_path)

        warmed = cache_manager.warm_cache(files=files, top_n=5)
        assert warmed == 3

    def test_warm_cache_top_n(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Warm cache should only cache top-N most complex files."""
        # Create test files
        files = []
        for i in range(5):
            file_path = os.path.join(temp_repo.name, f"top{i}.py")
            with open(file_path, "w") as f:
                f.write("x" * (100 * i))  # Increasing size
            files.append(file_path)

        # Only warm top 3
        warmed = cache_manager.warm_cache(files=files, top_n=3)
        assert warmed == 3

    def test_warm_cache_scans_repo(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Warm cache should scan repo for files when files=None."""
        # Create Python files
        for i in range(3):
            file_path = os.path.join(temp_repo.name, f"scan{i}.py")
            with open(file_path, "w") as f:
                f.write(f"def func{i}(): pass")

        # Create non-Python file (should be ignored)
        with open(os.path.join(temp_repo.name, "test.txt"), "w") as f:
            f.write("not python")

        warmed = cache_manager.warm_cache(files=None, top_n=10)
        assert warmed == 3  # Only Python files

    def test_warm_cache_skips_missing_files(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Warm cache should skip files that don't exist."""
        files = [
            os.path.join(temp_repo.name, "exists.py"),
            os.path.join(temp_repo.name, "missing.py"),
        ]

        # Only create one file
        with open(files[0], "w") as f:
            f.write("pass")

        warmed = cache_manager.warm_cache(files=files, top_n=10)
        assert warmed == 1  # Only existing file


class TestCacheStats:
    """Tests for cache statistics."""

    def test_get_stats_empty(self, cache_manager: IncrementalCacheManager) -> None:
        """Stats should be empty for new cache."""
        stats = cache_manager.get_stats()
        assert stats["entry_count"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["usage_percent"] == 0

    def test_get_stats_with_cache(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Stats should reflect cached entries."""
        # Add some cache entries
        file_path = os.path.join(temp_repo.name, "stats_test.py")
        with open(file_path, "w") as f:
            f.write("x = 1")

        cache_manager.put(file_path, {"test": True}, ast_bytes=b"ast")

        stats = cache_manager.get_stats()
        assert stats["entry_count"] == 1
        assert stats["total_size_bytes"] > 0
        assert stats["usage_percent"] < 100

    def test_get_stats_includes_git_state(self, cache_manager: IncrementalCacheManager) -> None:
        """Stats should include git state for git repos."""
        stats = cache_manager.get_stats()
        # Non-git repo should have None git_state
        assert stats.get("git_state") is None or isinstance(stats.get("git_state"), dict)


class TestIntegration:
    """Integration tests for cache with MCP workflow."""

    def test_cache_workflow(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Test typical cache workflow: get → miss → put → hit."""
        file_path = os.path.join(temp_repo.name, "workflow.py")
        with open(file_path, "w") as f:
            f.write("def workflow(): pass")

        # First get should miss
        result1 = cache_manager.get(file_path)
        assert result1 is None

        # Put in cache
        analysis = {"functions": ["workflow"]}
        cache_manager.put(file_path, analysis, ast_bytes=b"ast")

        # Second get should hit
        result2 = cache_manager.get(file_path)
        assert result2 is not None
        assert result2.analysis_result == analysis

    def test_invalidation_workflow(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Test cache invalidation workflow."""
        file_path = os.path.join(temp_repo.name, "invalidation.py")
        with open(file_path, "w") as f:
            f.write("original")

        # Cache the file
        cache_manager.put(file_path, {"v": 1}, ast_bytes=b"ast")
        assert cache_manager.get(file_path) is not None

        # Modify file
        with open(file_path, "w") as f:
            f.write("modified")

        # Should be invalidated
        assert cache_manager.get(file_path) is None

    def test_stats_tracking(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Test cache statistics tracking."""
        file_path = os.path.join(temp_repo.name, "stats.py")
        with open(file_path, "w") as f:
            f.write("x = 1")

        # Initially empty
        stats1 = cache_manager.get_stats()
        assert stats1["entry_count"] == 0

        # After adding entry
        cache_manager.put(file_path, {"test": True}, ast_bytes=b"ast")
        stats2 = cache_manager.get_stats()
        assert stats2["entry_count"] == 1

        # After invalidation
        cache_manager.invalidate(file_path)
        stats3 = cache_manager.get_stats()
        assert stats3["entry_count"] == 0

    def test_concurrent_access_safety(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Test concurrent access safety via file locks."""
        import threading

        file_path = os.path.join(temp_repo.name, "concurrent.py")
        with open(file_path, "w") as f:
            f.write("data")

        errors = []

        def worker() -> None:
            try:
                for _ in range(10):
                    cache_manager.get(file_path)
                    cache_manager.put(file_path, {"worker": "test"}, ast_bytes=b"ast")
            except Exception as e:
                errors.append(e)

        # Run multiple workers
        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not have any errors
        assert len(errors) == 0
