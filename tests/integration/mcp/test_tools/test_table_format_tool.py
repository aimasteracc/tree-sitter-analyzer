#!/usr/bin/env python3
"""
Test module for TableFormatTool - Enhanced version with comprehensive testing

This module provides comprehensive tests for the TableFormatTool class,
covering both successful operations and error handling scenarios.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)


class TestTableFormatTool:
    """Test cases for TableFormatTool class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.tool = TableFormatTool()

        # Create a temporary test file
        self.temp_dir = tempfile.mkdtemp()
        self.test_file_path = str(Path(self.temp_dir) / "test.java")

        # Simple Java content for testing
        self.test_java_content = """
public class TestClass {
    private String name;

    public void setName(String name) {
        this.name = name;
    }

    public String getName() {
        return this.name;
    }
}
"""

        with open(self.test_file_path, "w", encoding="utf-8") as f:
            f.write(self.test_java_content)

    def teardown_method(self):
        """Clean up test fixtures after each test method."""
        # Clean up temporary files
        test_file = Path(self.test_file_path)
        if test_file.exists():
            test_file.unlink()
        Path(self.temp_dir).rmdir()

    def test_init(self):
        """Test TableFormatTool initialization."""
        assert self.tool is not None
        assert hasattr(self.tool, "analysis_engine")

    def test_get_tool_schema(self):
        """Test get_tool_schema method returns proper JSON schema."""
        schema = self.tool.get_tool_schema()

        assert isinstance(schema, dict)
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

        # Check required parameters
        assert "file_path" in schema["required"]

        # Check properties
        props = schema["properties"]
        assert "file_path" in props
        assert "format_type" in props
        assert "language" in props
        assert "output_file" in props

        # Test format_type enum values - v1.6.1.4 specification formats only
        format_type_prop = props["format_type"]
        expected_formats = sorted(["full", "compact", "csv"])
        actual_formats = sorted(format_type_prop["enum"])
        assert actual_formats == expected_formats
        assert format_type_prop["default"] == "full"

    def test_get_tool_definition(self, mocker) -> None:
        """Test get_tool_definition method."""
        mock_tool_instance = mocker.MagicMock()
        mocker.patch("mcp.types.Tool", return_value=mock_tool_instance)
        result = self.tool.get_tool_definition()

        # Basic assertion that result is returned
        assert result is not None

    def test_get_tool_definition_fallback(self, mocker) -> None:
        """Test get_tool_definition fallback when MCP is not available."""
        mocker.patch("mcp.types.Tool", side_effect=ImportError)
        result = self.tool.get_tool_definition()

        assert isinstance(result, dict)
        assert result["name"] == "analyze_code_structure"
        assert "table" in result["description"].lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, mocker) -> None:
        """Test successful execution of analyze_code_structure tool with CLI-compatible flow."""
        # Mock all dependencies - avoiding with statements
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch(
            "tree_sitter_analyzer.language_detector.detect_language_from_file",
            return_value="java",
        )

        # Mock performance monitor
        mock_monitor = mocker.patch(
            "tree_sitter_analyzer.mcp.utils.get_performance_monitor"
        )
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = (
            mocker.MagicMock(return_value=mock_context)
        )
        mock_monitor_instance.measure_operation.return_value.__exit__ = (
            mocker.MagicMock(return_value=None)
        )
        mock_monitor.return_value = mock_monitor_instance

        # Mock structure data in the correct format that the tool expects
        mock_structure_data = self._create_mock_structure_data()

        # Mock unified analysis engine to return a dummy result
        from unittest.mock import AsyncMock

        mock_result = mocker.MagicMock()
        mock_result.elements = []  # Empty elements for simplicity

        mocker.patch.object(
            self.tool.analysis_engine,
            "analyze",
            new_callable=AsyncMock,
            return_value=mock_result,
        )

        # Mock the conversion method to return the expected structure
        mocker.patch.object(
            self.tool,
            "_convert_analysis_result_to_dict",
            return_value=mock_structure_data,
        )

        arguments = {
            "file_path": self.test_file_path,
            "format_type": "full",
            "output_format": "json",  # Use JSON format for test assertions
        }

        result = await self.tool.execute(arguments)

        assert result["file_path"] == self.test_file_path
        assert result["language"] == "java"
        assert result["format_type"] == "full"
        assert "table_output" in result
        assert "metadata" in result
        # Check actual metadata structure from implementation
        assert result["metadata"]["classes_count"] == 1
        assert result["metadata"]["methods_count"] == 2
        assert result["metadata"]["total_lines"] == 100

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self) -> None:
        """Test execute with missing file_path argument."""
        arguments = {"format_type": "full"}

        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            await self.tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, mocker) -> None:
        """Test execute with non-existent file."""
        # Mock path resolver to allow the file path to pass security validation
        mocker.patch.object(
            self.tool.path_resolver, "resolve", return_value="nonexistent.java"
        )
        mocker.patch.object(
            self.tool.path_resolver, "validate_path", return_value=(True, None)
        )
        mocker.patch("pathlib.Path.exists", return_value=False)
        arguments = {"file_path": "nonexistent.java"}

        with pytest.raises(ValueError, match="File not found"):
            await self.tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_with_explicit_language(self, mocker) -> None:
        """Test execute with explicitly specified language."""
        # Mock dependencies - avoiding with statements
        mocker.patch("pathlib.Path.exists", return_value=True)

        # Mock performance monitor
        mock_monitor = mocker.patch(
            "tree_sitter_analyzer.mcp.utils.get_performance_monitor"
        )
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = (
            mocker.MagicMock(return_value=mock_context)
        )
        mock_monitor_instance.measure_operation.return_value.__exit__ = (
            mocker.MagicMock(return_value=None)
        )
        mock_monitor.return_value = mock_monitor_instance

        # Mock structure data
        mock_structure_data = self._create_mock_structure_data()

        # Mock unified analysis engine to return a dummy result
        from unittest.mock import AsyncMock

        mocker.patch.object(
            self.tool.analysis_engine,
            "analyze",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(),
        )

        # Mock the conversion method to return the expected structure
        mocker.patch.object(
            self.tool,
            "_convert_analysis_result_to_dict",
            return_value=mock_structure_data,
        )
        arguments = {
            "file_path": self.test_file_path,
            "format_type": "compact",
            "language": "java",
            "output_format": "json",  # Use JSON format for test assertions
        }

        result = await self.tool.execute(arguments)

        assert result["language"] == "java"
        assert result["format_type"] == "compact"

    @pytest.mark.asyncio
    async def test_execute_structure_analysis_failure(self, mocker) -> None:
        """Test execute when structure analysis fails."""
        # Mock dependencies - avoiding with statements
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch(
            "tree_sitter_analyzer.language_detector.detect_language_from_file",
            return_value="java",
        )

        # Mock performance monitor
        mock_monitor = mocker.patch(
            "tree_sitter_analyzer.mcp.utils.get_performance_monitor"
        )
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = (
            mocker.MagicMock(return_value=mock_context)
        )
        mock_monitor_instance.measure_operation.return_value.__exit__ = (
            mocker.MagicMock(return_value=None)
        )
        mock_monitor.return_value = mock_monitor_instance

        # Mock unified analysis engine to return None (failure case)
        from unittest.mock import AsyncMock

        mocker.patch.object(
            self.tool.analysis_engine,
            "analyze",
            new_callable=AsyncMock,
            return_value=None,
        )
        arguments = {"file_path": self.test_file_path}

        with pytest.raises(RuntimeError, match="Failed to analyze structure for file"):
            await self.tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_different_formats(self, mocker) -> None:
        """Test execute with different output formats."""
        # Mock dependencies - avoiding with statements
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch(
            "tree_sitter_analyzer.language_detector.detect_language_from_file",
            return_value="java",
        )

        # Mock performance monitor
        mock_monitor = mocker.patch(
            "tree_sitter_analyzer.mcp.utils.get_performance_monitor"
        )
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = (
            mocker.MagicMock(return_value=mock_context)
        )
        mock_monitor_instance.measure_operation.return_value.__exit__ = (
            mocker.MagicMock(return_value=None)
        )
        mock_monitor.return_value = mock_monitor_instance

        # Mock structure data
        mock_structure_data = self._create_mock_structure_data()

        # Mock unified analysis engine to return a dummy result
        from unittest.mock import AsyncMock

        mocker.patch.object(
            self.tool.analysis_engine,
            "analyze",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(),
        )

        # Mock the conversion method to return the expected structure
        mocker.patch.object(
            self.tool,
            "_convert_analysis_result_to_dict",
            return_value=mock_structure_data,
        )

        # Test different formats - now using real LegacyTableFormatter
        for format_type in ["full", "compact", "csv"]:
            arguments = {
                "file_path": self.test_file_path,
                "format_type": format_type,
                "output_format": "json",  # Use JSON format for test assertions
            }

            result = await self.tool.execute(arguments)
            assert result["format_type"] == format_type
            # Check that output is generated (actual format content from LegacyTableFormatter)
            assert len(result["table_output"]) > 0
            # For CSV format, check for header presence instead of TestClass
            if format_type == "csv":
                assert (
                    "Type,Name,Signature,Visibility,Lines,Complexity,Doc"
                    in result["table_output"]
                )
            else:
                assert "TestClass" in result["table_output"]

    @pytest.mark.asyncio
    async def test_execute_with_file_output(self, mocker) -> None:
        """Test execute with file output functionality."""
        # Mock dependencies
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch(
            "tree_sitter_analyzer.language_detector.detect_language_from_file",
            return_value="java",
        )

        # Mock performance monitor
        mock_monitor = mocker.patch(
            "tree_sitter_analyzer.mcp.utils.get_performance_monitor"
        )
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = (
            mocker.MagicMock(return_value=mock_context)
        )
        mock_monitor_instance.measure_operation.return_value.__exit__ = (
            mocker.MagicMock(return_value=None)
        )
        mock_monitor.return_value = mock_monitor_instance

        # Mock structure data
        mock_structure_data = self._create_mock_structure_data()

        # Mock unified analysis engine
        from unittest.mock import AsyncMock

        mocker.patch.object(
            self.tool.analysis_engine,
            "analyze",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(),
        )

        # Mock the conversion method
        mocker.patch.object(
            self.tool,
            "_convert_analysis_result_to_dict",
            return_value=mock_structure_data,
        )

        # Mock file output manager
        mock_save_path = "/tmp/test_analysis.md"
        mock_save = mocker.patch.object(
            self.tool.file_output_manager, "save_to_file", return_value=mock_save_path
        )

        arguments = {
            "file_path": self.test_file_path,
            "format_type": "full",
            "output_file": "test_analysis",
            "output_format": "json",  # Use JSON format for test assertions
        }

        result = await self.tool.execute(arguments)

        # Check basic result
        assert result["file_path"] == self.test_file_path
        assert result["format_type"] == "full"
        assert "table_output" in result

        # Check file output results
        assert result["file_saved"] is True
        assert result["output_file_path"] == mock_save_path
        assert "file_save_error" not in result

        # Verify file output manager was called with actual LegacyTableFormatter output
        mock_save.assert_called_once()
        call_args = mock_save.call_args
        assert call_args.kwargs["base_name"] == "test_analysis"
        # Verify the content is actual formatted output (not mock)
        assert "TestClass" in call_args.kwargs["content"]
        assert "## Class Info" in call_args.kwargs["content"]

    @pytest.mark.asyncio
    async def test_execute_file_output_error(self, mocker) -> None:
        """Test execute with file output error handling."""
        # Mock dependencies
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch(
            "tree_sitter_analyzer.language_detector.detect_language_from_file",
            return_value="java",
        )

        # Mock performance monitor
        mock_monitor = mocker.patch(
            "tree_sitter_analyzer.mcp.utils.get_performance_monitor"
        )
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = (
            mocker.MagicMock(return_value=mock_context)
        )
        mock_monitor_instance.measure_operation.return_value.__exit__ = (
            mocker.MagicMock(return_value=None)
        )
        mock_monitor.return_value = mock_monitor_instance

        # Mock structure data
        mock_structure_data = self._create_mock_structure_data()

        # Mock FormatterRegistry to ensure it uses our mock formatter
        mock_formatter_registry = mocker.patch(
            "tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool.FormatterRegistry"
        )
        mock_formatter_registry.is_format_supported.return_value = True
        mock_formatter = mocker.MagicMock()
        table_output = "Mock table output"
        mock_formatter.format.return_value = table_output
        mock_formatter_registry.get_formatter.return_value = mock_formatter

        # Mock unified analysis engine
        from unittest.mock import AsyncMock

        mocker.patch.object(
            self.tool.analysis_engine,
            "analyze",
            new_callable=AsyncMock,
            return_value=mocker.MagicMock(),
        )

        # Mock the conversion method
        mocker.patch.object(
            self.tool,
            "_convert_analysis_result_to_dict",
            return_value=mock_structure_data,
        )

        # Mock file output manager to raise an error
        error_message = "Permission denied"
        mocker.patch.object(
            self.tool.file_output_manager,
            "save_to_file",
            side_effect=OSError(error_message),
        )

        arguments = {
            "file_path": self.test_file_path,
            "format_type": "full",
            "output_file": "test_analysis",
            "output_format": "json",  # Use JSON format for test assertions
        }

        result = await self.tool.execute(arguments)

        # Check that analysis still succeeded but file save failed
        assert result["file_path"] == self.test_file_path
        assert result["format_type"] == "full"
        assert "table_output" in result

        # Check file output error handling
        assert result["file_saved"] is False
        assert result["file_save_error"] == error_message
        assert "output_file_path" not in result

    def test_validate_arguments_success(self) -> None:
        """Test successful argument validation."""
        arguments = {
            "file_path": "/path/to/file.java",
            "format_type": "full",
            "language": "java",
        }

        # Should not raise any exception
        result = self.tool.validate_arguments(arguments)
        assert result is True

    def test_validate_arguments_missing_required(self) -> None:
        """Test validation with missing required arguments."""
        arguments = {"format_type": "full"}

        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            self.tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_file_path(self) -> None:
        """Test validation with invalid file_path."""
        # Test empty file_path
        arguments = {"file_path": ""}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            self.tool.validate_arguments(arguments)

        # Test non-string file_path
        arguments = {"file_path": 123}
        with pytest.raises(ValueError, match="file_path must be a string"):
            self.tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_format_type(self) -> None:
        """Test validation with invalid format_type."""
        # Test invalid format_type value
        arguments = {"file_path": "/path/to/file.java", "format_type": "invalid"}
        with pytest.raises(ValueError, match="format_type must be one of"):
            self.tool.validate_arguments(arguments)

        # Test non-string format_type
        arguments = {"file_path": "/path/to/file.java", "format_type": 123}
        with pytest.raises(ValueError, match="format_type must be a string"):
            self.tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_language(self) -> None:
        """Test validation with invalid language."""
        arguments = {"file_path": "/path/to/file.java", "language": 123}

        with pytest.raises(ValueError, match="language must be a string"):
            self.tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_output_file(self) -> None:
        """Test validation with invalid output_file."""
        # Test non-string output_file
        arguments = {"file_path": "/path/to/file.java", "output_file": 123}
        with pytest.raises(ValueError, match="output_file must be a string"):
            self.tool.validate_arguments(arguments)

        # Test empty output_file
        arguments = {"file_path": "/path/to/file.java", "output_file": ""}
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            self.tool.validate_arguments(arguments)

    def _create_mock_structure_data(self) -> dict:
        """Create mock structure data matching the actual implementation format."""
        return {
            "classes": [
                {
                    "name": "TestClass",
                    "start_line": 1,
                    "end_line": 10,
                    "methods": [
                        {
                            "name": "setName",
                            "start_line": 4,
                            "end_line": 6,
                            "parameters": ["String name"],
                            "return_type": "void",
                        },
                        {
                            "name": "getName",
                            "start_line": 8,
                            "end_line": 10,
                            "parameters": [],
                            "return_type": "String",
                        },
                    ],
                    "fields": [{"name": "name", "type": "String", "line": 2}],
                }
            ],
            "methods": [],
            "variables": [],
            "imports": [],
            "file_path": self.test_file_path,
            "language": "java",
            # Add statistics section as expected by the implementation
            "statistics": {
                "class_count": 1,
                "method_count": 2,
                "field_count": 1,
                "total_lines": 100,
                "import_count": 0,
                "annotation_count": 0,
            },
        }


if __name__ == "__main__":
    pytest.main([__file__])
