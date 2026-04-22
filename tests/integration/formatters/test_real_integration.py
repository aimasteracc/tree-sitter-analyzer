"""Real Integration Test — test format tools with actual tree-sitter-analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool as TableFormatTool,
)

PYTHON_CALCULATOR = '''
class Calculator:
    """A simple calculator class."""

    def __init__(self):
        self.result = 0

    def add(self, value: int) -> int:
        self.result += value
        return self.result

    def subtract(self, value: int) -> int:
        self.result -= value
        return self.result

    def multiply(self, value: int) -> int:
        self.result *= value
        return self.result

    def reset(self) -> None:
        self.result = 0
'''


@pytest.fixture
def temp_python_file():
    temp_dir = tempfile.mkdtemp()
    python_file = Path(temp_dir) / "test_class.py"
    python_file.write_text(PYTHON_CALCULATOR, encoding="utf-8")
    yield temp_dir, python_file
    python_file.unlink(missing_ok=True)
    Path(temp_dir).rmdir()


@pytest.mark.asyncio
async def test_table_format_tool_integration(temp_python_file):
    temp_dir, python_file = temp_python_file
    tool = TableFormatTool(project_root=temp_dir)

    for format_type in ["full", "compact", "csv"]:
        result = await tool.execute({
            "file_path": str(python_file),
            "format_type": format_type,
            "output_format": "json",
        })

        assert result["format_type"] == format_type
        assert result["language"] == "python"
        assert "table_output" in result
        assert result["table_output"].strip()

        table_output = result["table_output"]
        if format_type == "full":
            assert "=" in table_output or "#" in table_output
            assert "Calculator" in table_output or "FUNCTION" in table_output
        elif format_type == "compact":
            assert "-" in table_output or "|" in table_output
            assert "Calculator" in table_output or "function" in table_output.lower()
        elif format_type == "csv":
            assert "," in table_output
            assert "Method" in table_output or "__init__" in table_output


@pytest.mark.asyncio
async def test_format_consistency_across_types(temp_python_file):
    temp_dir, python_file = temp_python_file
    tool = TableFormatTool(project_root=temp_dir)

    formats = {}
    for format_type in ["full", "compact", "csv"]:
        result = await tool.execute({
            "file_path": str(python_file),
            "format_type": format_type,
            "output_format": "json",
        })
        formats[format_type] = result["table_output"]

    essential = ["add", "subtract", "multiply", "reset"]
    for format_type, output in formats.items():
        for name in essential:
            assert name in output, f"Missing '{name}' in {format_type}"
        if format_type != "csv":
            assert "Calculator" in output
