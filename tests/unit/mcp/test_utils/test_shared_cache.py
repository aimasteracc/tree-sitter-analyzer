#!/usr/bin/env python3
"""
Unit tests for SharedCache module.

Tests the singleton SharedCache class which provides
shared caching across MCP tool instances.
"""

import pytest

from tree_sitter_analyzer.mcp.utils.shared_cache import (
    SharedCache,
    get_shared_cache,
)


@pytest.fixture(autouse=True)
def clear_shared_cache():
    """Fixture to clear shared cache before each test."""
    yield
    # Clear cache after each test to ensure isolation
    cache = get_shared_cache()
    cache.clear()


class TestSharedCacheSingleton:
    """Tests for SharedCache singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Test that singleton returns the same instance."""
        cache1 = SharedCache()
        cache2 = SharedCache()
        assert cache1 is cache2

    def test_get_shared_cache_returns_instance(self):
        """Test that get_shared_cache returns SharedCache instance."""
        cache = get_shared_cache()
        assert isinstance(cache, SharedCache)

    def test_get_shared_cache_singleton(self):
        """Test that get_shared_cache returns singleton."""
        cache1 = get_shared_cache()
        cache2 = get_shared_cache()
        assert cache1 is cache2

    def test_multiple_instantiations_same_instance(self):
        """Test that multiple instantiations return same instance."""
        instances = [SharedCache() for _ in range(5)]
        # All instances should be the same object
        for instance in instances[1:]:
            assert instance is instances[0]

    def test_initialization_called_once(self):
        """Test that initialization is called only once."""
        cache1 = SharedCache()
        cache1.set_language("file.py", "python")

        cache2 = SharedCache()
        # Cache should retain data from first instantiation
        assert cache2.get_language("file.py") == "python"


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_make_key_with_project_root(self):
        """Test key generation with project root."""
        cache = SharedCache()
        key = cache._make_key("test_kind", "file.py", "/project/root")
        assert "/project/root" in key
        assert "test_kind" in key
        assert "file.py" in key

    def test_make_key_without_project_root(self):
        """Test key generation without project root."""
        cache = SharedCache()
        key = cache._make_key("test_kind", "file.py", None)
        assert "test_kind" in key
        assert "file.py" in key
        # Should start with empty project root separator
        assert key.startswith("::")

    def test_make_key_consistent(self):
        """Test that same parameters produce same key."""
        cache = SharedCache()
        key1 = cache._make_key("language", "file.py", "/root")
        key2 = cache._make_key("language", "file.py", "/root")
        assert key1 == key2

    def test_make_key_differentiates_kinds(self):
        """Test that different cache kinds produce different keys."""
        cache = SharedCache()
        key1 = cache._make_key("language", "file.py", "/root")
        key2 = cache._make_key("security", "file.py", "/root")
        assert key1 != key2

    def test_make_key_differentiates_paths(self):
        """Test that different paths produce different keys."""
        cache = SharedCache()
        key1 = cache._make_key("language", "file1.py", "/root")
        key2 = cache._make_key("language", "file2.py", "/root")
        assert key1 != key2


class TestLanguageCache:
    """Tests for language detection cache."""

    def test_set_and_get_language(self):
        """Test setting and getting language."""
        cache = SharedCache()
        cache.set_language("test.py", "python")
        result = cache.get_language("test.py")
        assert result == "python"

    def test_get_language_not_set(self):
        """Test getting language that was not set."""
        cache = SharedCache()
        result = cache.get_language("test.py")
        assert result is None

    def test_set_language_overwrites(self):
        """Test that set_language overwrites existing value."""
        cache = SharedCache()
        cache.set_language("test.py", "python")
        cache.set_language("test.py", "javascript")
        result = cache.get_language("test.py")
        assert result == "javascript"

    def test_language_cache_with_project_root(self):
        """Test language cache with project root."""
        cache = SharedCache()
        cache.set_language("test.py", "python", "/project/root")
        result = cache.get_language("test.py", "/project/root")
        assert result == "python"

    def test_language_cache_different_roots(self):
        """Test that different project roots create separate caches."""
        cache = SharedCache()
        cache.set_language("test.py", "python", "/root1")
        cache.set_language("test.py", "javascript", "/root2")

        result1 = cache.get_language("test.py", "/root1")
        result2 = cache.get_language("test.py", "/root2")

        assert result1 == "python"
        assert result2 == "javascript"


