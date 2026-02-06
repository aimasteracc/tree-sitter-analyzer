"""
Test search engine implementation (fd + ripgrep wrappers).

Following TDD: Write tests FIRST to define the contract.
This is T1.3: Search Engine (fd + ripgrep)
"""

from pathlib import Path

import pytest


class TestFileSearch:
    """Test file search using fd."""

    def test_search_engine_can_be_imported(self) -> None:
        """Test that SearchEngine can be imported."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        assert SearchEngine is not None

    def test_search_engine_initialization(self) -> None:
        """Test creating a search engine instance."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        assert search is not None

    def test_find_files_by_extension(self) -> None:
        """Test finding files by extension."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Find all Python files
        results = search.find_files(root_dir=str(fixtures_dir), pattern="*.py")

        assert isinstance(results, list)
        assert len(results) > 0
        assert any("sample1.py" in str(r) for r in results)

    def test_find_files_by_name(self) -> None:
        """Test finding files by name pattern."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Find files with "sample" in name
        results = search.find_files(root_dir=str(fixtures_dir), pattern="sample*")

        assert len(results) >= 2  # sample1.py, sample2.ts

    def test_find_files_with_type_filter(self) -> None:
        """Test finding files with type filter (e.g., only Python)."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Find only TypeScript files
        results = search.find_files(root_dir=str(fixtures_dir), pattern="*", file_type="ts")

        assert all(r.endswith(".ts") for r in results)

    def test_find_files_recursive(self) -> None:
        """Test that file search is recursive by default."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Find Java files (should find nested/Sample.java)
        results = search.find_files(root_dir=str(fixtures_dir), pattern="*.java")

        assert len(results) >= 1
        assert any("Sample.java" in str(r) for r in results)

    def test_find_files_returns_absolute_paths(self) -> None:
        """Test that find_files returns absolute paths."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        results = search.find_files(root_dir=str(fixtures_dir), pattern="*.py")

        assert all(Path(r).is_absolute() for r in results)

    def test_find_files_handles_nonexistent_directory(self) -> None:
        """Test that find_files handles nonexistent directory gracefully."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()

        with pytest.raises(ValueError, match="does not exist"):
            search.find_files(root_dir="/nonexistent/path/xyz", pattern="*.py")


class TestContentSearch:
    """Test content search using ripgrep."""

    def test_search_content_basic(self) -> None:
        """Test basic content search."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Search for "Calculator" in files
        results = search.search_content(root_dir=str(fixtures_dir.resolve()), pattern="Calculator")

        assert isinstance(results, list)
        assert len(results) > 0
        # Should find it in sample1.py
        assert any("sample1.py" in r["file"] for r in results)

    def test_search_content_returns_line_numbers(self) -> None:
        """Test that search results include line numbers."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        results = search.search_content(root_dir=str(fixtures_dir.resolve()), pattern="Calculator")

        assert len(results) > 0
        for result in results:
            assert "file" in result
            assert "line_number" in result
            assert "line_content" in result
            assert isinstance(result["line_number"], int)

    def test_search_content_with_file_type_filter(self) -> None:
        """Test content search with file type filter."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Search only in TypeScript files
        results = search.search_content(root_dir=str(fixtures_dir), pattern="User", file_type="ts")

        assert all(r["file"].endswith(".ts") for r in results)

    def test_search_content_case_insensitive(self) -> None:
        """Test case-insensitive content search."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Search for "hello" (should match "Hello" and "hello")
        results = search.search_content(
            root_dir=str(fixtures_dir), pattern="hello", case_sensitive=False
        )

        assert len(results) > 0

    def test_search_content_regex_pattern(self) -> None:
        """Test content search with regex pattern."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Search for function definitions (def or function keyword)
        results = search.search_content(
            root_dir=str(fixtures_dir), pattern=r"(def|function)\s+\w+", is_regex=True
        )

        assert len(results) > 0

    def test_search_content_handles_nonexistent_directory(self) -> None:
        """Test that search_content handles nonexistent directory."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()

        with pytest.raises(ValueError, match="does not exist"):
            search.search_content(root_dir="/nonexistent/path/xyz", pattern="test")


class TestBinaryDependencies:
    """Test that search engine handles missing binaries."""

    def test_search_engine_detects_fd_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that search engine raises error if fd is missing."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        # Mock fd not being found  - patch in search module
        def mock_get_fd_path() -> None:
            return None

        monkeypatch.setattr("tree_sitter_analyzer_v2.search.get_fd_path", mock_get_fd_path)

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(RuntimeError, match="fd binary not found"):
            search.find_files(root_dir=str(fixtures_dir), pattern="*.py")

    def test_search_engine_detects_ripgrep_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that search engine raises error if ripgrep is missing."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        # Mock ripgrep not being found - patch in search module
        def mock_get_ripgrep_path() -> None:
            return None

        monkeypatch.setattr(
            "tree_sitter_analyzer_v2.search.get_ripgrep_path", mock_get_ripgrep_path
        )

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(RuntimeError, match="ripgrep binary not found"):
            search.search_content(root_dir=str(fixtures_dir), pattern="test")


