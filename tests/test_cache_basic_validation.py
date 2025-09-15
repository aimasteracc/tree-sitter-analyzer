#!/usr/bin/env python3
"""
Basic cache validation tests for Phase 2 cache implementation.

This module tests the basic caching functionality without performance-sensitive tests
that might be unstable in CI environments.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool
from tree_sitter_analyzer.mcp.utils.search_cache import clear_cache, configure_cache


class TestCacheBasicValidation:
    """Test basic cache functionality without performance requirements"""

    @pytest.fixture(scope="class")
    def test_directory(self):
        """Path to the test directory - using project examples directory"""
        project_root = Path(__file__).parent.parent
        examples_dir = project_root / "examples"
        if examples_dir.exists() and any(examples_dir.iterdir()):
            return str(examples_dir)
        else:
            # Fallback to current directory if examples doesn't exist or is empty
            return str(project_root)

    @pytest.fixture
    def tool_with_cache(self, test_directory):
        """Create a SearchContentTool with caching enabled"""
        clear_cache()  # Start with clean cache
        configure_cache(max_size=100, ttl_seconds=300)  # 5 minutes TTL for testing
        return SearchContentTool(project_root=test_directory, enable_cache=True)

    @pytest.fixture
    def tool_without_cache(self, test_directory):
        """Create a SearchContentTool with caching disabled"""
        return SearchContentTool(project_root=test_directory, enable_cache=False)

    @pytest.mark.asyncio
    async def test_cache_basic_functionality(self, tool_with_cache, test_directory):
        """Test basic cache functionality without performance assertions"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        # Test search arguments
        search_args = {
            "query": "class",
            "roots": [test_directory],
            "case": "smart",
            "max_count": 10,  # Limit results for faster execution
        }

        # First search - cache miss
        result1 = await tool_with_cache.execute(search_args)

        # Verify first search was successful
        assert result1.get("success", True)
        assert not result1.get("cache_hit", False)

        # Second search - cache hit
        result2 = await tool_with_cache.execute(search_args)

        # Verify second search was a cache hit
        assert result2.get("success", True)
        assert result2.get("cache_hit", False) is True

        # Verify results are identical (excluding cache_hit flag and elapsed_ms)
        result1_clean = {
            k: v for k, v in result1.items() if k not in ["cache_hit", "elapsed_ms"]
        }
        result2_clean = {
            k: v for k, v in result2.items() if k not in ["cache_hit", "elapsed_ms"]
        }
        assert result1_clean == result2_clean

    @pytest.mark.asyncio
    async def test_cache_statistics_tracking(self, tool_with_cache, test_directory):
        """Test that cache statistics are properly tracked"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        # Clear cache and get initial stats
        clear_cache()
        initial_stats = tool_with_cache.cache.get_stats()
        assert initial_stats["hits"] == 0
        assert initial_stats["misses"] == 0

        search_args = {"query": "import", "roots": [test_directory], "max_count": 5}

        # First search - should be a miss
        await tool_with_cache.execute(search_args)
        stats_after_first = tool_with_cache.cache.get_stats()
        assert stats_after_first["misses"] >= 1
        assert stats_after_first["hits"] == 0

        # Second search - should be a hit
        await tool_with_cache.execute(search_args)
        stats_after_second = tool_with_cache.cache.get_stats()
        assert stats_after_second["hits"] >= 1

    @pytest.mark.asyncio
    async def test_different_search_parameters_create_different_cache_keys(
        self, tool_with_cache, test_directory
    ):
        """Test that different search parameters create different cache entries"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        base_args = {"query": "class", "roots": [test_directory], "max_count": 5}

        # Search with different parameters
        search_variants = [
            {**base_args, "case": "smart"},
            {**base_args, "case": "insensitive"},
            {**base_args, "query": "function"},
        ]

        results = []
        for search_args in search_variants:
            result = await tool_with_cache.execute(search_args)
            assert result.get("success", True)
            results.append(result)

        # Repeat the first search - should now be a cache hit
        result = await tool_with_cache.execute(search_variants[0])
        assert result.get("cache_hit", False) is True

    @pytest.mark.asyncio
    async def test_cache_with_different_output_modes(
        self, tool_with_cache, test_directory
    ):
        """Test cache works with different output modes"""
        if not Path(test_directory).exists():
            pytest.skip(f"Test directory {test_directory} does not exist")

        base_args = {"query": "test", "roots": [test_directory], "max_count": 3}

        # Test different output modes
        modes = [
            {},  # Normal mode
            {"count_only_matches": True},  # Count only mode
            {"summary_only": True},  # Summary mode
        ]

        for mode in modes:
            search_args = {**base_args, **mode}

            # First call - cache miss
            result1 = await tool_with_cache.execute(search_args)
            assert result1.get("success", True) or isinstance(result1, int)

            # Second call - cache hit
            result2 = await tool_with_cache.execute(search_args)

            # For count_only_matches with total_only, result might be an int
            if isinstance(result2, dict):
                assert result2.get("cache_hit", False) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
