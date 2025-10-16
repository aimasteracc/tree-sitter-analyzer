#!/usr/bin/env python3
"""
File Output Demo for Tree-sitter Analyzer

This demo shows how to use the new file output functionality
in the analyze_code_structure MCP tool.
"""

import json

# Example MCP tool call with file output
mcp_call_example = {
    "tool": "analyze_code_structure",
    "arguments": {
        "file_path": "examples/BigService.java",
        "format_type": "full",  # Options: "full", "compact", "csv"
        "output_file": "service_analysis",  # Will auto-detect extension based on content
    },
}

# Example response with file output
example_response = {
    "table_output": "| Class | Methods | Lines |\n|-------|---------|-------|\n| BigService | 66 | 1419 |",
    "format_type": "full",
    "file_path": "examples/BigService.java",
    "language": "java",
    "metadata": {
        "classes_count": 1,
        "methods_count": 66,
        "fields_count": 9,
        "total_lines": 1419,
    },
    "file_saved": True,
    "output_file_path": "/path/to/output/service_analysis.md",
}

# Environment configuration example
env_config = {
    "TREE_SITTER_PROJECT_ROOT": "/path/to/your/project",
    "TREE_SITTER_OUTPUT_PATH": "/path/to/output/directory",
}


def demo_content_type_detection():
    """Demo content type detection functionality."""
    print("=== Content Type Detection Demo ===")

    # Simulate FileOutputManager functionality
    test_cases = [
        ('{"key": "value", "data": [1, 2, 3]}', "json"),
        ("Name,Age,City\nJohn,30,NYC\nJane,25,LA", "csv"),
        ("# Title\n## Subtitle\n| Col1 | Col2 |\n|------|------|", "markdown"),
        ("Plain text content without special formatting", "text"),
    ]

    for content, expected_type in test_cases:
        # This would be the actual detection logic
        detected_type = detect_content_type_demo(content)
        extension = get_extension_demo(detected_type)
        print(f"Content: {content[:30]}...")
        print(f"Detected: {detected_type} → {extension}")
        print(f"Expected: {expected_type}")
        print("---")


def detect_content_type_demo(content):
    """Demo version of content type detection."""
    content = content.strip()

    # JSON detection
    if content.startswith(("{", "[")):
        try:
            json.loads(content)
            return "json"
        except:
            pass

    # CSV detection
    lines = content.split("\n")
    if len(lines) >= 2 and "," in lines[0]:
        return "csv"

    # Markdown detection
    if any(content.startswith(indicator) for indicator in ["#", "|", "```"]):
        return "markdown"

    return "text"


def get_extension_demo(content_type):
    """Demo version of extension mapping."""
    extensions = {"json": ".json", "csv": ".csv", "markdown": ".md", "text": ".txt"}
    return extensions.get(content_type, ".txt")


def print_usage_examples():
    """Print usage examples for the new functionality."""
    print("\n=== Usage Examples ===")

    print("\n1. Basic file output:")
    print(
        json.dumps(
            {
                "tool": "analyze_code_structure",
                "arguments": {
                    "file_path": "src/MyClass.java",
                    "output_file": "analysis_result",
                },
            },
            indent=2,
        )
    )

    print("\n2. CSV format output:")
    print(
        json.dumps(
            {
                "tool": "analyze_code_structure",
                "arguments": {
                    "file_path": "src/MyClass.java",
                    "format_type": "csv",
                    "output_file": "class_data",
                },
            },
            indent=2,
        )
    )

    print("\n3. Environment configuration:")
    print(
        json.dumps(
            {
                "env": {
                    "TREE_SITTER_PROJECT_ROOT": "/path/to/project",
                    "TREE_SITTER_OUTPUT_PATH": "/path/to/output",
                }
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    print("Tree-sitter Analyzer File Output Demo")
    print("=====================================")

    demo_content_type_detection()
    print_usage_examples()

    print("\n=== Key Features ===")
    print("✅ Automatic file extension detection based on content type")
    print("✅ Configurable output path via TREE_SITTER_OUTPUT_PATH")
    print("✅ Security validation for output locations")
    print("✅ Support for JSON, CSV, Markdown, and plain text formats")
    print("✅ Fallback to project root or current directory")

    print("\n=== Output Path Priority ===")
    print("1. TREE_SITTER_OUTPUT_PATH environment variable (highest)")
    print("2. Project root directory (from TREE_SITTER_PROJECT_ROOT)")
    print("3. Current working directory (fallback)")
