#!/usr/bin/env python3
"""
Unit tests for Dead Code Detection MCP Tool.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.dead_code_tool import DeadCodeTool
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


class TestDeadCodeToolToolDefinition:
    """Tests for DeadCodeTool tool definition."""

    def test_tool_name(self) -> None:
        """Test that tool has correct name."""
        tool = DeadCodeTool()
        definition = tool.get_tool_definition()
        assert definition["name"] == "dead_code"

    def test_tool_description(self) -> None:
        """Test that tool has description."""
        tool = DeadCodeTool()
        definition = tool.get_tool_definition()
        assert len(definition["description"]) > 0
        assert "dead" in definition["description"].lower()
        assert "unused" in definition["description"].lower()


class TestDeadCodeToolValidation:
    """Tests for DeadCodeTool argument validation."""

    def test_requires_file_path_or_project_root(self) -> None:
        """Test that validation fails when neither path is provided."""
        tool = DeadCodeTool()
        with pytest.raises((AnalysisError, ValueError), match="At least one of"):
            tool.validate_arguments({})

    def test_accepts_file_path(self) -> None:
        """Test that validation accepts file_path."""
        tool = DeadCodeTool()
        # Should not raise
        tool.validate_arguments({"file_path": "test.py"})

    def test_accepts_project_root(self) -> None:
        """Test that validation accepts project_root."""
        tool = DeadCodeTool()
        # Should not raise
        tool.validate_arguments({"project_root": "/project"})

    def test_accepts_both_paths(self) -> None:
        """Test that validation accepts both paths."""
        tool = DeadCodeTool()
        # Should not raise
        tool.validate_arguments({"file_path": "test.py", "project_root": "/project"})

    def test_confidence_threshold_validation(self) -> None:
        """Test confidence_threshold validation."""
        tool = DeadCodeTool()

        # Valid values
        tool.validate_arguments({"project_root": "/project", "confidence_threshold": 0.5})
        tool.validate_arguments({"project_root": "/project", "confidence_threshold": 0.0})
        tool.validate_arguments({"project_root": "/project", "confidence_threshold": 1.0})

        # Invalid values
        with pytest.raises((AnalysisError, ValueError), match="confidence_threshold"):
            tool.validate_arguments({"project_root": "/project", "confidence_threshold": -0.1})
        with pytest.raises((AnalysisError, ValueError), match="confidence_threshold"):
            tool.validate_arguments({"project_root": "/project", "confidence_threshold": 1.1})
        with pytest.raises((AnalysisError, ValueError), match="confidence_threshold"):
            tool.validate_arguments({"project_root": "/project", "confidence_threshold": "invalid"})

    def test_output_format_validation(self) -> None:
        """Test output_format validation."""
        tool = DeadCodeTool()

        # Valid values
        tool.validate_arguments({"project_root": "/project", "output_format": "json"})
        tool.validate_arguments({"project_root": "/project", "output_format": "toon"})
        tool.validate_arguments({"project_root": "/project", "output_format": "summary"})

        # Invalid value
        with pytest.raises((AnalysisError, ValueError), match="output_format"):
            tool.validate_arguments({"project_root": "/project", "output_format": "invalid"})


class TestDeadCodeToolExecute:
    """Tests for DeadCodeTool execution."""

    @pytest.mark.asyncio
    async def test_execute_with_project_root(self) -> None:
        """Test execution with project_root."""
        tool = DeadCodeTool(project_root="/tmp")
        result = tool.execute({"project_root": "/tmp"})

        assert result["success"] is True
        assert "files_scanned" in result
        assert "total_issues" in result

    @pytest.mark.asyncio
    async def test_execute_json_format(self) -> None:
        """Test JSON output format."""
        tool = DeadCodeTool(project_root="/tmp")
        result = tool.execute({"project_root": "/tmp", "output_format": "json"})

        assert result["success"] is True
        assert result.get("output_format") == "json"

    @pytest.mark.asyncio
    async def test_execute_toon_format(self) -> None:
        """Test TOON output format."""
        tool = DeadCodeTool(project_root="/tmp")
        result = tool.execute({"project_root": "/tmp", "output_format": "toon"})

        assert result["success"] is True
        assert result["output_format"] == "toon"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_execute_summary_format(self) -> None:
        """Test summary output format."""
        tool = DeadCodeTool(project_root="/tmp")
        result = tool.execute({"project_root": "/tmp", "output_format": "summary"})

        assert result["success"] is True
        assert result["output_format"] == "summary"
        assert "summary" in result
        assert "Dead Code Analysis Report" in result["summary"]

    @pytest.mark.asyncio
    async def test_confidence_threshold_filter(self) -> None:
        """Test confidence threshold filtering."""
        tool = DeadCodeTool(project_root="/tmp")
        result = tool.execute({"project_root": "/tmp", "confidence_threshold": 0.9})

        assert result["success"] is True
        # Should only return issues with confidence >= 0.9


class TestDeadCodeToolOutputFormats:
    """Tests for different output formats."""

    def test_json_format_structure(self) -> None:
        """Test JSON format has correct structure."""
        tool = DeadCodeTool(project_root="/tmp")
        result = tool.execute({"project_root": "/tmp", "output_format": "json"})

        assert "files_scanned" in result
        assert "total_issues" in result
        assert "unused_functions" in result
        assert "unused_classes" in result
        assert "unused_imports" in result
        assert "issues" in result

    def test_toon_format_structure(self) -> None:
        """Test TOON format has correct structure."""
        tool = DeadCodeTool(project_root="/tmp")
        result = tool.execute({"project_root": "/tmp", "output_format": "toon"})

        assert "data" in result
        assert isinstance(result["data"], str)

    def test_summary_format_content(self) -> None:
        """Test summary format has expected content."""
        tool = DeadCodeTool(project_root="/tmp")
        result = tool.execute({"project_root": "/tmp", "output_format": "summary"})

        assert "summary" in result
        summary = result["summary"]
        assert "Files scanned:" in summary
        assert "Total issues:" in summary
        assert "Unused functions:" in summary
        assert "Unused classes:" in summary
        assert "Unused imports:" in summary


class TestDeadCodeToolIntegration:
    """Integration tests for DeadCodeTool."""

    def test_tool_can_be_instantiated(self) -> None:
        """Test that tool can be instantiated."""
        tool = DeadCodeTool()
        assert tool is not None
        assert tool.project_root is None

    def test_tool_with_project_root(self) -> None:
        """Test tool with project_root set."""
        tool = DeadCodeTool(project_root="/test")
        assert tool.project_root == "/test"

    def test_tool_definition_is_valid(self) -> None:
        """Test that tool definition is valid."""
        tool = DeadCodeTool()
        definition = tool.get_tool_definition()

        assert "name" in definition
        assert "description" in definition
        assert "inputSchema" in definition
        assert "properties" in definition["inputSchema"]
        assert "examples" in definition["inputSchema"]
