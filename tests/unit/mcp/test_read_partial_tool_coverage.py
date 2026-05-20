from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


@pytest.fixture
def tool():
    server = MagicMock()
    return ReadPartialTool(server)


def test_read_partial_tool_basic(tool):
    assert tool is not None
    assert tool.file_output_manager is not None


@pytest.mark.asyncio
async def test_read_partial_tool_execute_invalid_params(tool):
    """Test that execute properly handles invalid parameters."""
    with pytest.raises(ValueError, match="file_path is required"):
        await tool.execute({})


@pytest.mark.asyncio
async def test_read_partial_tool_execute_missing_line_range(tool):
    """Test execute with file_path but no line range raises."""
    server = MagicMock()
    server.project_root = "/tmp"
    tool = ReadPartialTool(server)
    with pytest.raises((ValueError, KeyError)):
        await tool.execute({"file_path": "/nonexistent/file.py"})


def test_read_partial_tool_schema(tool):
    """Verify tool exposes a valid JSON schema."""
    schema = tool.get_tool_schema()
    assert isinstance(schema, dict)
    assert "type" in schema
