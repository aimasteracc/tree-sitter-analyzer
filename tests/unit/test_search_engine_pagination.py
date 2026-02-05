"""
Test search engine pagination features (limit/offset).

Following TDD: Write tests FIRST to define the contract.
This tests the new limit/offset parameters for find_files and search_content.
"""

from pathlib import Path

import pytest


class TestFindFilesPagination:
    """Test find_files with limit/offset parameters."""

    def test_find_files_with_limit(self) -> None:
        """Test finding files with limit parameter."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Find all Python files with limit=1
        results = search.find_files(root_dir=str(fixtures_dir), pattern="*.py", limit=1)

        assert isinstance(results, list)
        assert len(results) == 1

    def test_find_files_with_limit_larger_than_results(self) -> None:
        """Test that limit larger than results returns all results."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Find all Python files with large limit
        results = search.find_files(root_dir=str(fixtures_dir), pattern="*.py", limit=1000)

        # Should return all results (not padded to 1000)
        assert len(results) > 0
        assert len(results) < 1000

    def test_find_files_with_offset(self) -> None:
        """Test finding files with offset parameter."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Get all results first
        all_results = search.find_files(root_dir=str(fixtures_dir), pattern="*.py")

        # Get results with offset=1
        offset_results = search.find_files(root_dir=str(fixtures_dir), pattern="*.py", offset=1)

        # Should skip first result
        assert len(offset_results) == len(all_results) - 1
        if len(all_results) > 1:
            assert offset_results[0] == all_results[1]

    def test_find_files_with_limit_and_offset(self) -> None:
        """Test finding files with both limit and offset."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Get all results first
        all_results = search.find_files(root_dir=str(fixtures_dir), pattern="*")

        # Get page 2 (skip 2, take 2)
        page_results = search.find_files(
            root_dir=str(fixtures_dir), pattern="*", offset=2, limit=2
        )

        # Should return 2 results starting from index 2
        assert len(page_results) <= 2
        if len(all_results) > 2:
            assert page_results[0] == all_results[2]

    def test_find_files_offset_beyond_results(self) -> None:
        """Test that offset beyond results returns empty list."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Get results with huge offset
        results = search.find_files(root_dir=str(fixtures_dir), pattern="*.py", offset=1000)

        assert results == []

    def test_find_files_limit_zero(self) -> None:
        """Test that limit=0 returns empty list."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        results = search.find_files(root_dir=str(fixtures_dir), pattern="*.py", limit=0)

        assert results == []

    def test_find_files_negative_limit_raises_error(self) -> None:
        """Test that negative limit raises ValueError."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(ValueError, match="limit must be non-negative"):
            search.find_files(root_dir=str(fixtures_dir), pattern="*.py", limit=-1)

    def test_find_files_negative_offset_raises_error(self) -> None:
        """Test that negative offset raises ValueError."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(ValueError, match="offset must be non-negative"):
            search.find_files(root_dir=str(fixtures_dir), pattern="*.py", offset=-1)


class TestSearchContentPagination:
    """Test search_content with limit/offset parameters."""

    def test_search_content_with_limit(self) -> None:
        """Test searching content with limit parameter."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Search for "def" with limit=1
        results = search.search_content(
            root_dir=str(fixtures_dir), pattern="def", limit=1
        )

        assert isinstance(results, list)
        assert len(results) == 1

    def test_search_content_with_offset(self) -> None:
        """Test searching content with offset parameter."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Get all results first
        all_results = search.search_content(root_dir=str(fixtures_dir), pattern="def")

        # Get results with offset=1
        offset_results = search.search_content(
            root_dir=str(fixtures_dir), pattern="def", offset=1
        )

        # Should skip first result
        if len(all_results) > 1:
            assert len(offset_results) == len(all_results) - 1
            # Check that first result is skipped (not checking exact match due to order)
            assert offset_results[0] != all_results[0]

    def test_search_content_with_limit_and_offset(self) -> None:
        """Test searching content with both limit and offset."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Get page 2 (skip 1, take 2)
        results = search.search_content(
            root_dir=str(fixtures_dir), pattern="def", offset=1, limit=2
        )

        assert len(results) <= 2

    def test_search_content_limit_zero(self) -> None:
        """Test that limit=0 returns empty list."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        results = search.search_content(
            root_dir=str(fixtures_dir), pattern="def", limit=0
        )

        assert results == []

    def test_search_content_negative_limit_raises_error(self) -> None:
        """Test that negative limit raises ValueError."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(ValueError, match="limit must be non-negative"):
            search.search_content(root_dir=str(fixtures_dir), pattern="def", limit=-1)

    def test_search_content_negative_offset_raises_error(self) -> None:
        """Test that negative offset raises ValueError."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(ValueError, match="offset must be non-negative"):
            search.search_content(root_dir=str(fixtures_dir), pattern="def", offset=-1)
