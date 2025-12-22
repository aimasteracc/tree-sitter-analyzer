from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


@pytest.fixture
def tool():
    server = MagicMock()
    return ReadPartialTool(server)


def test_read_partial_tool_basic(tool):
    assert tool is not None


@pytest.mark.asyncio
async def test_read_partial_tool_execute_invalid_params(tool):
    """Test that execute properly handles invalid parameters."""
    # execute raises ValueError for missing required parameters
    with pytest.raises(ValueError, match="file_path is required"):
        await tool.execute({})
