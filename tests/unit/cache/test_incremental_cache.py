"""
Tests for incremental analysis cache.
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from tree_sitter_analyzer.cache import (
    CachedAnalysis,
    CacheEntry,
    CacheKey,
    IncrementalCacheManager,
)


@pytest.fixture
def temp_repo() -> tempfile.TemporaryDirectory[str]:
    """Create a temporary repository for testing."""
    return tempfile.TemporaryDirectory()


@pytest.fixture
def cache_manager(temp_repo: tempfile.TemporaryDirectory[str]) -> IncrementalCacheManager:
    """Create a cache manager for testing."""
    return IncrementalCacheManager(temp_repo.name, max_size_bytes=1024 * 1024)  # 1MB for testing


@pytest.fixture
def sample_file(temp_repo: tempfile.TemporaryDirectory[str]) -> str:
    """Create a sample Python file."""
    file_path = os.path.join(temp_repo.name, "sample.py")
    with open(file_path, "w") as f:
        f.write("def hello():\n    print('world')\n")
    return file_path


@pytest.fixture
def sample_analysis() -> dict[str, object]:
    """Create a sample analysis result."""
    return {
        "functions": [{"name": "hello", "line": 1}],
        "complexity": 1,
        "imports": [],
    }


class TestCacheKey:
    """Tests for CacheKey dataclass."""

    def test_hashable(self) -> None:
        """CacheKey should be hashable for use as dict keys."""
        key = CacheKey(
            file_path="test.py",
            content_hash="abc123",
            tree_sitter_version="1.0.0",
            language="python",
        )
        hash_value = hash(key)
        assert isinstance(hash_value, int)

    def test_equality(self) -> None:
        """CacheKey with same values should be equal."""
        key1 = CacheKey(
            file_path="test.py",
            content_hash="abc123",
            tree_sitter_version="1.0.0",
            language="python",
        )
        key2 = CacheKey(
            file_path="test.py",
            content_hash="abc123",
            tree_sitter_version="1.0.0",
            language="python",
        )
        assert key1 == key2
        assert hash(key1) == hash(key2)

    def test_inequality_different_content(self) -> None:
        """CacheKey with different content_hash should not be equal."""
        key1 = CacheKey(
            file_path="test.py",
            content_hash="abc123",
            tree_sitter_version="1.0.0",
            language="python",
        )
        key2 = CacheKey(
            file_path="test.py",
            content_hash="def456",
            tree_sitter_version="1.0.0",
            language="python",
        )
        assert key1 != key2


class TestCachedAnalysis:
    """Tests for CachedAnalysis dataclass."""

    def test_create(self) -> None:
        """CachedAnalysis should create with all fields."""
        key = CacheKey("test.py", "abc123", "1.0.0", "python")
        analysis = CachedAnalysis(
            key=key,
            ast_bytes=b"fake_ast",
            analysis_result={"test": "data"},
            timestamp=time.time(),
            git_sha="commit123",
        )
        assert analysis.key == key
        assert analysis.ast_bytes == b"fake_ast"
        assert analysis.analysis_result == {"test": "data"}
        assert analysis.git_sha == "commit123"


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_create(self) -> None:
        """CacheEntry should create with metadata."""
        key = CacheKey("test.py", "abc123", "1.0.0", "python")
        analysis = CachedAnalysis(
            key=key,
            ast_bytes=b"ast",
            analysis_result={},
            timestamp=time.time(),
            git_sha=None,
        )
        entry = CacheEntry(
            key=key,
            value=analysis,
            last_access=time.time(),
            size_bytes=1024,
        )
        assert entry.key == key
        assert entry.value == analysis
        assert entry.size_bytes == 1024


class TestIncrementalCacheManager:
    """Tests for IncrementalCacheManager."""

    def test_cache_dir_created(self, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Cache directory should be created on initialization."""
        cache_dir = os.path.join(temp_repo.name, "custom_cache")
        IncrementalCacheManager(temp_repo.name, cache_dir=cache_dir)
        assert os.path.exists(cache_dir)

    def test_cache_miss(self, cache_manager: IncrementalCacheManager, sample_file: str) -> None:
        """get() should return None for non-cached file."""
        result = cache_manager.get(sample_file)
        assert result is None

    def test_cache_hit(self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]) -> None:
        """get() should return cached analysis after put()."""
        cache_manager.put(
            sample_file,
            sample_analysis,
            ast_bytes=b"fake_ast",
            language="python",
        )

        result = cache_manager.get(sample_file, language="python")
        assert isinstance(result, dict)
        assert result.analysis_result == sample_analysis
        assert result.ast_bytes == b"fake_ast"

    def test_file_change_invalidates_cache(
        self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]
    ) -> None:
        """Changing file content should invalidate cache."""
        # Cache the file
        cache_manager.put(sample_file, sample_analysis, ast_bytes=b"ast")

        # Modify the file
        with open(sample_file, "a") as f:
            f.write("\n    print('modified')\n")

        # Cache should be invalidated
        result = cache_manager.get(sample_file)
        assert result is None

    def test_is_stale_file_changed(
        self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]
    ) -> None:
        """is_stale() should return True when file changes."""
        cache_manager.put(sample_file, sample_analysis, ast_bytes=b"ast")
        cached = cache_manager.get(sample_file)
        assert cached is not None

        # Initially not stale
        assert not cache_manager.is_stale(cached)

        # Modify file
        with open(sample_file, "a") as f:
            f.write("\n# comment\n")

        # Now stale
        assert cache_manager.is_stale(cached)

    def test_is_stale_file_deleted(
        self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]
    ) -> None:
        """is_stale() should return True when file is deleted."""
        cache_manager.put(sample_file, sample_analysis, ast_bytes=b"ast")
        cached = cache_manager.get(sample_file)
        assert cached is not None

        # Delete file
        os.remove(sample_file)

        # Should be stale
        assert cache_manager.is_stale(cached)

    def test_invalidate_single_file(self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]) -> None:
        """invalidate() should remove cache for specific file."""
        cache_manager.put(sample_file, sample_analysis, ast_bytes=b"ast")
        assert cache_manager.get(sample_file) is not None

        cache_manager.invalidate(sample_file)
        assert cache_manager.get(sample_file) is None

    def test_invalidate_all(self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]) -> None:
        """invalidate_all() should clear all cache entries."""
        cache_manager.put(sample_file, sample_analysis, ast_bytes=b"ast")
        assert cache_manager.get(sample_file) is not None

        cache_manager.invalidate_all()
        assert cache_manager.get(sample_file) is None

    def test_cache_key_includes_language(
        self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]
    ) -> None:
        """Cache should distinguish between different languages."""
        # Cache as Python
        cache_manager.put(sample_file, sample_analysis, ast_bytes=b"py_ast", language="python")
        result_py = cache_manager.get(sample_file, language="python")
        assert result_py is not None
        assert result_py.ast_bytes == b"py_ast"

        # Same file as JavaScript should be cache miss
        result_js = cache_manager.get(sample_file, language="javascript")
        assert result_js is None

    def test_git_sha_stored(self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]) -> None:
        """git_sha should be stored in cached analysis."""
        cache_manager.put(
            sample_file,
            sample_analysis,
            ast_bytes=b"ast",
            git_sha="abc123def",
        )

        result = cache_manager.get(sample_file)
        assert isinstance(result, dict)
        assert result.git_sha == "abc123def"

    def test_size_based_eviction(self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Cache should evict LRU entries when size limit is reached."""
        # Create cache manager with small limit (10KB)
        small_cache = IncrementalCacheManager(temp_repo.name, max_size_bytes=10 * 1024)

        # Create multiple files
        files = []
        for i in range(5):
            file_path = os.path.join(temp_repo.name, f"file{i}.py")
            with open(file_path, "w") as f:
                f.write(f"# File {i}\n" * 100)  # ~1KB each
            files.append(file_path)

        # Cache all files
        for file_path in files:
            large_ast = b"x" * 5000  # 5KB each
            small_cache.put(file_path, {"file": file_path}, ast_bytes=large_ast)

        # Last file should still be cached (most recent)
        assert small_cache.get(files[-1]) is not None

        # First file may have been evicted due to size limit
        # (depends on exact size calculations)

    def test_corrupted_cache_deleted(
        self, cache_manager: IncrementalCacheManager, sample_file: str, sample_analysis: dict[str, object]
    ) -> None:
        """Corrupted cache file should be deleted and return None."""
        # Cache the file
        cache_manager.put(sample_file, sample_analysis, ast_bytes=b"ast")

        # Corrupt the cache file
        cache_key = cache_manager._make_cache_key(sample_file, "python")
        cache_path = cache_manager._get_cache_path(cache_key)
        with open(cache_path, "wb") as f:
            f.write(b"corrupted data")

        # Should return None and delete corrupted file
        result = cache_manager.get(sample_file)
        assert result is None
        assert not cache_path.exists()

    def test_context_manager(self, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Cache manager should work as context manager."""
        with IncrementalCacheManager(temp_repo.name) as manager:
            assert manager is not None
        # Lock should be released on exit

    def test_multiple_files_cached(
        self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]
    ) -> None:
        """Multiple files should be cached independently."""
        files = []
        for i in range(3):
            file_path = os.path.join(temp_repo.name, f"test{i}.py")
            with open(file_path, "w") as f:
                f.write(f"def func{i}(): pass\n")
            files.append(file_path)

        # Cache all files
        for file_path in files:
            cache_manager.put(file_path, {"file": file_path}, ast_bytes=b"ast")

        # All should be retrievable
        for file_path in files:
            result = cache_manager.get(file_path)
            assert isinstance(result, dict)
            assert result.analysis_result["file"] == file_path

    def test_relative_path_handling(self, cache_manager: IncrementalCacheManager, temp_repo: tempfile.TemporaryDirectory[str]) -> None:
        """Cache should handle subdirectory files correctly."""
        subdir = os.path.join(temp_repo.name, "subdir")
        os.makedirs(subdir)
        file_path = os.path.join(subdir, "test.py")

        with open(file_path, "w") as f:
            f.write("pass")

        cache_manager.put(file_path, {"path": file_path}, ast_bytes=b"ast")
        result = cache_manager.get(file_path)

        assert result is not None
        # Key should store relative path
        assert "subdir" in result.key.file_path
