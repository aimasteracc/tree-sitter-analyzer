from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


@pytest.fixture
def tool():
    server = MagicMock()
    return ReadPartialTool(server)


def test_read_partial_tool_basic(tool):
    assert tool is not None


def test_read_partial_tool_run_invalid_params(tool):
    with pytest.raises((KeyError, ValueError, TypeError)):  # More specific exceptions
        tool.run({})
