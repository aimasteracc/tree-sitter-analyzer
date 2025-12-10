#!/usr/bin/env python3
"""
TOON Format Demo

Demonstrates the TOON (Token-Oriented Object Notation) format features
for LLM-optimized code analysis output.

Usage:
    uv run python examples/toon_demo.py
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder
from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter


def demo_basic_encoding():
    """Demonstrate basic TOON encoding."""
    print("\n" + "=" * 60)
    print("1. BASIC TOON ENCODING")
    print("=" * 60)

    encoder = ToonEncoder()

    # Simple values
    print("\n--- Primitive Values ---")
    print(f"  null:    {encoder.encode_value(None)}")
    print(f"  true:    {encoder.encode_value(True)}")
    print(f"  false:   {encoder.encode_value(False)}")
    print(f"  number:  {encoder.encode_value(42)}")
    print(f"  float:   {encoder.encode_value(3.14)}")
    print(f"  string:  {encoder.encode_value('hello')}")

    # String with special characters
    print("\n--- String Escaping ---")
    special = "line1\nline2\twith:colons"
    print(f"  Original: {repr(special)}")
    print(f"  Encoded:  {encoder.encode_value(special)}")


def demo_dict_encoding():
    """Demonstrate dictionary encoding."""
    print("\n" + "=" * 60)
    print("2. DICTIONARY ENCODING")
    print("=" * 60)

    encoder = ToonEncoder()

    # Simple dict
    simple = {"name": "example", "count": 42, "active": True}
    print("\n--- Simple Dictionary ---")
    print("Input:", simple)
    print("\nJSON output:")
    print(json.dumps(simple, indent=2))
    print("\nTOON output:")
    print(encoder.encode(simple))

    # Nested dict
    nested = {
        "file": "sample.py",
        "metadata": {
            "language": "python",
            "version": "3.11",
        },
        "statistics": {
            "lines": 100,
            "methods": 5,
        },
    }
    print("\n--- Nested Dictionary ---")
    print("Input:", nested)
    print("\nTOON output:")
    print(encoder.encode(nested))


def demo_array_table():
    """Demonstrate array table encoding."""
    print("\n" + "=" * 60)
    print("3. ARRAY TABLE FORMAT")
    print("=" * 60)

    encoder = ToonEncoder()

    # Homogeneous array of dicts
    methods = [
        {"name": "init", "visibility": "public", "lines": "1-10"},
        {"name": "process", "visibility": "public", "lines": "12-45"},
        {"name": "validate", "visibility": "private", "lines": "47-60"},
        {"name": "cleanup", "visibility": "public", "lines": "62-70"},
    ]

    print("\n--- Array of Objects ---")
    print("Input:")
    print(json.dumps(methods, indent=2))

    print("\nJSON size:", len(json.dumps(methods)), "chars")

    print("\nTOON output (compact table format):")
    toon_output = encoder.encode_array_table(methods)
    print(toon_output)
    print("\nTOON size:", len(toon_output), "chars")

    # Calculate reduction
    json_size = len(json.dumps(methods))
    toon_size = len(toon_output)
    reduction = (1 - toon_size / json_size) * 100
    print(f"\nReduction: {reduction:.1f}%")


def demo_tabs_delimiter():
    """Demonstrate tab delimiter mode."""
    print("\n" + "=" * 60)
    print("4. TAB DELIMITER MODE")
    print("=" * 60)

    # Compare comma vs tab delimiters
    data = [
        {"file": "app.py", "lines": 100, "methods": 5},
        {"file": "utils.py", "lines": 50, "methods": 3},
        {"file": "models.py", "lines": 200, "methods": 10},
    ]

    comma_encoder = ToonEncoder(use_tabs=False)
    tab_encoder = ToonEncoder(use_tabs=True)

    print("\n--- Comma Delimiter (default) ---")
    comma_output = comma_encoder.encode_array_table(data)
    print(comma_output)

    print("\n--- Tab Delimiter (--toon-use-tabs) ---")
    tab_output = tab_encoder.encode_array_table(data)
    # Show tabs as visible markers for demo
    print(tab_output.replace("\t", "→"))

    print(f"\nComma version: {len(comma_output)} chars")
    print(f"Tab version:   {len(tab_output)} chars")


def demo_formatter():
    """Demonstrate ToonFormatter usage."""
    print("\n" + "=" * 60)
    print("5. TOON FORMATTER (High-Level API)")
    print("=" * 60)

    formatter = ToonFormatter()

    # MCP-style response
    mcp_response = {
        "success": True,
        "data": {
            "file_path": "sample.py",
            "language": "python",
            "classes": [
                {"name": "Calculator"},
                {"name": "Helper"},
            ],
            "methods": [
                {"name": "add", "visibility": "public", "lines": "10-15"},
                {"name": "subtract", "visibility": "public", "lines": "17-22"},
            ],
        },
        "metadata": {
            "execution_time": 0.045,
            "cache_hit": True,
        },
    }

    print("\n--- MCP Response Formatting ---")
    print("Input: MCP tool response with nested data")
    print("\nTOON output:")
    print(formatter.format(mcp_response))


def demo_error_handling():
    """Demonstrate error handling features."""
    print("\n" + "=" * 60)
    print("6. ERROR HANDLING")
    print("=" * 60)

    encoder = ToonEncoder(fallback_to_json=True)

    # Circular reference
    print("\n--- Circular Reference Detection ---")
    circular: dict = {"key": "value"}
    circular["self"] = circular

    print("Input: dict with circular reference")
    print("Output (falls back to JSON):")
    result = encoder.encode_safe(circular)
    print(result[:100] + "..." if len(result) > 100 else result)

    # Safe encoding
    print("\n--- Safe Encoding (Never Fails) ---")
    encoder_safe = ToonEncoder(fallback_to_json=True)
    print("encode_safe() always returns a string, never raises")
    print(f"Result: {encoder_safe.encode_safe({'normal': 'data'})}")


def demo_cli_usage():
    """Show CLI usage examples."""
    print("\n" + "=" * 60)
    print("7. CLI USAGE EXAMPLES")
    print("=" * 60)

    print("""
