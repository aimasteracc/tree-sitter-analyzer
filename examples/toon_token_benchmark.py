#!/usr/bin/env python3
"""
TOON Token Reduction Benchmark

Measures and compares token consumption between JSON and TOON formats.
Demonstrates the 50-70% token reduction that TOON provides for LLM consumption.

Usage:
    uv run python examples/toon_token_benchmark.py

    # With tiktoken (more accurate):
    uv add tiktoken --optional
    uv run python examples/toon_token_benchmark.py
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter


@dataclass
class TokenCount:
    """Token count result."""

    format_name: str
    char_count: int
    token_count: int  # Estimated or actual
    is_estimated: bool


class TokenCounter:
    """
    Token counter that uses tiktoken if available, otherwise estimates.

    Token estimation uses a simple heuristic: ~4 characters per token for English text.
    This is a rough approximation of GPT-4/Claude tokenization.
    """

    CHARS_PER_TOKEN = 4  # Rough estimation for English/code

    def __init__(self):
        """Initialize token counter."""
        self._tiktoken = None
        self._encoding = None

        try:
            import tiktoken

            self._tiktoken = tiktoken
            self._encoding = tiktoken.get_encoding("cl100k_base")
            print("✓ Using tiktoken for accurate token counting")
        except ImportError:
            print("⚠ tiktoken not available, using character-based estimation")
            print("  Install with: uv add tiktoken --optional")

    def count_tokens(self, text: str, format_name: str) -> TokenCount:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for
            format_name: Name of the format (for reporting)

        Returns:
            TokenCount with results
        """
        char_count = len(text)

        if self._encoding:
            # Accurate counting with tiktoken
            tokens = self._encoding.encode(text)
            return TokenCount(
                format_name=format_name,
                char_count=char_count,
                token_count=len(tokens),
                is_estimated=False,
            )
        else:
            # Estimation based on character count
            estimated_tokens = char_count // self.CHARS_PER_TOKEN
            return TokenCount(
                format_name=format_name,
                char_count=char_count,
                token_count=estimated_tokens,
                is_estimated=True,
            )


def create_sample_analysis_result() -> dict:
    """Create a realistic code analysis result for benchmarking."""
    return {
        "file_path": "/src/components/UserDashboard.tsx",
        "language": "typescript",
        "package": "com.example.dashboard",
        "classes": [
            {
                "name": "UserDashboard",
                "visibility": "public",
                "line_range": {"start": 15, "end": 245},
            },
            {
                "name": "UserProfile",
                "visibility": "public",
                "line_range": {"start": 250, "end": 380},
            },
            {
                "name": "NotificationPanel",
                "visibility": "private",
                "line_range": {"start": 385, "end": 520},
            },
        ],
        "methods": [
            {
                "name": "constructor",
                "visibility": "public",
                "return_type": "void",
                "parameters": [],
                "line_range": {"start": 20, "end": 35},
            },
            {
                "name": "fetchUserData",
                "visibility": "public",
                "return_type": "Promise<User>",
                "parameters": [{"name": "userId", "type": "string"}],
                "line_range": {"start": 40, "end": 65},
            },
            {
                "name": "updateProfile",
                "visibility": "public",
                "return_type": "Promise<void>",
                "parameters": [{"name": "profile", "type": "UserProfile"}],
                "line_range": {"start": 70, "end": 95},
            },
            {
                "name": "handleNotification",
                "visibility": "private",
                "return_type": "void",
                "parameters": [{"name": "notification", "type": "Notification"}],
                "line_range": {"start": 100, "end": 125},
            },
            {
                "name": "renderDashboard",
                "visibility": "public",
                "return_type": "JSX.Element",
                "parameters": [],
                "line_range": {"start": 130, "end": 180},
            },
            {
                "name": "componentDidMount",
                "visibility": "public",
                "return_type": "void",
                "parameters": [],
                "line_range": {"start": 185, "end": 200},
            },
            {
                "name": "componentWillUnmount",
                "visibility": "public",
                "return_type": "void",
                "parameters": [],
                "line_range": {"start": 205, "end": 215},
            },
            {
                "name": "handleError",
                "visibility": "private",
                "return_type": "void",
                "parameters": [{"name": "error", "type": "Error"}],
                "line_range": {"start": 220, "end": 240},
            },
        ],
        "fields": [
            {"name": "userData", "type": "User | null", "visibility": "private"},
            {"name": "isLoading", "type": "boolean", "visibility": "private"},
            {
                "name": "notifications",
                "type": "Notification[]",
                "visibility": "private",
            },
            {"name": "errorMessage", "type": "string | null", "visibility": "private"},
        ],
        "imports": [
            {"statement": "import React, { Component } from 'react'"},
            {"statement": "import { User, UserProfile, Notification } from './types'"},
            {
                "statement": "import { fetchUser, updateUserProfile } from '../api/userApi'"
            },
            {
                "statement": "import { NotificationService } from '../services/NotificationService'"
            },
        ],
        "statistics": {
            "class_count": 3,
            "method_count": 8,
            "field_count": 4,
            "import_count": 4,
            "total_lines": 520,
            "code_lines": 420,
            "comment_lines": 65,
            "blank_lines": 35,
        },
        "analysis_metadata": {
            "analysis_time": 0.0234,
            "language": "typescript",
            "file_path": "/src/components/UserDashboard.tsx",
            "analyzer_version": "2.0.0",
        },
    }


