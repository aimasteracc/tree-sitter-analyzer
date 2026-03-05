"""Tests for SharedCache singleton thread safety."""
import threading


class TestSharedCacheThreadSafety:
    """Test SharedCache singleton thread safety."""

    def test_shared_cache_singleton_thread_safety(self):
        """Multiple threads should get same SharedCache instance."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        instances = []
        errors = []

        def get_instance():
            try:
                instance = SharedCache()
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        # Reset singleton
        SharedCache._instance = None

        # Create 10 threads
        threads = [threading.Thread(target=get_instance) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(instances) == 10

        # All should be same instance
        first = instances[0]
        for inst in instances:
            assert inst is first, "Not all SharedCache instances are identical"

    def test_shared_cache_concurrent_access(self):
        """Concurrent cache operations should not cause issues."""
        from tree_sitter_analyzer.mcp.utils.shared_cache import SharedCache

        SharedCache._instance = None
        cache = SharedCache()

        errors = []

        def cache_operations(thread_id: int):
            try:
                for i in range(100):
                    key = f"test_key_{thread_id}_{i}"
                    cache.set_language(key, f"lang_{thread_id}")
                    result = cache.get_language(key)
                    assert result == f"lang_{thread_id}"
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=cache_operations, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent access errors: {errors}"
