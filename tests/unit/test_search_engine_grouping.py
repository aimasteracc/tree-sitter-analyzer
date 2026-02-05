"""
Test search engine grouping features (group_by_directory).

Following TDD: Write tests FIRST to define the contract.
This tests the new group_by_directory parameter for find_files.
"""

from pathlib import Path

import pytest


class TestFindFilesGrouping:
    """Test find_files with group_by_directory parameter."""

    def test_find_files_group_by_directory(self) -> None:
        """Test grouping files by directory."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Find all Python files grouped by directory
        result = search.find_files(
            root_dir=str(fixtures_dir), pattern="*.py", group_by_directory=True
        )

        assert isinstance(result, dict)
        assert "by_directory" in result
        assert "summary" in result
        assert isinstance(result["by_directory"], dict)
        assert isinstance(result["summary"], dict)

    def test_find_files_group_by_directory_summary(self) -> None:
        """Test that summary contains expected fields."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = search.find_files(
            root_dir=str(fixtures_dir), pattern="*", group_by_directory=True
        )

        assert "total_files" in result["summary"]
        assert "directories" in result["summary"]
        assert result["summary"]["total_files"] > 0
        assert result["summary"]["directories"] > 0

    def test_find_files_group_by_directory_structure(self) -> None:
        """Test that by_directory has correct structure."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = search.find_files(
            root_dir=str(fixtures_dir), pattern="*.py", group_by_directory=True
        )

        # Each directory should map to a list of files
        for dir_path, files in result["by_directory"].items():
            assert isinstance(dir_path, str)
            assert isinstance(files, list)
            assert all(isinstance(f, str) for f in files)

    def test_find_files_group_by_directory_with_limit(self) -> None:
        """Test grouping with limit parameter."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = search.find_files(
            root_dir=str(fixtures_dir), pattern="*", group_by_directory=True, limit=5
        )

        # Should respect limit
        total_files = sum(len(files) for files in result["by_directory"].values())
        assert total_files <= 5
        assert result["summary"]["total_files"] <= 5

    def test_find_files_group_by_directory_false_returns_list(self) -> None:
        """Test that group_by_directory=False returns list (default behavior)."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = search.find_files(
            root_dir=str(fixtures_dir), pattern="*.py", group_by_directory=False
        )

        # Should return list, not dict
        assert isinstance(result, list)

    def test_find_files_default_returns_list(self) -> None:
        """Test that default behavior returns list (not grouped)."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = search.find_files(root_dir=str(fixtures_dir), pattern="*.py")

        # Should return list by default
        assert isinstance(result, list)

    def test_find_files_group_by_directory_relative_paths(self) -> None:
        """Test that grouped directories use relative paths."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = search.find_files(
            root_dir=str(fixtures_dir), pattern="*", group_by_directory=True
        )

        # Directory keys should be relative to root_dir
        for dir_path in result["by_directory"].keys():
            # Should not be absolute paths
            assert not Path(dir_path).is_absolute() or dir_path == "."

    def test_find_files_group_by_directory_empty_results(self) -> None:
        """Test grouping with no results."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = search.find_files(
            root_dir=str(fixtures_dir), pattern="*.nonexistent", group_by_directory=True
        )

        assert result["by_directory"] == {}
        assert result["summary"]["total_files"] == 0
        assert result["summary"]["directories"] == 0
