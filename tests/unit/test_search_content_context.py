"""Unit tests for search_content context lines support."""
import pytest
from pathlib import Path
from tree_sitter_analyzer_v2.mcp.tools.search import SearchContentTool


class TestSearchContentContext:
    """Test cases for search_content context lines support."""
    
    @pytest.fixture
    def tool(self):
        """Create SearchContentTool instance."""
        return SearchContentTool()
    
    @pytest.fixture
    def fixtures_dir(self):
        """Get fixtures directory."""
        return Path(__file__).parent.parent / "fixtures" / "search_fixtures"
    
    def test_search_with_context_before(self, tool, fixtures_dir):
        """Test search with context_before parameter."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": "def test_function",
            "context_before": 2,
        })
        
        assert result["success"]
        assert "matches" in result
        
        # Verify context lines are included
        if result["matches"]:
            match = result["matches"][0]
            assert "context_before" in match
            assert isinstance(match["context_before"], list)
            assert len(match["context_before"]) <= 2
    
    def test_search_with_context_after(self, tool, fixtures_dir):
        """Test search with context_after parameter."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": "def test_function",
            "context_after": 2,
        })
        
        assert result["success"]
        assert "matches" in result
        
        # Verify context lines are included
        if result["matches"]:
            match = result["matches"][0]
            assert "context_after" in match
            assert isinstance(match["context_after"], list)
            assert len(match["context_after"]) <= 2
    
    def test_search_with_context(self, tool, fixtures_dir):
        """Test search with context parameter (both before and after)."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": "def test_function",
            "context": 2,
        })
        
        assert result["success"]
        assert "matches" in result
        
        # Verify context lines are included
        if result["matches"]:
            match = result["matches"][0]
            assert "context_before" in match
            assert "context_after" in match
            assert isinstance(match["context_before"], list)
            assert isinstance(match["context_after"], list)
            assert len(match["context_before"]) <= 2
            assert len(match["context_after"]) <= 2
    
    def test_search_without_context(self, tool, fixtures_dir):
        """Test search without context (default behavior)."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": "def test_function",
        })
        
        assert result["success"]
        assert "matches" in result
        
        # Verify no context lines by default
        if result["matches"]:
            match = result["matches"][0]
            assert "context_before" not in match or match["context_before"] == []
            assert "context_after" not in match or match["context_after"] == []
    
    def test_context_at_file_boundaries(self, tool, fixtures_dir):
        """Test context lines at file start and end."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": "def",
            "context": 10,  # Request more context than available
        })
        
        assert result["success"]
        assert "matches" in result
        
        # Verify context doesn't exceed file boundaries
        if result["matches"]:
            for match in result["matches"]:
                if "context_before" in match:
                    # Context before should not be negative line numbers
                    assert all(isinstance(line, str) for line in match["context_before"])
                if "context_after" in match:
                    # Context after should be valid lines
                    assert all(isinstance(line, str) for line in match["context_after"])
    
    def test_context_with_limit(self, tool, fixtures_dir):
        """Test context lines with limit parameter."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": "def",
            "context": 2,
            "limit": 3,
        })
        
        assert result["success"]
        assert "matches" in result
        assert len(result["matches"]) <= 3
        
        # Verify all matches have context
        for match in result["matches"]:
            assert "context_before" in match or "context_after" in match