def create_mcp_response() -> dict:
    """Create a typical MCP tool response for benchmarking."""
    return {
        "success": True,
        "data": {
            "files_analyzed": 15,
            "total_lines": 3420,
            "results": [
                {"file": "src/app.py", "classes": 2, "methods": 12, "lines": 245},
                {"file": "src/utils.py", "classes": 0, "methods": 8, "lines": 156},
                {"file": "src/models.py", "classes": 5, "methods": 25, "lines": 380},
                {
                    "file": "src/api/routes.py",
                    "classes": 1,
                    "methods": 15,
                    "lines": 290,
                },
                {
                    "file": "src/api/handlers.py",
                    "classes": 3,
                    "methods": 18,
                    "lines": 320,
                },
            ],
        },
        "metadata": {
            "execution_time": 1.234,
            "cache_hit": False,
            "version": "1.6.0",
        },
    }


def create_simple_dict() -> dict:
    """Create a simple dictionary for benchmarking."""
    return {
        "name": "example_function",
        "visibility": "public",
        "return_type": "string",
        "parameters": [
            {"name": "input", "type": "string"},
            {"name": "options", "type": "Options"},
        ],
        "line_range": {"start": 10, "end": 25},
        "complexity": 5,
        "is_async": True,
    }


def run_benchmark(
    data: dict, name: str, counter: TokenCounter
) -> tuple[TokenCount, TokenCount, float]:
    """
    Run benchmark comparing JSON and TOON formats.

    Args:
        data: Data to encode
        name: Name of the benchmark
        counter: Token counter instance

    Returns:
        Tuple of (json_count, toon_count, reduction_percentage)
    """
    # Encode as JSON
    json_output = json.dumps(data, indent=2, ensure_ascii=False)

    # Encode as TOON
    formatter = ToonFormatter()
    toon_output = formatter.format(data)

    # Count tokens
    json_count = counter.count_tokens(json_output, "JSON")
    toon_count = counter.count_tokens(toon_output, "TOON")

    # Calculate reduction
    if json_count.token_count > 0:
        reduction = (1 - toon_count.token_count / json_count.token_count) * 100
    else:
        reduction = 0.0

    return json_count, toon_count, reduction


def print_benchmark_result(
    name: str,
    json_count: TokenCount,
    toon_count: TokenCount,
    reduction: float,
) -> None:
    """Print formatted benchmark result."""
    estimate_marker = " (est.)" if json_count.is_estimated else ""

    print(f"\n{'=' * 60}")
    print(f"Benchmark: {name}")
    print(f"{'=' * 60}")
    print(
        f"  JSON: {json_count.char_count:,} chars / {json_count.token_count:,} tokens{estimate_marker}"
    )
    print(
        f"  TOON: {toon_count.char_count:,} chars / {toon_count.token_count:,} tokens{estimate_marker}"
    )
    print(
        f"  Character reduction: {(1 - toon_count.char_count / json_count.char_count) * 100:.1f}%"
    )
    print(f"  Token reduction: {reduction:.1f}%")

    # Goal indicator
    if reduction >= 50:
        status = "✓ GOAL MET" if reduction >= 50 else "✗ BELOW GOAL"
        print(f"  Status: {status} (target: ≥50%)")


def main():
    """Run token reduction benchmarks."""
    print("=" * 60)
    print("TOON Token Reduction Benchmark")
    print("=" * 60)

    counter = TokenCounter()

    # Benchmark 1: Simple dictionary
    data1 = create_simple_dict()
    json1, toon1, red1 = run_benchmark(data1, "Simple Dictionary", counter)
    print_benchmark_result("Simple Dictionary", json1, toon1, red1)

    # Benchmark 2: Analysis result
    data2 = create_sample_analysis_result()
    json2, toon2, red2 = run_benchmark(data2, "Code Analysis Result", counter)
    print_benchmark_result("Code Analysis Result", json2, toon2, red2)

    # Benchmark 3: MCP response
    data3 = create_mcp_response()
    json3, toon3, red3 = run_benchmark(data3, "MCP Tool Response", counter)
    print_benchmark_result("MCP Tool Response", json3, toon3, red3)

    # Summary
    avg_reduction = (red1 + red2 + red3) / 3
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Average token reduction: {avg_reduction:.1f}%")
    print("  Target: 50-70%")

    if avg_reduction >= 50:
        print("  Result: ✓ TARGET ACHIEVED")
    else:
        print("  Result: ✗ Below target")

    # Show sample outputs
    print(f"\n{'=' * 60}")
    print("SAMPLE OUTPUT COMPARISON")
    print(f"{'=' * 60}")

    simple_data = {"name": "test", "count": 42, "active": True}
    print("\nInput data:")
    print(f"  {simple_data}")

    print("\nJSON output:")
    json_out = json.dumps(simple_data, indent=2)
    for line in json_out.split("\n"):
        print(f"  {line}")

    print("\nTOON output:")
    toon_out = ToonFormatter().format(simple_data)
    for line in toon_out.split("\n"):
        print(f"  {line}")

    print(f"\n{'=' * 60}")
    print("Benchmark complete!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
