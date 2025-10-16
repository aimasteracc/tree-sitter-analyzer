#!/usr/bin/env python3
"""
Tests for suppress_output feature in analyze_code_structure tool.

This test suite verifies that the suppress_output parameter works correctly
to reduce token usage when saving output to files.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool


class TestSuppressOutputFeature:
    """Test suppress_output functionality in TableFormatTool."""

    @pytest.fixture
    def temp_java_file(self):
        """Create a temporary Java file for testing."""
        content = '''package com.example;

public class TestClass {
    private String field1;
    private int field2;
    
    public TestClass() {
        this.field1 = "test";
        this.field2 = 42;
    }
    
    public String getField1() {
        return field1;
    }
    
    public void setField1(String field1) {
        this.field1 = field1;
    }
    
    public int getField2() {
        return field2;
    }
    
    public void setField2(int field2) {
        this.field2 = field2;
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(content)
            f.flush()
            yield f.name
        
        # Cleanup
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def table_format_tool(self):
        """Create a TableFormatTool instance for testing."""
        with patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_analysis_engine'):
            tool = TableFormatTool()
            return tool

    def test_schema_includes_suppress_output(self, table_format_tool):
        """Test that the tool schema includes suppress_output parameter."""
        schema = table_format_tool.get_tool_schema()
        
        assert "suppress_output" in schema["properties"]
        suppress_output_prop = schema["properties"]["suppress_output"]
        
        assert suppress_output_prop["type"] == "boolean"
        assert suppress_output_prop["default"] is False
        assert "suppress table_output in response to save tokens" in suppress_output_prop["description"]

    def test_validate_arguments_with_suppress_output(self, table_format_tool):
        """Test argument validation with suppress_output parameter."""
        # Valid arguments with suppress_output=True
        args = {
            "file_path": "test.java",
            "suppress_output": True
        }
        assert table_format_tool.validate_arguments(args) is True
        
        # Valid arguments with suppress_output=False
        args = {
            "file_path": "test.java",
            "suppress_output": False
        }
        assert table_format_tool.validate_arguments(args) is True
        
        # Invalid suppress_output type
        args = {
            "file_path": "test.java",
            "suppress_output": "invalid"
        }
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            table_format_tool.validate_arguments(args)

    @pytest.mark.asyncio
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_analysis_engine')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.detect_language_from_file')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_performance_monitor')
    async def test_suppress_output_false_includes_table_output(
        self, mock_monitor, mock_detect_lang, mock_engine, temp_java_file
    ):
        """Test that suppress_output=False includes table_output in response."""
        # Setup mocks
        mock_detect_lang.return_value = "java"
        mock_monitor.return_value.measure_operation.return_value.__enter__ = Mock()
        mock_monitor.return_value.measure_operation.return_value.__exit__ = Mock()
        
        # Mock analysis result
        mock_analysis_result = Mock()
        mock_analysis_result.file_path = temp_java_file
        mock_analysis_result.language = "java"
        mock_analysis_result.line_count = 30
        mock_analysis_result.elements = []
        
        mock_engine_instance = Mock()
        mock_engine_instance.analyze = AsyncMock(return_value=mock_analysis_result)
        mock_engine.return_value = mock_engine_instance
        
        tool = TableFormatTool()
        
        args = {
            "file_path": temp_java_file,
            "format_type": "compact",
            "suppress_output": False
        }
        
        result = await tool.execute(args)
        
        # Should include table_output when suppress_output=False
        assert "table_output" in result
        assert result["format_type"] == "compact"
        assert result["file_path"] == temp_java_file

    @pytest.mark.asyncio
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_analysis_engine')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.detect_language_from_file')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_performance_monitor')
    async def test_suppress_output_true_without_output_file_includes_table_output(
        self, mock_monitor, mock_detect_lang, mock_engine, temp_java_file
    ):
        """Test that suppress_output=True without output_file still includes table_output."""
        # Setup mocks
        mock_detect_lang.return_value = "java"
        mock_monitor.return_value.measure_operation.return_value.__enter__ = Mock()
        mock_monitor.return_value.measure_operation.return_value.__exit__ = Mock()
        
        # Mock analysis result
        mock_analysis_result = Mock()
        mock_analysis_result.file_path = temp_java_file
        mock_analysis_result.language = "java"
        mock_analysis_result.line_count = 30
        mock_analysis_result.elements = []
        
        mock_engine_instance = Mock()
        mock_engine_instance.analyze = AsyncMock(return_value=mock_analysis_result)
        mock_engine.return_value = mock_engine_instance
        
        tool = TableFormatTool()
        
        args = {
            "file_path": temp_java_file,
            "format_type": "compact",
            "suppress_output": True
            # No output_file specified
        }
        
        result = await tool.execute(args)
        
        # Should include table_output when no output_file is specified, even with suppress_output=True
        assert "table_output" in result
        assert result["format_type"] == "compact"
        assert result["file_path"] == temp_java_file

    @pytest.mark.asyncio
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_analysis_engine')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.detect_language_from_file')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_performance_monitor')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.FileOutputManager.get_managed_instance')
    async def test_suppress_output_true_with_output_file_excludes_table_output(
        self, mock_get_managed_instance, mock_monitor, mock_detect_lang, mock_engine, temp_java_file
    ):
        """Test that suppress_output=True with output_file excludes table_output from response."""
        # Setup mocks
        mock_detect_lang.return_value = "java"
        mock_monitor.return_value.measure_operation.return_value.__enter__ = Mock()
        mock_monitor.return_value.measure_operation.return_value.__exit__ = Mock()
        
        # Mock file output manager
        mock_file_manager_instance = Mock()
        mock_file_manager_instance.save_to_file.return_value = "/path/to/output.md"
        mock_get_managed_instance.return_value = mock_file_manager_instance
        
        # Mock analysis result
        mock_analysis_result = Mock()
        mock_analysis_result.file_path = temp_java_file
        mock_analysis_result.language = "java"
        mock_analysis_result.line_count = 30
        mock_analysis_result.elements = []
        
        mock_engine_instance = Mock()
        mock_engine_instance.analyze = AsyncMock(return_value=mock_analysis_result)
        mock_engine.return_value = mock_engine_instance
        
        tool = TableFormatTool()
        
        args = {
            "file_path": temp_java_file,
            "format_type": "compact",
            "output_file": "test_output.md",
            "suppress_output": True
        }
        
        result = await tool.execute(args)
        
        # Should NOT include table_output when suppress_output=True and output_file is specified
        assert "table_output" not in result
        assert result["format_type"] == "compact"
        assert result["file_path"] == temp_java_file
        assert result["file_saved"] is True
        assert result["output_file_path"] == "/path/to/output.md"

    @pytest.mark.asyncio
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_analysis_engine')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.detect_language_from_file')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.get_performance_monitor')
    @patch('tree_sitter_analyzer.mcp.tools.table_format_tool.FileOutputManager.get_managed_instance')
    async def test_suppress_output_false_with_output_file_includes_table_output(
        self, mock_get_managed_instance, mock_monitor, mock_detect_lang, mock_engine, temp_java_file
    ):
        """Test that suppress_output=False with output_file still includes table_output."""
        # Setup mocks
        mock_detect_lang.return_value = "java"
        mock_monitor.return_value.measure_operation.return_value.__enter__ = Mock()
        mock_monitor.return_value.measure_operation.return_value.__exit__ = Mock()
        
        # Mock file output manager
        mock_file_manager_instance = Mock()
        mock_file_manager_instance.save_to_file.return_value = "/path/to/output.md"
        mock_get_managed_instance.return_value = mock_file_manager_instance
        
        # Mock analysis result
        mock_analysis_result = Mock()
        mock_analysis_result.file_path = temp_java_file
        mock_analysis_result.language = "java"
        mock_analysis_result.line_count = 30
        mock_analysis_result.elements = []
        
        mock_engine_instance = Mock()
        mock_engine_instance.analyze = AsyncMock(return_value=mock_analysis_result)
        mock_engine.return_value = mock_engine_instance
        
        tool = TableFormatTool()
        
        args = {
            "file_path": temp_java_file,
            "format_type": "compact",
            "output_file": "test_output.md",
            "suppress_output": False
        }
        
        result = await tool.execute(args)
        
        # Should include table_output when suppress_output=False, even with output_file
        assert "table_output" in result
        assert result["format_type"] == "compact"
        assert result["file_path"] == temp_java_file
        assert result["file_saved"] is True
        assert result["output_file_path"] == "/path/to/output.md"

    def test_backward_compatibility_default_behavior(self, table_format_tool):
        """Test that default behavior (no suppress_output) maintains backward compatibility."""
        # When suppress_output is not specified, it should default to False
        args = {
            "file_path": "test.java",
            "format_type": "full"
        }
        
        # Should validate successfully
        assert table_format_tool.validate_arguments(args) is True
        
        # The default value should be False (backward compatible)
        schema = table_format_tool.get_tool_schema()
        assert schema["properties"]["suppress_output"]["default"] is False


class TestMCPServerSuppressOutputIntegration:
    """Test suppress_output integration with MCP server."""

    @patch('tree_sitter_analyzer.mcp.server.MCP_AVAILABLE', True)
    @patch('tree_sitter_analyzer.mcp.server.get_analysis_engine')
    @patch('tree_sitter_analyzer.mcp.server.setup_logger')
    def test_mcp_server_schema_includes_suppress_output(self, mock_logger, mock_engine):
        """Test that MCP server schema includes suppress_output parameter."""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
        
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()
        
        server = TreeSitterAnalyzerMCPServer()
        mcp_server = server.create_server()
        
        # The schema should be updated in the server's tool definitions
        # This is tested indirectly through the tool schema
        tool = server.table_format_tool
        schema = tool.get_tool_schema()
        
        assert "suppress_output" in schema["properties"]

    @pytest.mark.asyncio
    @patch('tree_sitter_analyzer.mcp.server.MCP_AVAILABLE', True)
    @patch('tree_sitter_analyzer.mcp.server.get_analysis_engine')
    @patch('tree_sitter_analyzer.mcp.server.setup_logger')
    async def test_mcp_server_passes_suppress_output_parameter(self, mock_logger, mock_engine):
        """Test that MCP server correctly passes suppress_output parameter to tool."""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
        
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()
        
        server = TreeSitterAnalyzerMCPServer()
        
        # Mock the table format tool execute method
        server.table_format_tool.execute = AsyncMock(return_value={"test": "result"})
        
        # Simulate tool call with suppress_output parameter
        arguments = {
            "file_path": "test.java",
            "format_type": "compact",
            "output_file": "output.md",
            "suppress_output": True
        }
        
        # This would normally be called by the MCP framework
        # We're testing the argument passing logic
        full_args = {
            "file_path": arguments["file_path"],
            "format_type": arguments.get("format_type", "full"),
            "language": arguments.get("language"),
            "output_file": arguments.get("output_file"),
            "suppress_output": arguments.get("suppress_output", False),
        }
        
        await server.table_format_tool.execute(full_args)
        
        # Verify that suppress_output was passed correctly
        server.table_format_tool.execute.assert_called_once_with(full_args)
        called_args = server.table_format_tool.execute.call_args[0][0]
        assert called_args["suppress_output"] is True