class TestLanguageMetaCache:
    """Tests for language metadata cache."""

    def test_set_and_get_language_meta(self):
        """Test setting and getting language metadata."""
        cache = SharedCache()
        meta = {"version": "3.10", "extensions": [".py"]}
        cache.set_language_meta("/path/to/file.py", meta)
        result = cache.get_language_meta("/path/to/file.py")
        assert result == meta

    def test_get_language_meta_not_set(self):
        """Test getting metadata that was not set."""
        cache = SharedCache()
        result = cache.get_language_meta("/path/to/file.py")
        assert result is None

    def test_set_language_meta_overwrites(self):
        """Test that set_language_meta overwrites existing value."""
        cache = SharedCache()
        meta1 = {"version": "3.10"}
        meta2 = {"version": "3.11", "extensions": [".py"]}

        cache.set_language_meta("/path/to/file.py", meta1)
        cache.set_language_meta("/path/to/file.py", meta2)

        result = cache.get_language_meta("/path/to/file.py")
        assert result == meta2

    def test_language_meta_cache_with_project_root(self):
        """Test language metadata cache with project root."""
        cache = SharedCache()
        meta = {"version": "3.10"}
        cache.set_language_meta("/path/to/file.py", meta, "/project/root")
        result = cache.get_language_meta("/path/to/file.py", "/project/root")
        assert result == meta


class TestSecurityCache:
    """Tests for security validation cache."""

    def test_set_and_get_security(self):
        """Test setting and getting security validation."""
        cache = SharedCache()
        result = (True, "Validation passed")
        cache.set_security_validation("test.py", result)
        retrieved = cache.get_security_validation("test.py")
        assert retrieved == result

    def test_get_security_not_set(self):
        """Test getting security that was not set."""
        cache = SharedCache()
        result = cache.get_security_validation("test.py")
        assert result is None

    def test_set_security_overwrites(self):
        """Test that set_security overwrites existing value."""
        cache = SharedCache()
        result1 = (True, "First validation")
        result2 = (False, "Second validation")

        cache.set_security_validation("test.py", result1)
        cache.set_security_validation("test.py", result2)

        retrieved = cache.get_security_validation("test.py")
        assert retrieved == result2

    def test_security_cache_with_project_root(self):
        """Test security cache with project root."""
        cache = SharedCache()
        result = (True, "Valid")
        cache.set_security_validation("test.py", result, "/project/root")
        retrieved = cache.get_security_validation("test.py", "/project/root")
        assert retrieved == result


class TestMetricsCache:
    """Tests for metrics cache."""

    def test_set_and_get_metrics(self):
        """Test setting and getting metrics."""
        cache = SharedCache()
        metrics = {"lines": 100, "functions": 10}
        cache.set_metrics("test.py", metrics)
        result = cache.get_metrics("test.py")
        assert result == metrics

    def test_get_metrics_not_set(self):
        """Test getting metrics that was not set."""
        cache = SharedCache()
        result = cache.get_metrics("test.py")
        assert result is None

    def test_set_metrics_overwrites(self):
        """Test that set_metrics overwrites existing value."""
        cache = SharedCache()
        metrics1 = {"lines": 100}
        metrics2 = {"lines": 200, "functions": 20}

        cache.set_metrics("test.py", metrics1)
        cache.set_metrics("test.py", metrics2)

        result = cache.get_metrics("test.py")
        assert result == metrics2

    def test_metrics_cache_with_project_root(self):
        """Test metrics cache with project root."""
        cache = SharedCache()
        metrics = {"complexity": 50}
        cache.set_metrics("test.py", metrics, "/project/root")
        result = cache.get_metrics("test.py", "/project/root")
        assert result == metrics


