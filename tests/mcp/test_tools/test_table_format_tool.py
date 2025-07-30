#!/usr/bin/env python3
"""
Test module for TableFormatTool - Enhanced version with comprehensive testing

This module provides comprehensive tests for the TableFormatTool class,
covering both successful operations and error handling scenarios.
"""

import pytest
import pytest_asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool


class TestTableFormatTool:
    """Test cases for TableFormatTool class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.tool = TableFormatTool()
        
        # Create a temporary test file
        self.temp_dir = tempfile.mkdtemp()
        self.test_file_path = os.path.join(self.temp_dir, "test.java")
        
        # Simple Java content for testing
        self.test_java_content = '''
public class TestClass {
    private String name;
    
    public void setName(String name) {
        this.name = name;
    }
    
    public String getName() {
        return this.name;
    }
}
'''
        
        with open(self.test_file_path, 'w', encoding='utf-8') as f:
            f.write(self.test_java_content)

    def teardown_method(self):
        """Clean up test fixtures after each test method."""
        # Clean up temporary files
        if os.path.exists(self.test_file_path):
            os.remove(self.test_file_path)
        os.rmdir(self.temp_dir)
    
    def test_init(self):
        """Test TableFormatTool initialization."""
        assert self.tool is not None
        assert hasattr(self.tool, 'analysis_engine')

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
        
        # Test format_type enum values
        format_type_prop = props["format_type"]
        assert format_type_prop["enum"] == ["full", "compact", "csv"]
        assert format_type_prop["default"] == "full"

    def test_get_tool_definition(self, mocker) -> None:
        """Test get_tool_definition method."""
        mock_tool_instance = mocker.MagicMock()
        mock_tool = mocker.patch("mcp.types.Tool", return_value=mock_tool_instance)
        result = self.tool.get_tool_definition()
        
        # Basic assertion that result is returned
        assert result is not None

    def test_get_tool_definition_fallback(self, mocker) -> None:
        """Test get_tool_definition fallback when MCP is not available."""
        mocker.patch("mcp.types.Tool", side_effect=ImportError)
        result = self.tool.get_tool_definition()
        
        assert isinstance(result, dict)
        assert result["name"] == "format_table"
        assert "table" in result["description"].lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, mocker) -> None:
        """Test successful execution of format_table tool with CLI-compatible flow."""
        # Mock all dependencies - avoiding with statements
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch("tree_sitter_analyzer.language_detector.detect_language_from_file", return_value="java")
        
        # Mock performance monitor
        mock_monitor = mocker.patch("tree_sitter_analyzer.mcp.utils.get_performance_monitor")
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = mocker.MagicMock(return_value=mock_context)
        mock_monitor_instance.measure_operation.return_value.__exit__ = mocker.MagicMock(return_value=None)
        mock_monitor.return_value = mock_monitor_instance
        
        # Mock structure data in the correct format that the tool expects
        mock_structure_data = self._create_mock_structure_data()
        
        # Mock TableFormatter
        mock_formatter_class = mocker.patch("tree_sitter_analyzer.mcp.tools.table_format_tool.TableFormatter")
        mock_formatter = mocker.MagicMock()
        mock_formatter.format_structure.return_value = "# Mock Table Output\n| Column | Value |\n|--------|-------|\n| Test   | Data  |"
        mock_formatter_class.return_value = mock_formatter
        
        # Mock unified analysis engine to return a dummy result
        from unittest.mock import AsyncMock
        mocker.patch.object(self.tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=mocker.MagicMock())
        
        # Mock the conversion method to return the expected structure
        mocker.patch.object(self.tool, "_convert_analysis_result_to_dict", return_value=mock_structure_data)
        
        arguments = {
            "file_path": self.test_file_path,
            "format_type": "full"
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
        
        with pytest.raises(ValueError, match="file_path is required"):
            await self.tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, mocker) -> None:
        """Test execute with non-existent file."""
        mocker.patch("pathlib.Path.exists", return_value=False)
        arguments = {"file_path": "nonexistent.java"}
        
        with pytest.raises(FileNotFoundError):
            await self.tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_with_explicit_language(self, mocker) -> None:
        """Test execute with explicitly specified language."""
        # Mock dependencies - avoiding with statements
        mocker.patch("pathlib.Path.exists", return_value=True)
        
        # Mock performance monitor
        mock_monitor = mocker.patch("tree_sitter_analyzer.mcp.utils.get_performance_monitor")
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = mocker.MagicMock(return_value=mock_context)
        mock_monitor_instance.measure_operation.return_value.__exit__ = mocker.MagicMock(return_value=None)
        mock_monitor.return_value = mock_monitor_instance
        
        # Mock structure data
        mock_structure_data = self._create_mock_structure_data()
        
        # Mock TableFormatter
        mock_formatter_class = mocker.patch("tree_sitter_analyzer.mcp.tools.table_format_tool.TableFormatter")
        mock_formatter = mocker.MagicMock()
        mock_formatter.format_structure.return_value = "# Mock Output"
        mock_formatter_class.return_value = mock_formatter
        
        # Mock unified analysis engine to return a dummy result
        from unittest.mock import AsyncMock
        mocker.patch.object(self.tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=mocker.MagicMock())
        
        # Mock the conversion method to return the expected structure
        mocker.patch.object(self.tool, "_convert_analysis_result_to_dict", return_value=mock_structure_data)
        arguments = {
            "file_path": self.test_file_path,
            "format_type": "compact",
            "language": "java"
        }
        
        result = await self.tool.execute(arguments)
        
        assert result["language"] == "java"
        assert result["format_type"] == "compact"

    @pytest.mark.asyncio
    async def test_execute_structure_analysis_failure(self, mocker) -> None:
        """Test execute when structure analysis fails."""
        # Mock dependencies - avoiding with statements
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch("tree_sitter_analyzer.language_detector.detect_language_from_file", return_value="java")
        
        # Mock performance monitor
        mock_monitor = mocker.patch("tree_sitter_analyzer.mcp.utils.get_performance_monitor")
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = mocker.MagicMock(return_value=mock_context)
        mock_monitor_instance.measure_operation.return_value.__exit__ = mocker.MagicMock(return_value=None)
        mock_monitor.return_value = mock_monitor_instance
        
        # Mock unified analysis engine to return None (failure case)
        from unittest.mock import AsyncMock
        mocker.patch.object(self.tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=None)
        arguments = {"file_path": self.test_file_path}
        
        with pytest.raises(RuntimeError, match="Failed to analyze structure for file"):
            await self.tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_different_formats(self, mocker) -> None:
        """Test execute with different output formats."""
        # Mock dependencies - avoiding with statements
        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch("tree_sitter_analyzer.language_detector.detect_language_from_file", return_value="java")
        
        # Mock performance monitor
        mock_monitor = mocker.patch("tree_sitter_analyzer.mcp.utils.get_performance_monitor")
        mock_context = mocker.MagicMock()
        mock_monitor_instance = mocker.MagicMock()
        mock_monitor_instance.measure_operation.return_value.__enter__ = mocker.MagicMock(return_value=mock_context)
        mock_monitor_instance.measure_operation.return_value.__exit__ = mocker.MagicMock(return_value=None)
        mock_monitor.return_value = mock_monitor_instance
        
        # Mock structure data
        mock_structure_data = self._create_mock_structure_data()
        
        # Mock TableFormatter for different formats
        mock_formatter_class = mocker.patch("tree_sitter_analyzer.mcp.tools.table_format_tool.TableFormatter")
        mock_formatter = mocker.MagicMock()
        mock_formatter_class.return_value = mock_formatter
        
        # Mock unified analysis engine to return a dummy result
        from unittest.mock import AsyncMock
        mocker.patch.object(self.tool.analysis_engine, "analyze", new_callable=AsyncMock, return_value=mocker.MagicMock())
        
        # Mock the conversion method to return the expected structure
        mocker.patch.object(self.tool, "_convert_analysis_result_to_dict", return_value=mock_structure_data)
        
        # Test different formats
        for format_type in ["full", "compact", "csv"]:
            mock_formatter.format_structure.return_value = f"Mock {format_type} output"
            arguments = {
                "file_path": self.test_file_path,
                "format_type": format_type
            }
            
            result = await self.tool.execute(arguments)
            assert result["format_type"] == format_type
            assert f"Mock {format_type} output" in result["table_output"]

    def test_validate_arguments_success(self) -> None:
        """Test successful argument validation."""
        arguments = {
            "file_path": "/path/to/file.java",
            "format_type": "full",
            "language": "java"
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
        arguments = {
            "file_path": "/path/to/file.java",
            "format_type": "invalid"
        }
        with pytest.raises(ValueError, match="format_type must be one of"):
            self.tool.validate_arguments(arguments)
        
        # Test non-string format_type
        arguments = {
            "file_path": "/path/to/file.java",
            "format_type": 123
        }
        with pytest.raises(ValueError, match="format_type must be a string"):
            self.tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_language(self) -> None:
        """Test validation with invalid language."""
        arguments = {
            "file_path": "/path/to/file.java",
            "language": 123
        }
        
        with pytest.raises(ValueError, match="language must be a string"):
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
                            "return_type": "void"
                        },
                        {
                            "name": "getName", 
                            "start_line": 8,
                            "end_line": 10,
                            "parameters": [],
                            "return_type": "String"
                        }
                    ],
                    "fields": [
                        {
                            "name": "name",
                            "type": "String",
                            "line": 2
                        }
                    ]
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
                "annotation_count": 0
            }
        }


if __name__ == "__main__":
    pytest.main([__file__])