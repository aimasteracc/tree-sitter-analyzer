#!/usr/bin/env python3
"""
Quick MCP integration test for analyze_code_structure tool
"""

import asyncio
import sys
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool

# Add the tree_sitter_analyzer to path
sys.path.insert(0, str(Path(__file__).parent / "tree_sitter_analyzer"))


async def test_mcp_tool() -> None:
    """Test MCP tool integration"""
    test_file = Path("examples/Sample.java")
    if test_file.exists():
        print("Testing MCP tool with Sample.java...")

        # Create tool instance with current directory as project root
        current_dir = str(Path.cwd())
        tool = TableFormatTool(project_root=current_dir)

        # Test full format - use relative path
        result = await tool.execute(
            {"file_path": "examples/Sample.java", "format_type": "full"}
        )
        print("MCP tool test completed successfully")
        print(f"Result length: {len(result.get('table_output', ''))} characters")

        # Test compact format
        result_compact = await tool.execute(
            {"file_path": str(test_file), "format_type": "compact"}
        )
        compact_output = result_compact.get("table_output", "")
        print(f"Compact format length: {len(compact_output)} characters")

        # Test CSV format
        result_csv = await tool.execute(
            {"file_path": str(test_file), "format_type": "csv"}
        )
        print(
            f"CSV format length: {len(result_csv.get('table_output', ''))} characters"
        )

    else:
        print("Sample.java not found, skipping MCP test")


if __name__ == "__main__":
    asyncio.run(test_mcp_tool())
