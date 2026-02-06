"""
Tests for mcp/tools/refactoring_safety.py module.

TDD: Testing refactoring safety tools.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer_v2.mcp.tools.refactoring_safety import (
    CheckRefactoringSafetyTool,
    ProjectKnowledgeTool,
)


class TestCheckRefactoringSafetyTool:
    """Test CheckRefactoringSafetyTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = CheckRefactoringSafetyTool()
        assert tool.get_name() == "check_refactoring_safety"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = CheckRefactoringSafetyTool()
        desc = tool.get_description()
        assert "安全" in desc or "refactor" in desc.lower()

    def test_get_schema(self) -> None:
        """Should return correct schema."""
        tool = CheckRefactoringSafetyTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "function_name" in schema["properties"]
        assert "function_name" in schema["required"]

    def test_missing_function_name(self) -> None:
        """Should return error for missing function name."""
        tool = CheckRefactoringSafetyTool()
        result = tool.execute({})
        
        assert result["success"] is False
        assert "Missing" in result["error"]

    @patch("tree_sitter_analyzer_v2.mcp.tools.refactoring_safety.get_function_safety")
    def test_function_not_found(self, mock_get_safety) -> None:
        """Should handle function not found."""
        mock_get_safety.return_value = None
        
        tool = CheckRefactoringSafetyTool()
        result = tool.execute({"function_name": "nonexistent"})
        
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("tree_sitter_analyzer_v2.mcp.tools.refactoring_safety.get_function_safety")
    def test_successful_check(self, mock_get_safety) -> None:
        """Should return safety info on success."""
        mock_get_safety.return_value = {
            "function": "my_func",
            "file": "module.py",
            "impact_level": "low",
            "safe_to_refactor": True
        }
        
        tool = CheckRefactoringSafetyTool()
        result = tool.execute({"function_name": "my_func"})
        
        assert result["success"] is True
        assert result["function"] == "my_func"
        assert result["safe_to_refactor"] is True


class TestProjectKnowledgeTool:
    """Test ProjectKnowledgeTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = ProjectKnowledgeTool()
        assert tool.get_name() == "query_project_knowledge"

    def test_get_schema(self) -> None:
        """Should return correct schema."""
        tool = ProjectKnowledgeTool()
        schema = tool.get_schema()
        
        assert "query_type" in schema["properties"]
        assert "query_type" in schema["required"]

    def test_missing_query_type(self) -> None:
        """Should return error for missing query_type."""
        tool = ProjectKnowledgeTool()
        result = tool.execute({})
        
        assert result["success"] is False
        assert "Missing" in result["error"]

    def test_unknown_query_type(self) -> None:
        """Should return error for unknown query_type."""
        tool = ProjectKnowledgeTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = tool.execute({
                "query_type": "unknown",
                "project_root": tmpdir
            })
            
            assert result["success"] is False
            assert "Unknown" in result["error"]

    @patch("tree_sitter_analyzer_v2.mcp.tools.refactoring_safety.ProjectKnowledgeEngine")
    def test_query_snapshot(self, mock_engine_class) -> None:
        """Should query snapshot."""
        mock_engine = MagicMock()
        mock_engine.load_snapshot.return_value = "FUNC:main"
        mock_engine_class.return_value = mock_engine
        
        tool = ProjectKnowledgeTool()
        result = tool.execute({
            "query_type": "snapshot",
            "max_functions": 30
        })
        
        assert result["success"] is True
        assert result["query_type"] == "snapshot"

    @patch("tree_sitter_analyzer_v2.mcp.tools.refactoring_safety.ProjectKnowledgeEngine")
    def test_query_hotspots(self, mock_engine_class) -> None:
        """Should query hotspots."""
        mock_engine = MagicMock()
        mock_engine.get_hotspots.return_value = [{"function": "main"}]
        mock_engine_class.return_value = mock_engine
        
        tool = ProjectKnowledgeTool()
        result = tool.execute({
            "query_type": "hotspots",
            "top_n": 10
        })
        
        assert result["success"] is True
        assert result["query_type"] == "hotspots"