class TestResolvedPathCache:
    """Tests for resolved path cache."""

    def test_set_and_get_resolved_path(self):
        """Test setting and getting resolved path."""
        cache = SharedCache()
        cache.set_resolved_path("file.py", "/resolved/path/to/file.py")
        result = cache.get_resolved_path("file.py")
        assert result == "/resolved/path/to/file.py"

    def test_get_resolved_path_not_set(self):
        """Test getting resolved path that was not set."""
        cache = SharedCache()
        result = cache.get_resolved_path("file.py")
        assert result is None

    def test_set_resolved_path_overwrites(self):
        """Test that set_resolved_path overwrites existing value."""
        cache = SharedCache()
        path1 = "/resolved/path1"
        path2 = "/resolved/path2"

        cache.set_resolved_path("file.py", path1)
        cache.set_resolved_path("file.py", path2)

        result = cache.get_resolved_path("file.py")
        assert result == path2

    def test_resolved_path_cache_with_project_root(self):
        """Test resolved path cache with project root."""
        cache = SharedCache()
        resolved_path = "/absolute/path/to/file.py"
        cache.set_resolved_path("file.py", resolved_path, "/project/root")
        result = cache.get_resolved_path("file.py", "/project/root")
        assert result == resolved_path


class TestCacheClear:
    """Tests for cache clearing."""

    def test_clear_all_caches(self):
        """Test that clear removes all cached data."""
        cache = SharedCache()

        # Set values in all caches
        cache.set_language("file.py", "python")
        cache.set_language_meta("/path/file.py", {"version": "3.10"})
        cache.set_security_validation("file.py", (True, "valid"))
        cache.set_metrics("file.py", {"lines": 100})
        cache.set_resolved_path("file.py", "/resolved/path")

        # Verify values are set
        assert cache.get_language("file.py") == "python"
        assert cache.get_language_meta("/path/file.py") is not None
        assert cache.get_security_validation("file.py") is not None
        assert cache.get_metrics("file.py") is not None
        assert cache.get_resolved_path("file.py") is not None

        # Clear all caches
        cache.clear()

        # Verify all caches are empty
        assert cache.get_language("file.py") is None
        assert cache.get_language_meta("/path/file.py") is None
        assert cache.get_security_validation("file.py") is None
        assert cache.get_metrics("file.py") is None
        assert cache.get_resolved_path("file.py") is None

    def test_clear_preserves_singleton(self):
        """Test that clear preserves singleton instance."""
        cache1 = SharedCache()
        cache1.set_language("file.py", "python")
        cache1.clear()

        cache2 = SharedCache()
        # Should still be the same instance
        assert cache1 is cache2
        # But caches should be cleared
        assert cache2.get_language("file.py") is None


class TestCacheIsolation:
    """Tests for cache isolation between different cache types."""

    def test_caches_are_independent(self):
        """Test that different cache types don't interfere."""
        cache = SharedCache()

        cache.set_language("file.py", "python")
        cache.set_language_meta("/path/file.py", {"version": "3.10"})
        cache.set_security_validation("file.py", (True, "valid"))
        cache.set_metrics("file.py", {"lines": 100})
        cache.set_resolved_path("file.py", "/resolved/path")

        # Each cache should return its own value
        assert cache.get_language("file.py") == "python"
        assert cache.get_language_meta("/path/file.py") == {"version": "3.10"}
        assert cache.get_security_validation("file.py") == (True, "valid")
        assert cache.get_metrics("file.py") == {"lines": 100}
        assert cache.get_resolved_path("file.py") == "/resolved/path"

    def test_same_key_different_cache_types(self):
        """Test that same key in different cache types works correctly."""
        cache = SharedCache()

        cache.set_language("file.py", "python")
        cache.set_metrics("file.py", {"lines": 100})

        # Same key should work in different caches
        assert cache.get_language("file.py") == "python"
        assert cache.get_metrics("file.py") == {"lines": 100}


