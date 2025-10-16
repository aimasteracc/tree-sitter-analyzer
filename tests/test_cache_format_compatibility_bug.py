"""
Test for cache format compatibility bug fix.

This test validates the fix for the bug discovered in roo_task_sep-16-2025_1-18-38-am.md
where get_compatible_result was returning wrong format cached data.
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.utils.search_cache import SearchCache


class TestCacheFormatCompatibilityBug:
    """Test cases for the cache format compatibility bug."""

    def test_total_only_should_not_return_for_detailed_request(self):
        """
        Test that cached total_only results (integers) are not returned
        when detailed results are requested.

        This reproduces the bug from roo_task_sep-16-2025_1-18-38-am.md
        """
        cache = SearchCache()

        # Simulate the bug scenario:
        # 1. total_only query caches an integer result
        total_only_key = "query:test_total_only:True"
        cache.set(total_only_key, 3)  # Cache integer result

        # 2. User requests detailed results with same query
        detailed_key = "query:test_summary_only:True"  # Different format key

        # 3. get_compatible_result should NOT return the integer for detailed request
        result = cache.get_compatible_result(detailed_key, "summary")

        # Should return None (not compatible) instead of the integer 3
        assert result is None, (
            "Should not return integer result for summary format request"
        )

    def test_format_compatibility_validation(self):
        """Test the _is_format_compatible method with various scenarios."""
        cache = SearchCache()

        # Test total_only format compatibility
        assert cache._is_format_compatible(3, "total_only") is True
        assert cache._is_format_compatible({"matches": []}, "total_only") is False

        # Test count_only format compatibility
        count_result = {"file_counts": {"file1.java": 2}, "success": True}
        assert cache._is_format_compatible(count_result, "count_only") is True
        assert cache._is_format_compatible(3, "count_only") is False

        # Test summary format compatibility
        summary_result = {"success": True, "files": [], "total_matches": 0}
        assert cache._is_format_compatible(summary_result, "summary") is True
        assert cache._is_format_compatible(3, "summary") is False

        # Test normal format compatibility
        normal_result = {"matches": [{"file": "test.java", "line": 1}]}
        assert cache._is_format_compatible(normal_result, "normal") is True
        assert cache._is_format_compatible(3, "normal") is False

    def test_correct_format_cache_hit(self):
        """Test that correctly formatted cached results are returned."""
        cache = SearchCache()

        # Cache a summary result
        summary_key = "query:test_summary_only:True"
        summary_result = {
            "success": True,
            "files": [{"file": "test.java", "match_count": 2}],
            "total_matches": 2,
        }
        cache.set(summary_key, summary_result)

        # Request summary format - should get cache hit
        result = cache.get_compatible_result(summary_key, "summary")
        assert result is not None
        assert result == summary_result

    def test_cross_format_derivation_still_works(self):
        """Test that cross-format derivation still works after the fix."""
        cache = SearchCache()

        # Mock the derivation methods
        with (
            patch.object(cache, "_derive_count_key_from_cache_key") as mock_derive_key,
            patch.object(cache, "_can_derive_file_list") as mock_can_derive,
            patch.object(cache, "_derive_file_list_result") as mock_derive_result,
        ):
            # Setup mocks
            count_key = "query:test_count_only_matches:True"
            mock_derive_key.return_value = count_key
            mock_can_derive.return_value = True

            expected_derived = {
                "success": True,
                "files": ["test.java"],
                "cache_derived": True,
            }
            mock_derive_result.return_value = expected_derived

            # Cache a count result
            count_result = {
                "file_counts": {"test.java": 2},
                "success": True,
                "count_only": True,
            }
            cache.set(count_key, count_result)

            # Request file_list format - should derive from count data
            file_list_key = "query:test_file_list:True"
            result = cache.get_compatible_result(file_list_key, "file_list")

            # Should get derived result
            assert result == expected_derived
            mock_derive_result.assert_called_once_with(count_result, "file_list")

    def test_bug_reproduction_scenario(self):
        """
        Reproduce the exact bug scenario from the roo_task document.

        User sequence:
        1. total_only: true -> returns 3
        2. Request detailed results -> should NOT return 3, should return proper format
        """
        cache = SearchCache()

        # Step 1: User makes total_only request
        total_only_key = cache.create_cache_key(
            query="insert.*TEST_PATTERN_ABC|TEST_PATTERN_ABC.*insert",
            roots=["."],
            case="insensitive",
            include_globs=["*.java"],
            total_only=True,
        )
        cache.set(total_only_key, 3)  # Cache the integer result

        # Step 2: User requests detailed results (same query, different format)
        detailed_key = cache.create_cache_key(
            query="insert.*TEST_PATTERN_ABC|TEST_PATTERN_ABC.*insert",
            roots=["."],
            case="insensitive",
            include_globs=["*.java"],
            context_before=5,
            context_after=5,
        )

        # Step 3: get_compatible_result should NOT return the integer 3
        result = cache.get_compatible_result(detailed_key, "normal")

        # The bug was: this returned 3 instead of None
        # After fix: should return None (no compatible cached result)
        assert result is None, f"Expected None, but got {result}. Bug not fixed!"

    def test_unknown_format_prevents_primitive_return(self):
        """Test that unknown formats prevent primitive data return (the main bug)."""
        cache = SearchCache()

        # Cache a primitive result (the bug scenario)
        cache.set("test_key", 42)  # Integer result

        result = cache.get_compatible_result("test_key", "unknown_format")
        assert result is None, (
            "Unknown formats should not return primitive data (prevents bug)"
        )

        # But dict results are allowed for unknown formats (backward compatibility)
        cache.set("test_key2", {"some": "data"})
        result2 = cache.get_compatible_result("test_key2", "unknown_format")
        assert result2 is not None, "Dict results should be allowed for unknown formats"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
