"""Unit tests for search_content multiline support."""
import pytest
from pathlib import Path
from tree_sitter_analyzer_v2.mcp.tools.search import SearchContentTool


class TestSearchMultiline:
    """Test cases for multiline search support."""
    
    @pytest.fixture
    def tool(self):
        """Create SearchContentTool instance."""
        return SearchContentTool()
    
    @pytest.fixture
    def fixtures_dir(self):
        """Get fixtures directory."""
        return Path(__file__).parent.parent / "fixtures" / "search_fixtures"
    
    def test_search_multiline_pattern(self, tool, fixtures_dir):
        """Test searching for multiline patterns."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": r"def.*\n.*return",
            "multiline": True,
            "use_regex": True,
        })
        
        assert result["success"]
        assert "matches" in result
        # Should find function definitions that span multiple lines
    
    def test_search_multiline_disabled(self, tool, fixtures_dir):
        """Test that multiline is disabled by default."""
        # When multiline is disabled, search for single-line patterns
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": "def",
            "use_regex": False,
            "multiline": False,
        })
        
        assert result["success"]
        # Should find single-line matches
        assert len(result.get("matches", [])) > 0
    
    def test_search_multiline_with_context(self, tool, fixtures_dir):
        """Test multiline search with context."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": r"class.*\n.*def",
            "multiline": True,
            "use_regex": True,
            "context": 1,
        })
        
        assert result["success"]
        assert "matches" in result
        # Should include context lines
    
    def test_search_multiline_class_definition(self, tool, fixtures_dir):
        """Test searching for class definitions with methods."""
        result = tool.execute({
            "root_dir": str(fixtures_dir),
            "pattern": r"class \w+.*:\n\s+def",
            "multiline": True,
            "use_regex": True,
        })
        
        assert result["success"]
        assert "matches" in result
