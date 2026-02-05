"""
Test find_and_grep tool returns match content (not just file list).

Following TDD: Write tests FIRST to define the contract.
This tests that find_and_grep returns matching lines, not just file paths.
"""

from pathlib import Path

import pytest


class TestFindAndGrepMatchContent:
    """Test that find_and_grep returns match content."""

    def test_find_and_grep_with_query_returns_matches(self) -> None:
        """Test that find_and_grep with query returns match content."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = tool.execute(
            {
                "roots": [str(fixtures_dir)],
                "pattern": "*.py",
                "query": "def",
            }
        )

        assert result["success"] is True
        assert "matches" in result
        assert isinstance(result["matches"], list)
        
        # Should have match content, not just file paths
        if len(result["matches"]) > 0:
            first_match = result["matches"][0]
            assert "file" in first_match
            assert "line_number" in first_match
            assert "line_content" in first_match or "line" in first_match

    def test_find_and_grep_without_query_returns_files(self) -> None:
        """Test that find_and_grep without query returns file list."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = tool.execute(
            {
                "roots": [str(fixtures_dir)],
                "pattern": "*.py",
            }
        )

        assert result["success"] is True
        assert "files" in result
        assert isinstance(result["files"], list)

    def test_find_and_grep_match_structure(self) -> None:
        """Test that matches have correct structure."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = tool.execute(
            {
                "roots": [str(fixtures_dir)],
                "pattern": "*.py",
                "query": "def",
            }
        )

        assert result["success"] is True
        
        if len(result["matches"]) > 0:
            match = result["matches"][0]
            # Should have all required fields
            assert isinstance(match["file"], str)
            assert isinstance(match["line_number"], int)
            assert isinstance(match.get("line_content") or match.get("line"), str)

    def test_find_and_grep_with_limit(self) -> None:
        """Test that find_and_grep respects limit parameter."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = tool.execute(
            {
                "roots": [str(fixtures_dir)],
                "pattern": "*.py",
                "query": "def",
                "limit": 2,
            }
        )

        assert result["success"] is True
        assert len(result["matches"]) <= 2

    def test_find_and_grep_case_insensitive(self) -> None:
        """Test case-insensitive search returns matches."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "search_fixtures"

        result = tool.execute(
            {
                "roots": [str(fixtures_dir)],
                "pattern": "*.py",
                "query": "DEF",
                "case_sensitive": False,
            }
        )

        assert result["success"] is True
        # Should find matches even with uppercase query
        assert len(result["matches"]) > 0
