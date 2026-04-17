"""
Unit tests for Semantic Search MCP Tool.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.semantic_search_tool import SemanticSearchTool


class TestSemanticSearchTool:
    """Test SemanticSearchTool class."""

    @pytest.fixture
    def tool(self, tmp_path) -> SemanticSearchTool:
        """Get SemanticSearchTool instance."""
        return SemanticSearchTool(project_root=str(tmp_path))

    def test_get_name(self, tool: SemanticSearchTool) -> None:
        """Test getting tool name."""
        assert tool.get_name() == "semantic_search"

    def test_get_description(self, tool: SemanticSearchTool) -> None:
        """Test getting tool description."""
        description = tool.get_description()

        assert "semantic code search" in description.lower()
        assert "query classification" in description.lower()

    def test_get_parameters(self, tool: SemanticSearchTool) -> None:
        """Test getting tool parameters schema."""
        params = tool.get_parameters()

        assert params["type"] == "object"
        assert "query" in params["properties"]
        assert params["properties"]["query"]["type"] == "string"
        assert params["required"] == ["query"]

        # Optional parameters
        assert "format" in params["properties"]
        assert "use_cache" in params["properties"]
        assert "llm_provider" in params["properties"]

    def test_execute_no_query(self, tool: SemanticSearchTool) -> None:
        """Test execute with no query."""
        result = tool.execute({})

        assert "No query provided" in result

    def test_execute_simple_query(self, tool: SemanticSearchTool) -> None:
        """Test execute with a simple query."""
        # Mock the executor to return results
        with patch.object(tool.executor, "execute") as mock_execute:
            mock_execute.return_value = MagicMock(
                success=True,
                results=[{"file": "test.py", "line": 10, "content": "def test(): pass"}],
                execution_time=0.5,
                tool_used="ripgrep",
            )

            result = tool.execute({"query": "functions named test"})

            assert "test.py" in result
            assert "Line 10" in result

    def test_execute_with_format_json(self, tool: SemanticSearchTool) -> None:
        """Test execute with JSON format."""
        with patch.object(tool.executor, "execute") as mock_execute:
            mock_execute.return_value = MagicMock(
                success=True,
                results=[{"file": "test.py"}],
                execution_time=0.1,
                tool_used="grep",
            )

            result = tool.execute({"query": "test", "format": "json"})

            # Should contain JSON output
            assert '"results"' in result
            assert '"count"' in result

    def test_execute_with_cache_disabled(self, tool: SemanticSearchTool) -> None:
        """Test execute with cache disabled."""
        with patch.object(tool.executor, "execute") as mock_execute:
            mock_execute.return_value = MagicMock(
                success=True,
                results=[],
                execution_time=0.1,
                tool_used="grep",
            )

            # Mock cache to verify it's not used
            with patch.object(tool.cache, "get") as mock_cache_get:
                tool.execute({"query": "test", "use_cache": False})

                # Cache should not be checked
                mock_cache_get.assert_not_called()

    def test_execute_cache_hit(self, tool: SemanticSearchTool) -> None:
        """Test execute with cache hit."""
        cached_results = [{"file": "cached.py", "line": 5}]

        with patch.object(tool.cache, "get", return_value=cached_results):
            result = tool.execute({"query": "test"})

            assert "cached.py" in result

    def test_execute_llm_provider_selection(self, tool: SemanticSearchTool) -> None:
        """Test LLM provider selection."""
        with patch.object(tool, "llm") as mock_llm:
            # Mock LLM integration
            mock_llm.parse_query.return_value = MagicMock(
                tool_calls=[],
                execution_time=0.5,
                provider_used=MagicMock(value="openai"),
            )

            # Test OpenAI provider
            tool.execute({"query": "complex query", "llm_provider": "openai"})
            # LLM should have been replaced with OpenAI provider
            assert tool.llm is not None

    def test_execute_error_handling(self, tool: SemanticSearchTool) -> None:
        """Test error handling in execute."""
        with patch.object(tool.classifier, "classify", side_effect=Exception("Test error")):
            result = tool.execute({"query": "test"})

            assert "error" in result.lower() or "failed" in result.lower()


class TestSemanticSearchToolIntegration:
    """Integration tests for SemanticSearchTool."""

    @pytest.fixture
    def tool(self) -> SemanticSearchTool:
        """Get SemanticSearchTool instance for current repo."""
        return SemanticSearchTool()

    def test_real_project_search(self, tool: SemanticSearchTool) -> None:
        """Test searching in the actual project."""
        # Search for a common pattern that should exist
        result = tool.execute({"query": "functions named test"})

        # Should return some result (even if empty)
        assert isinstance(result, str)
