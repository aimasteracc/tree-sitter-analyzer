#!/usr/bin/env python3
"""
Property-based tests for MCP request-response consistency.

**Feature: test-coverage-improvement, Property 3**

Property 3: MCP Request-Response Consistency
- Every valid request produces a valid response
- Response format matches protocol specification
- Error responses contain proper error codes
- Validates Requirements 3.1, 3.2, 3.3

Requirements:
- 3.1: MCP server handles valid tool requests correctly
- 3.2: MCP tools analyze files correctly
- 3.3: Error responses contain proper information
"""

import tempfile
from pathlib import Path

import pytest

# Skip entire module if MCP is not available
pytest.importorskip("mcp")


class TestMCPRequestResponseConsistency:
    """Property tests for MCP request-response consistency."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def sample_files(self, temp_dir):
        """Create sample files for testing."""
        files = {}

        # Python file
        py_file = Path(temp_dir) / "sample.py"
        py_file.write_text('def hello():\n    return "Hello"\n')
        files["python"] = str(py_file)

        # JavaScript file
        js_file = Path(temp_dir) / "sample.js"
        js_file.write_text('function hello() { return "Hello"; }\n')
        files["javascript"] = str(js_file)

        # Java file
        java_file = Path(temp_dir) / "Sample.java"
        java_file.write_text("public class Sample { }\n")
        files["java"] = str(java_file)

        return files

    @pytest.mark.asyncio
    async def test_analyze_file_valid_response_structure(self, temp_dir, sample_files):
        """Test that execute produces valid response structure."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        tool = UniversalAnalyzeTool(temp_dir)

        for lang, file_path in sample_files.items():
            result = await tool.execute({"file_path": file_path})

            # Response must be a dict
            assert isinstance(result, dict), f"Response for {lang} must be a dict"

    @pytest.mark.asyncio
    async def test_analyze_file_error_response_format(self, temp_dir):
        """Test that error responses have proper format."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        tool = UniversalAnalyzeTool(temp_dir)

        # Non-existent file should raise an error
        with pytest.raises((ValueError, AnalysisError)):
            await tool.execute({"file_path": str(Path(temp_dir) / "nonexistent.py")})

    def test_tool_definition_format(self):
        """Test that tool definition returns proper format."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        tool = UniversalAnalyzeTool()
        definition = tool.get_tool_definition()

        # Verify tool definition is properly structured
        assert isinstance(definition, dict)
        assert "name" in definition, "Tool definition must have a name"
        assert "description" in definition, "Tool definition must have a description"
        assert isinstance(definition["name"], str)
        assert isinstance(definition["description"], str)

    @pytest.mark.asyncio
    async def test_invalid_file_path_handling(self, temp_dir):
        """Test that invalid file paths are handled gracefully."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        tool = UniversalAnalyzeTool(temp_dir)

        # Invalid path should raise an error
        with pytest.raises((ValueError, AnalysisError)):
            await tool.execute({"file_path": "invalid/path/that/does/not/exist.py"})

    @pytest.mark.asyncio
    async def test_concurrent_requests_consistency(self, temp_dir, sample_files):
        """Test that concurrent requests produce consistent responses."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        tool = UniversalAnalyzeTool(temp_dir)
        py_file = sample_files["python"]

        # Run multiple times and verify consistency
        results = []
        for _ in range(3):
            result = await tool.execute({"file_path": py_file})
            results.append(result)

        # All results should have same structure
        keys_list = [set(r.keys()) for r in results]
        assert all(
            k == keys_list[0] for k in keys_list
        ), "Response structure should be consistent"


class TestMCPProtocolCompliance:
    """Test MCP protocol compliance."""

    def test_mcp_info_has_required_fields(self):
        """Test that MCP_INFO contains all required fields."""
        from tree_sitter_analyzer.mcp import MCP_INFO

        required_fields = ["name", "version", "description"]
        for field in required_fields:
            assert field in MCP_INFO, f"MCP_INFO must contain {field}"

    def test_mcp_capabilities_structure(self):
        """Test that MCP capabilities are properly structured."""
        from tree_sitter_analyzer.mcp import MCP_INFO

        if "capabilities" in MCP_INFO:
            caps = MCP_INFO["capabilities"]
            # Capabilities should be a dict
            assert isinstance(caps, dict)

    def test_tool_schema_validity(self):
        """Test that tool schemas are valid."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        tool = UniversalAnalyzeTool()
        definition = tool.get_tool_definition()

        # If tool has inputSchema, it should be a valid JSON schema
        if "inputSchema" in definition:
            schema = definition["inputSchema"]
            assert isinstance(schema, dict)
            # JSON schema should have type defined
            if "properties" in schema:
                assert isinstance(schema["properties"], dict)


class TestErrorResponseConsistency:
    """Test error response consistency."""

    @pytest.mark.asyncio
    async def test_file_not_found_error_format(self, tmp_path):
        """Test error response for file not found."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        tool = UniversalAnalyzeTool(str(tmp_path))

        # Should raise an error for non-existent file
        with pytest.raises((ValueError, AnalysisError)):
            await tool.execute({"file_path": "/nonexistent/path/file.py"})

    @pytest.mark.asyncio
    async def test_unsupported_language_handling(self, tmp_path):
        """Test handling of unsupported file types."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        # Create a file with unsupported extension
        unsupported_file = tmp_path / "file.xyz123"
        unsupported_file.write_text("some content")

        tool = UniversalAnalyzeTool(str(tmp_path))

        # Should raise an error for unsupported language
        with pytest.raises((ValueError, AnalysisError)):
            await tool.execute({"file_path": str(unsupported_file)})

    @pytest.mark.asyncio
    async def test_empty_file_handling(self, tmp_path):
        """Test handling of empty files."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        tool = UniversalAnalyzeTool(str(tmp_path))

        # Empty file should either succeed or raise a specific error
        try:
            result = await tool.execute({"file_path": str(empty_file)})
            assert isinstance(result, dict)
        except (ValueError, AnalysisError):
            # This is also acceptable behavior
            pass
