#!/usr/bin/env python3
"""
Demonstration of the suppress_output feature in analyze_code_structure tool.

This script shows how to use the suppress_output parameter to reduce token usage
when saving analysis results to files.
"""

import asyncio
import tempfile
from pathlib import Path

from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool


async def demo_suppress_output():
    """Demonstrate the suppress_output feature."""

    # Create a sample Java file for demonstration
    sample_java_code = """package com.example.demo;

public class SampleClass {
    private String name;
    private int value;

    public SampleClass(String name, int value) {
        this.name = name;
        this.value = value;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }

    @Override
    public String toString() {
        return "SampleClass{name='" + name + "', value=" + value + "}";
    }
}
"""

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
        f.write(sample_java_code)
        temp_file = f.name

    try:
        tool = TableFormatTool()

        print("=== Suppress Output Feature Demo ===\n")

        # Demo 1: Normal behavior (backward compatibility)
        print("1. Normal behavior (suppress_output=False, default):")
        result1 = await tool.execute({"file_path": temp_file, "format_type": "compact"})

        print(f"   - Contains table_output: {'table_output' in result1}")
        print(f"   - Table output length: {len(result1.get('table_output', ''))}")
        print(f"   - File saved: {result1.get('file_saved', False)}")
        print()

        # Demo 2: With output file but suppress_output=False
        print("2. With output file, suppress_output=False:")
        result2 = await tool.execute(
            {
                "file_path": temp_file,
                "format_type": "compact",
                "output_file": "demo_output_with_table.md",
                "suppress_output": False,
            }
        )

        print(f"   - Contains table_output: {'table_output' in result2}")
        print(f"   - Table output length: {len(result2.get('table_output', ''))}")
        print(f"   - File saved: {result2.get('file_saved', False)}")
        print(f"   - Output file: {result2.get('output_file_path', 'N/A')}")
        print()

        # Demo 3: Token-saving mode (suppress_output=True with output file)
        print("3. Token-saving mode (suppress_output=True with output file):")
        result3 = await tool.execute(
            {
                "file_path": temp_file,
                "format_type": "compact",
                "output_file": "demo_output_no_table.md",
                "suppress_output": True,
            }
        )

        print(f"   - Contains table_output: {'table_output' in result3}")
        print(f"   - Table output length: {len(result3.get('table_output', ''))}")
        print(f"   - File saved: {result3.get('file_saved', False)}")
        print(f"   - Output file: {result3.get('output_file_path', 'N/A')}")
        print()

        # Demo 4: suppress_output=True without output file (still shows table_output)
        print("4. suppress_output=True without output file (still shows table_output):")
        result4 = await tool.execute(
            {
                "file_path": temp_file,
                "format_type": "compact",
                "suppress_output": True,
                # No output_file specified
            }
        )

        print(f"   - Contains table_output: {'table_output' in result4}")
        print(f"   - Table output length: {len(result4.get('table_output', ''))}")
        print(f"   - File saved: {result4.get('file_saved', False)}")
        print()

        # Calculate token savings
        normal_tokens = len(result2.get("table_output", ""))
        suppressed_tokens = len(result3.get("table_output", ""))
        token_savings = normal_tokens - suppressed_tokens

        print("=== Token Savings Analysis ===")
        print(f"Normal response size: {normal_tokens} characters")
        print(f"Suppressed response size: {suppressed_tokens} characters")
        print(
            f"Token savings: {token_savings} characters ({token_savings / normal_tokens * 100:.1f}% reduction)"
        )
        print()

        print("=== Usage Recommendations ===")
        print("• Use suppress_output=True when:")
        print("  - You only need the file output")
        print("  - Working with large files to save tokens")
        print("  - Batch processing multiple files")
        print()
        print("• Use suppress_output=False (default) when:")
        print("  - You need to see the analysis results immediately")
        print("  - Working interactively")
        print("  - File output is optional")

    finally:
        # Cleanup
        Path(temp_file).unlink(missing_ok=True)

        # Clean up demo output files
        for filename in ["demo_output_with_table.md", "demo_output_no_table.md"]:
            Path(filename).unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(demo_suppress_output())
