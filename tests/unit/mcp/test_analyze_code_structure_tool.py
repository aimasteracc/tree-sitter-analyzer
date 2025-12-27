import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)


@pytest.mark.asyncio
async def test_analyze_code_structure_tool_definition():
    tool = AnalyzeCodeStructureTool()
    definition = tool.get_tool_definition()
    assert definition["name"] == "analyze_code_structure"
    assert "description" in definition
    assert "inputSchema" in definition
    assert "file_path" in definition["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_server_registration():
    server = TreeSitterAnalyzerMCPServer()
    # Check if tool instance is initialized
    assert hasattr(server, "analyze_code_structure_tool")
    assert isinstance(server.analyze_code_structure_tool, AnalyzeCodeStructureTool)


@pytest.mark.asyncio
async def test_analyze_code_structure_execution(tmp_path):
    # Create a dummy python file
    test_file = tmp_path / "test.py"
    test_file.write_text("class MyClass:\n    def my_method(self):\n        pass\n")

    tool = AnalyzeCodeStructureTool(project_root=str(tmp_path))
    # Explicitly request JSON format to verify fields
    result = await tool.execute({"file_path": str(test_file), "output_format": "json"})

    assert result["success"] is True
    assert "table_output" in result
    assert "metadata" in result
    assert result["metadata"]["classes_count"] == 1
    assert result["metadata"]["methods_count"] == 1
