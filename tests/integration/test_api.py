"""
Integration tests for Python API interface.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

This is T5.2: Python API Interface
"""

from pathlib import Path

import pytest


class TestTreeSitterAnalyzerAPI:
    """Tests for TreeSitterAnalyzerAPI class."""

    def test_api_initialization(self):
        """Test API can be initialized."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()
        assert api is not None

    def test_analyze_file_default_format(self, analyze_fixtures_dir):
        """Test analyzing file with default format (TOON for API)."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = api.analyze_file(str(sample_py))

        assert result["success"] is True
        assert result["language"] == "python"
        assert result["output_format"] == "toon"  # Default for API
        assert isinstance(result["data"], str)
        assert len(result["data"]) > 0

    def test_analyze_file_toon_format(self, analyze_fixtures_dir):
        """Test analyzing file with TOON format explicitly."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = api.analyze_file(str(sample_py), output_format="toon")

        assert result["success"] is True
        assert result["output_format"] == "toon"
        assert isinstance(result["data"], str)

    def test_analyze_file_markdown_format(self, analyze_fixtures_dir):
        """Test analyzing file with Markdown format."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = api.analyze_file(str(sample_py), output_format="markdown")

        assert result["success"] is True
        assert result["output_format"] == "markdown"
        assert "**" in result["data"] or "#" in result["data"]

    def test_analyze_file_raw(self, analyze_fixtures_dir):
        """Test analyzing file returning raw parsed data."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = api.analyze_file_raw(str(sample_py))

        # Raw result should be a dict with parsed elements
        assert isinstance(result, dict)
        assert "classes" in result or "functions" in result or "imports" in result
        assert "metadata" in result

    def test_analyze_nonexistent_file(self):
        """Test analyzing nonexistent file returns error."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        result = api.analyze_file("nonexistent.py")

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower() or "does not exist" in result["error"].lower()

    def test_analyze_unsupported_language(self, tmp_path):
        """Test analyzing unsupported language returns error."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()
        test_file = tmp_path / "test.xyz"
        test_file.write_text("unknown language")

        result = api.analyze_file(str(test_file))

        assert result["success"] is False
        assert "error" in result
        assert (
            "unsupported" in result["error"].lower() or "not supported" in result["error"].lower()
        )


class TestSearchFilesAPI:
    """Tests for search_files API method."""

    def test_search_files_by_pattern(self, search_fixtures_dir):
        """Test searching files by glob pattern."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        result = api.search_files(root_dir=str(search_fixtures_dir), pattern="*.py")

        assert result["success"] is True
        assert len(result["files"]) > 0
        assert any("sample1.py" in f for f in result["files"])
        assert result["count"] == len(result["files"])

    def test_search_files_by_type(self, search_fixtures_dir):
        """Test searching files by type."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        result = api.search_files(root_dir=str(search_fixtures_dir), file_type="py")

        assert result["success"] is True
        assert len(result["files"]) > 0
        assert any("sample1.py" in f for f in result["files"])

    def test_search_files_nonexistent_directory(self):
        """Test searching in nonexistent directory returns error."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        result = api.search_files(root_dir="/nonexistent/path", pattern="*.py")

        assert result["success"] is False
        assert "error" in result


class TestSearchContentAPI:
    """Tests for search_content API method."""

    def test_search_content_by_pattern(self, search_fixtures_dir):
        """Test searching content by pattern."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        result = api.search_content(root_dir=str(search_fixtures_dir), pattern="class")

        assert result["success"] is True
        assert len(result["matches"]) > 0
        assert result["count"] == len(result["matches"])
        # Check match structure
        first_match = result["matches"][0]
        assert "file" in first_match
        assert "line_number" in first_match
        assert "line_content" in first_match

    def test_search_content_case_insensitive(self, search_fixtures_dir):
        """Test case-insensitive content search."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        result = api.search_content(
            root_dir=str(search_fixtures_dir), pattern="CLASS", case_sensitive=False
        )

        assert result["success"] is True
        # Should find "class" even though we searched for "CLASS"

    def test_search_content_with_type_filter(self, search_fixtures_dir):
        """Test content search with file type filter."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        result = api.search_content(
            root_dir=str(search_fixtures_dir), pattern="function", file_type="py"
        )

        assert result["success"] is True


class TestAPITypeHints:
    """Tests for API type hints and documentation."""

    def test_api_has_type_hints(self):
        """Test API methods have proper type hints."""
        import inspect

        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        # Check analyze_file has annotations
        sig = inspect.signature(api.analyze_file)
        assert sig.return_annotation != inspect.Parameter.empty

        # Check analyze_file_raw has annotations
        sig = inspect.signature(api.analyze_file_raw)
        assert sig.return_annotation != inspect.Parameter.empty

        # Check search_files has annotations
        sig = inspect.signature(api.search_files)
        assert sig.return_annotation != inspect.Parameter.empty

        # Check search_content has annotations
        sig = inspect.signature(api.search_content)
        assert sig.return_annotation != inspect.Parameter.empty

    def test_api_has_docstrings(self):
        """Test API methods have docstrings."""
        from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

        api = TreeSitterAnalyzerAPI()

        assert api.analyze_file.__doc__ is not None
        assert api.analyze_file_raw.__doc__ is not None
        assert api.search_files.__doc__ is not None
        assert api.search_content.__doc__ is not None


@pytest.fixture
def search_fixtures_dir():
    """Return path to search test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "search_fixtures"


@pytest.fixture
def analyze_fixtures_dir():
    """Return path to analyze test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "analyze_fixtures"
