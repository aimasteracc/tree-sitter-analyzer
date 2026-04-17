"""
Unit tests for SearchResultFormatter.
"""
from __future__ import annotations

import pytest

from tree_sitter_analyzer.search.formatter import (
    SearchResultFormatter,
    format_search_error,
)


class TestSearchResultFormatter:
    """Test SearchResultFormatter class."""

    @pytest.fixture
    def formatter(self) -> SearchResultFormatter:
        """Get SearchResultFormatter instance."""
        return SearchResultFormatter()

    def test_init(self, formatter: SearchResultFormatter) -> None:
        """Test SearchResultFormatter initialization."""
        assert formatter is not None

    def test_format_text_empty_results(self, formatter: SearchResultFormatter) -> None:
        """Test formatting empty results as text."""
        result = formatter.format([], format_type="text")

        assert "No results found" in result

    def test_format_text_with_results(self, formatter: SearchResultFormatter) -> None:
        """Test formatting results as text."""
        results = [
            {"file": "test.py", "line": 10, "content": "def test(): pass"},
            {"file": "main.py", "line": 5, "content": "import os"},
        ]

        output = formatter.format(results, format_type="text")

        assert "Found 2 result(s)" in output
        assert "test.py" in output
        assert "main.py" in output
        assert "Line 10" in output
        assert "Line 5" in output

    def test_format_text_with_metadata(self, formatter: SearchResultFormatter) -> None:
        """Test formatting with metadata."""
        results = [{"file": "test.py", "line": 1}]
        metadata = {
            "query": "functions named test",
            "execution_time": 0.5,
            "tool_used": "ripgrep",
        }

        output = formatter.format(results, format_type="text", metadata=metadata)

        assert "Query: functions named test" in output
        assert "Tool: ripgrep" in output
        assert "Time: 0.500s" in output

    def test_format_json(self, formatter: SearchResultFormatter) -> None:
        """Test formatting results as JSON."""
        results = [
            {"file": "test.py", "line": 10, "content": "def test(): pass"},
        ]

        output = formatter.format(results, format_type="json")

        import json
        parsed = json.loads(output)

        assert parsed["count"] == 1
        assert parsed["results"][0]["file"] == "test.py"
        assert parsed["results"][0]["line"] == 10

    def test_format_json_with_metadata(self, formatter: SearchResultFormatter) -> None:
        """Test formatting with metadata as JSON."""
        results = [{"file": "test.py"}]
        metadata = {"query": "test query"}

        output = formatter.format(results, format_type="json", metadata=metadata)

        import json
        parsed = json.loads(output)

        assert "metadata" in parsed
        assert parsed["metadata"]["query"] == "test query"

    def test_format_toon(self, formatter: SearchResultFormatter) -> None:
        """Test formatting results in TOON format."""
        results = [
            {"file": "test.py", "line": 10, "content": "def test(): pass"},
        ]

        output = formatter.format(results, format_type="toon")

        assert "# Search Results" in output
        assert "Found 1 result(s)" in output
        assert "test.py:10" in output

    def test_format_toon_with_metadata(self, formatter: SearchResultFormatter) -> None:
        """Test TOON format with metadata."""
        results = [{"file": "test.py"}]
        metadata = {"query": "test query"}

        output = formatter.format(results, format_type="toon", metadata=metadata)

        assert "Query: test query" in output
        assert "# Search Results" in output

    def test_format_toon_empty_results(self, formatter: SearchResultFormatter) -> None:
        """Test TOON format with empty results."""
        output = formatter.format([], format_type="toon")

        assert "No results found" in output
        assert "# Search Results" in output


class TestFormatSearchError:
    """Test format_search_error function."""

    def test_format_error_text(self) -> None:
        """Test formatting error as text."""
        output = format_search_error("Test error", format_type="text")

        assert "Error: Test error" in output

    def test_format_error_json(self) -> None:
        """Test formatting error as JSON."""
        output = format_search_error("Test error", format_type="json")

        import json
        parsed = json.loads(output)

        assert parsed["error"] == "Test error"
        assert parsed["results"] == []

    def test_format_error_toon(self) -> None:
        """Test formatting error in TOON format."""
        output = format_search_error("Test error", format_type="toon")

        assert "# Error" in output
        assert "Test error" in output
