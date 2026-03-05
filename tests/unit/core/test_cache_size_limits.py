"""Tests for cache size limits and LRU eviction."""
import pytest


class TestCacheSizeLimits:
    """Test cache size limits and eviction."""

    def test_shared_cache_has_max_size(self):
        """SharedCache should have configurable max size."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache()

        assert hasattr(cache, "_max_size")
        assert cache._max_size > 0

    def test_shared_cache_evicts_on_overflow(self):
        """Cache should evict old entries when full."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache(max_size=10)

        # Add more entries than limit
        for i in range(20):
            cache.set_language(f"/path/file_{i}", f"lang_{i}")

        # Cache should not exceed max size
        total_entries = len(cache._language_cache)
        assert total_entries <= cache._max_size

    def test_lru_eviction_removes_oldest(self):
        """LRU eviction should remove least recently used entries."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache(max_size=5)

        # Add entries
        for i in range(5):
            cache.set_language(f"/path/file_{i}", f"lang_{i}")

        # Access first entry (makes it recently used)
        cache.get_language("/path/file_0")

        # Add only 4 more entries (not 5) to keep file_0 in cache
        # After adding file_0-4, order is: 0,1,2,3,4
        # After accessing file_0, order is: 1,2,3,4,0 (0 moved to end)
        # Adding file_5 evicts 1 -> order: 2,3,4,0,5
        # Adding file_6 evicts 2 -> order: 3,4,0,5,6
        # Adding file_7 evicts 3 -> order: 4,0,5,6,7
        # Adding file_8 evicts 4 -> order: 0,5,6,7,8
        # file_0 is still present
        for i in range(5, 9):
            cache.set_language(f"/path/file_{i}", f"lang_{i}")

        # First entry should still exist (was accessed recently)
        assert cache.get_language("/path/file_0") == "lang_0"
        # file_1 should have been evicted (was oldest after file_0 access)
        assert cache.get_language("/path/file_1") is None

    def test_default_max_size_is_1000(self):
        """Default max_size should be 1000."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache()

        assert cache._max_size == 1000

    def test_custom_max_size(self):
        """Should accept custom max_size parameter."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache(max_size=50)

        assert cache._max_size == 50

    def test_get_marks_as_recently_used(self):
        """Getting an entry should mark it as recently used."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache(max_size=3)

        # Add 3 entries
        cache.set_language("/path/a", "lang_a")
        cache.set_language("/path/b", "lang_b")
        cache.set_language("/path/c", "lang_c")

        # Access 'a' to make it recently used
        cache.get_language("/path/a")

        # Add 2 more entries, should evict 'b' and 'c' but not 'a'
        cache.set_language("/path/d", "lang_d")
        cache.set_language("/path/e", "lang_e")

        # 'a' should still be present because it was accessed recently
        assert cache.get_language("/path/a") == "lang_a"
        # 'b' should have been evicted (it was oldest)
        assert cache.get_language("/path/b") is None

    def test_all_caches_respect_max_size(self):
        """All cache dictionaries should respect max_size."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache(max_size=5)

        # Fill language_meta_cache
        for i in range(10):
            cache.set_language_meta(f"/path/meta_{i}", {"data": i})

        # Fill security_cache
        for i in range(10):
            cache.set_security_validation(f"/path/sec_{i}", (True, "ok"))

        # Fill metrics_cache
        for i in range(10):
            cache.set_metrics(f"/path/metrics_{i}", {"lines": i})

        # Fill resolved_paths
        for i in range(10):
            cache.set_resolved_path(f"/path/orig_{i}", f"/resolved/{i}")

        # All caches should be at or below max_size
        assert len(cache._language_meta_cache) <= cache._max_size
        assert len(cache._security_cache) <= cache._max_size
        assert len(cache._metrics_cache) <= cache._max_size
        assert len(cache._resolved_paths) <= cache._max_size