class TestSearchPerformance:
    """Test search engine performance."""

    def test_file_search_performance(self) -> None:
        """Test that file search completes quickly."""
        import time

        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        start = time.perf_counter()
        search.find_files(root_dir=str(fixtures_dir), pattern="*.py")
        elapsed = (time.perf_counter() - start) * 1000  # Convert to ms

        # Should complete in <1000ms for small directory (subprocess overhead on Windows)
        # Adjusted from 300ms to 1000ms due to Windows subprocess overhead (Issue #11 fix)
        assert elapsed < 1000

    def test_content_search_performance(self) -> None:
        """Test that content search completes quickly."""
        import time

        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        start = time.perf_counter()
        search.search_content(root_dir=str(fixtures_dir), pattern="class")
        elapsed = (time.perf_counter() - start) * 1000

        # Should complete in <1000ms for small directory (subprocess overhead on Windows)
        # Adjusted from 300ms to 1000ms due to Windows subprocess overhead (Issue #11 fix)
        assert elapsed < 1000


class TestEncodingSupport:
    """Test encoding support for search results (Issue #11)."""

    def test_search_content_handles_utf8_output(self) -> None:
        """Test that search_content correctly handles UTF-8 encoded ripgrep output.

        This tests Issue #11: UnicodeDecodeError when ripgrep outputs UTF-8
        but subprocess uses system default encoding (cp932 on Windows).
        """
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Search for content that might include UTF-8 characters
        # This should NOT raise UnicodeDecodeError
        try:
            results = search.search_content(
                root_dir=str(fixtures_dir), pattern="class", file_type="py"
            )
            assert isinstance(results, list)
            # Should complete without encoding errors
        except UnicodeDecodeError as e:
            pytest.fail(f"UnicodeDecodeError should not occur: {e}")

    def test_search_content_with_absolute_path(self) -> None:
        """Test that search_content works with absolute path.

        This tests Issue #10: API should work with both relative and absolute paths.
        """
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        # Use absolute path
        root_dir = Path(__file__).parent.parent.parent / "tree_sitter_analyzer_v2"

        results = search.search_content(
            root_dir=str(root_dir.resolve()), pattern="CodeGraphBuilder", file_type="py"
        )

        # Should find at least 10 matches
        assert len(results) >= 10, f"Expected >= 10 matches, got {len(results)}"

        # Verify structure
        for result in results:
            assert "file" in result
            assert "line_number" in result
            assert "line_content" in result
            assert "CodeGraphBuilder" in result["line_content"]


class TestSearchResultParsing:
    """Test parsing of search results."""

    def test_parse_fd_output(self) -> None:
        """Test parsing fd output format."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()

        # Simulate fd output (one file per line)
        fd_output = "path/to/file1.py\npath/to/file2.py\npath/to/file3.py\n"

        results = search._parse_fd_output(fd_output)

        assert len(results) == 3
        assert results[0] == "path/to/file1.py"
        assert results[1] == "path/to/file2.py"
        assert results[2] == "path/to/file3.py"

    def test_parse_fd_output_empty(self) -> None:
        """Test parsing empty fd output."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        results = search._parse_fd_output("")

        assert results == []

    def test_parse_rg_output(self) -> None:
        """Test parsing ripgrep output format."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()

        # Simulate ripgrep output (file:line:content)
        rg_output = (
            "file1.py:10:    def hello():\n"
            "file2.py:25:    class Calculator:\n"
            "file3.py:5:def main():\n"
        )

        results = search._parse_rg_output(rg_output)

        assert len(results) == 3
        assert results[0]["file"] == "file1.py"
        assert results[0]["line_number"] == 10
        assert "hello" in results[0]["line_content"]

    def test_parse_rg_output_empty(self) -> None:
        """Test parsing empty ripgrep output."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        results = search._parse_rg_output("")

        assert results == []


class TestSearchValidation:
    """Test input validation for search methods."""

    def test_find_files_negative_limit(self) -> None:
        """Test that find_files raises ValueError for negative limit."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(ValueError, match="limit must be non-negative"):
            search.find_files(root_dir=str(fixtures_dir), pattern="*.py", limit=-1)

    def test_find_files_negative_offset(self) -> None:
        """Test that find_files raises ValueError for negative offset."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(ValueError, match="offset must be non-negative"):
            search.find_files(root_dir=str(fixtures_dir), pattern="*.py", offset=-1)

    def test_search_content_negative_limit(self) -> None:
        """Test that search_content raises ValueError for negative limit."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(ValueError, match="limit must be non-negative"):
            search.search_content(root_dir=str(fixtures_dir), pattern="test", limit=-1)

    def test_search_content_negative_offset(self) -> None:
        """Test that search_content raises ValueError for negative offset."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        with pytest.raises(ValueError, match="offset must be non-negative"):
            search.search_content(root_dir=str(fixtures_dir), pattern="test", offset=-1)

    def test_find_files_with_offset(self) -> None:
        """Test find_files with offset."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Get all files first
        all_files = search.find_files(root_dir=str(fixtures_dir), pattern="*")

        # Get files with offset
        if len(all_files) > 1:
            offset_files = search.find_files(root_dir=str(fixtures_dir), pattern="*", offset=1)
            assert len(offset_files) == len(all_files) - 1

    def test_search_content_with_offset(self) -> None:
        """Test search_content with offset."""
        from tree_sitter_analyzer_v2.search import SearchEngine

        search = SearchEngine()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        # Get all matches first
        all_matches = search.search_content(root_dir=str(fixtures_dir), pattern="def")

        # Get matches with offset
        if len(all_matches) > 1:
            offset_matches = search.search_content(
                root_dir=str(fixtures_dir), pattern="def", offset=1
            )
            assert len(offset_matches) == len(all_matches) - 1