class TestCacheWithSpecialCharacters:
    """Tests for cache with special characters in keys."""

    def test_cache_key_with_spaces(self):
        """Test cache with spaces in file path."""
        cache = SharedCache()
        cache.set_language("file with spaces.py", "python")
        result = cache.get_language("file with spaces.py")
        assert result == "python"

    def test_cache_key_with_special_chars(self):
        """Test cache with special characters in file path."""
        cache = SharedCache()
        special_path = "file-with_special.chars@#$.py"
        cache.set_language(special_path, "python")
        result = cache.get_language(special_path)
        assert result == "python"

    def test_cache_key_with_unicode(self):
        """Test cache with unicode characters."""
        cache = SharedCache()
        unicode_path = "文件.py"
        cache.set_language(unicode_path, "python")
        result = cache.get_language(unicode_path)
        assert result == "python"


class TestCacheEdgeCases:
    """Tests for edge cases."""

    def test_empty_string_key(self):
        """Test cache with empty string key."""
        cache = SharedCache()
        cache.set_language("", "python")
        result = cache.get_language("")
        assert result == "python"

    def test_none_value(self):
        """Test cache with None value."""
        cache = SharedCache()
        cache.set_language("file.py", None)
        result = cache.get_language("file.py")
        assert result is None

    def test_complex_dict_value(self):
        """Test cache with complex nested dict value."""
        cache = SharedCache()
        complex_meta = {
            "version": "3.10",
            "extensions": [".py", ".pyw"],
            "features": {"async": True, "type_hints": True},
            "stats": {"lines": 1000, "functions": 50},
        }
        cache.set_language_meta("/path/file.py", complex_meta)
        result = cache.get_language_meta("/path/file.py")
        assert result == complex_meta

    def test_very_long_key(self):
        """Test cache with very long key."""
        cache = SharedCache()
        long_key = "x" * 10000
        cache.set_language(long_key, "python")
        result = cache.get_language(long_key)
        assert result == "python"

    def test_very_long_value(self):
        """Test cache with very long value."""
        cache = SharedCache()
        long_value = "y" * 10000
        cache.set_language("file.py", long_value)
        result = cache.get_language("file.py")
        assert result == long_value


class TestCachePersistence:
    """Tests for cache persistence across operations."""

    def test_cache_persists_across_operations(self):
        """Test that cache persists across multiple operations."""
        cache = SharedCache()

        cache.set_language("file1.py", "python")
        cache.set_language("file2.py", "javascript")
        cache.set_metrics("file1.py", {"lines": 100})

        # All values should persist
        assert cache.get_language("file1.py") == "python"
        assert cache.get_language("file2.py") == "javascript"
        assert cache.get_metrics("file1.py") == {"lines": 100}

    def test_multiple_sets_same_key(self):
        """Test that multiple sets to same key work correctly."""
        cache = SharedCache()

        for i in range(10):
            cache.set_language("file.py", f"python_{i}")

        # Should get last set value
        result = cache.get_language("file.py")
        assert result == "python_9"


class TestCacheThreadSafety:
    """Tests for thread-safe cache operations."""

    def test_concurrent_sets_same_key(self):
        """Test concurrent sets to same key."""
        import threading

        cache = SharedCache()
        threads = []

        def set_value(value):
            cache.set_language("file.py", value)

        for i in range(50):
            t = threading.Thread(target=set_value, args=(f"value_{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have one of the values
        result = cache.get_language("file.py")
        assert result is not None
        assert result.startswith("value_")

    def test_concurrent_different_keys(self):
        """Test concurrent sets to different keys."""
        import threading

        cache = SharedCache()
        threads = []

        for i in range(50):
            t = threading.Thread(
                target=cache.set_language, args=(f"file_{i}.py", f"python_{i}")
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All values should be set
        for i in range(50):
            result = cache.get_language(f"file_{i}.py")
            assert result == f"python_{i}"