--- Basic TOON Output ---
  uv run python -m tree_sitter_analyzer.cli file.py --structure --format toon

--- With Tab Delimiter ---
  uv run python -m tree_sitter_analyzer.cli file.py --structure --format toon --toon-use-tabs

--- Summary with TOON ---
  uv run python -m tree_sitter_analyzer.cli file.py --summary --format toon

--- Advanced Analysis ---
  uv run python -m tree_sitter_analyzer.cli file.py --advanced --format toon

--- Partial Read ---
  uv run python -m tree_sitter_analyzer.cli file.py --partial-read --start-line 1 --end-line 50 --format toon
""")


def demo_mcp_usage():
    """Show MCP tool usage examples."""
    print("\n" + "=" * 60)
    print("8. MCP TOOL USAGE")
    print("=" * 60)

    print("""
All MCP tools support the 'output_format' parameter:

--- analyze_code_structure ---
  {
    "file_path": "sample.py",
    "output_format": "toon"
  }

--- list_files ---
  {
    "directory": "src",
    "output_format": "toon"
  }

--- search_content ---
  {
    "pattern": "def.*test",
    "output_format": "toon"
  }

--- query_code ---
  {
    "file_path": "sample.py",
    "query_key": "function",
    "output_format": "toon"
  }
""")


def main():
    """Run all demos."""
    print("=" * 60)
    print("TOON FORMAT DEMONSTRATION")
    print("Token-Oriented Object Notation for LLM Optimization")
    print("=" * 60)

    demo_basic_encoding()
    demo_dict_encoding()
    demo_array_table()
    demo_tabs_delimiter()
    demo_formatter()
    demo_error_handling()
    demo_cli_usage()
    demo_mcp_usage()

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)
    print("\nFor more information, run the token benchmark:")
    print("  uv run python examples/toon_token_benchmark.py")


if __name__ == "__main__":
    main()
