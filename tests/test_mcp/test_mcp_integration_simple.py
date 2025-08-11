#!/usr/bin/env python3
"""
Simplified MCP Integration Tests

This module contains simplified integration tests for the MCP server with
educational content generation tools, focusing on direct tool testing.
"""

import pytest
import tempfile
import os
from pathlib import Path

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer


class TestMCPIntegrationSimple:
    """Simplified test suite for MCP server integration with educational tools."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.server = TreeSitterAnalyzerMCPServer(self.temp_dir)
        
        # Create test file
        self.test_file = os.path.join(self.temp_dir, "test.py")
        with open(self.test_file, 'w') as f:
            f.write('''
class TestClass:
    def __init__(self, value):
        self.value = value
    
    def process(self, data):
        if data:
            return self.value * len(data)
        return 0
    
    def validate(self, item):
        return item is not None and len(str(item)) > 0
''')

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_server_has_educational_tools(self):
        """Test that server has the new educational tools initialized."""
        # Check that educational tools are initialized
        assert hasattr(self.server, 'learning_complexity_tool')
        assert hasattr(self.server, 'educational_content_generator')
        
        # Check that tools are properly configured
        assert self.server.learning_complexity_tool is not None
        assert self.server.educational_content_generator is not None

    @pytest.mark.asyncio
    async def test_analyze_learning_complexity_tool_direct(self):
        """Test the analyze_learning_complexity tool directly."""
        # Use relative path from temp_dir
        rel_path = os.path.relpath(self.test_file, self.temp_dir)
        arguments = {
            "file_path": rel_path,
            "analysis_depth": "detailed",
            "target_audience": "intermediate",
            "include_recommendations": True
        }

        result = await self.server.learning_complexity_tool.execute(arguments)

        assert "file_path" in result
        assert "language" in result
        assert "complexity_metrics" in result
        assert "learning_difficulty" in result

    @pytest.mark.asyncio
    async def test_generate_educational_content_tool_direct(self):
        """Test the generate_educational_content tool directly."""
        # Use relative path from temp_dir
        rel_path = os.path.relpath(self.test_file, self.temp_dir)
        arguments = {
            "project_path": rel_path,
            "target_audience": "intermediate",
            "content_type": "tutorial",
            "learning_objectives": [
                "Understand class structure",
                "Learn method implementation"
            ],
            "content_depth": "basic",
            "output_format": "structured"
        }

        result = await self.server.educational_content_generator.execute(arguments)

        assert "success" in result
        assert "project_path" in result
        if result["success"]:
            assert "generated_content" in result

    def test_tool_schema_validation(self):
        """Test that tool schemas are properly defined."""
        # Test learning complexity tool schema
        complexity_schema = self.server.learning_complexity_tool.get_tool_schema()
        assert complexity_schema["type"] == "object"
        assert "properties" in complexity_schema
        assert "required" in complexity_schema
        assert "file_path" in complexity_schema["required"]
        
        # Test educational content generator schema
        generator_schema = self.server.educational_content_generator.get_tool_schema()
        assert generator_schema["type"] == "object"
        assert "properties" in generator_schema
        assert "required" in generator_schema
        assert "project_path" in generator_schema["required"]

    @pytest.mark.asyncio
    async def test_error_handling_in_tool_calls(self):
        """Test error handling in educational tool calls."""
        # Test with invalid file path
        arguments = {
            "file_path": "nonexistent.py",
            "analysis_depth": "detailed",
            "target_audience": "intermediate"
        }
        
        result = await self.server.learning_complexity_tool.execute(arguments)
        
        # Should return error information
        assert "success" in result
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tool_workflow_integration(self):
        """Test the workflow of educational tools."""
        # Step 1: Analyze learning complexity
        complexity_args = {
            "file_path": "test.py",
            "target_audience": "intermediate"
        }
        complexity_result = await self.server.learning_complexity_tool.execute(complexity_args)
        
        # Step 2: Generate educational content
        content_args = {
            "project_path": "test.py",
            "target_audience": "intermediate",
            "content_type": "tutorial",
            "content_depth": "basic"
        }
        content_result = await self.server.educational_content_generator.execute(content_args)
        
        # Verify workflow results
        assert complexity_result["language"] == "python"
        assert content_result["success"] is True
        
        # Results should be consistent
        assert complexity_result["file_path"] == content_result["project_path"]

    @pytest.mark.asyncio
    async def test_concurrent_tool_calls(self):
        """Test concurrent tool calls."""
        import asyncio
        
        # Create multiple concurrent requests
        tasks = []
        for _ in range(3):
            args = {
                "file_path": "test.py",
                "target_audience": "intermediate",
                "analysis_depth": "basic"
            }
            tasks.append(self.server.learning_complexity_tool.execute(args))
        
        results = await asyncio.gather(*tasks)
        
        # All responses should be successful
        for result in results:
            assert "language" in result
            assert result["language"] == "python"

    def test_server_initialization_with_educational_tools(self):
        """Test that server initializes properly with educational tools."""
        server = TreeSitterAnalyzerMCPServer(self.temp_dir)
        
        # Check that educational tools are initialized
        assert hasattr(server, 'learning_complexity_tool')
        assert hasattr(server, 'educational_content_generator')
        
        # Check that tools are properly configured
        assert server.learning_complexity_tool is not None
        assert server.educational_content_generator is not None

    def test_tool_definitions(self):
        """Test tool definitions for MCP compatibility."""
        # Test learning complexity tool definition
        complexity_def = self.server.learning_complexity_tool.get_tool_definition()
        
        # Should work with or without MCP library
        if hasattr(complexity_def, 'name'):
            assert complexity_def.name == "analyze_learning_complexity"
            assert "learning complexity" in complexity_def.description.lower()
        else:
            assert complexity_def["name"] == "analyze_learning_complexity"
            assert "learning complexity" in complexity_def["description"].lower()
        
        # Test educational content generator definition
        generator_def = self.server.educational_content_generator.get_tool_definition()
        
        if hasattr(generator_def, 'name'):
            assert generator_def.name == "generate_educational_content"
            assert "educational content" in generator_def.description.lower()
        else:
            assert generator_def["name"] == "generate_educational_content"
            assert "educational content" in generator_def["description"].lower()

    @pytest.mark.asyncio
    async def test_different_output_formats(self):
        """Test different output formats for educational content generation."""
        formats = ["structured", "markdown", "json"]
        
        for output_format in formats:
            arguments = {
                "project_path": "test.py",
                "target_audience": "intermediate",
                "content_type": "tutorial",
                "output_format": output_format,
                "content_depth": "basic"
            }
            
            result = await self.server.educational_content_generator.execute(arguments)
            
            if result["success"]:
                assert "generated_content" in result
                assert result["generated_content"]["format"] == output_format


if __name__ == "__main__":
    pytest.main([__file__])
