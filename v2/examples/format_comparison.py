#!/usr/bin/env python3
"""
Output format comparison example.

Shows the difference between TOON, Markdown, and Summary formats.

Usage:
    cd v2
    uv run python examples/format_comparison.py
"""

from tree_sitter_analyzer_v2.formatters import get_default_registry
from tree_sitter_analyzer_v2.languages.python_parser import PythonParser

SAMPLE_CODE = '''
import os
from pathlib import Path

class FileManager:
    """Manages file operations."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def list_files(self, pattern: str = "*") -> list[str]:
        """List files matching pattern."""
        return [str(p) for p in self.root.glob(pattern)]

    def read_file(self, name: str) -> str:
        """Read file contents."""
        return (self.root / name).read_text()

    @staticmethod
    def exists(path: str) -> bool:
        """Check if path exists."""
        return os.path.exists(path)


def get_home() -> Path:
    """Get user home directory."""
    return Path.home()
'''


def main() -> None:
    """Compare output formats side by side."""
    parser = PythonParser()
    result = parser.parse(SAMPLE_CODE, "example.py")
    result["language"] = "python"
    result["file_path"] = "example.py"

    # Add metadata for summary formatter
    lines = SAMPLE_CODE.splitlines()
    result["metadata"] = {
        "total_lines": len(lines),
        "code_lines": sum(1 for l in lines if l.strip() and not l.strip().startswith("#")),
        "comment_lines": sum(1 for l in lines if l.strip().startswith("#")),
        "blank_lines": sum(1 for l in lines if not l.strip()),
    }

    registry = get_default_registry()

    for format_name in ["toon", "markdown", "summary"]:
        formatter = registry.get(format_name)
        output = formatter.format(result)
        tokens_approx = len(output.split())

        print(f"\n{'=' * 60}")
        print(f"FORMAT: {format_name.upper()} (~{tokens_approx} tokens)")
        print("=" * 60)
        print(output)

    print("\n" + "=" * 60)
    print("TOON format uses 50-70% fewer tokens than Markdown!")


if __name__ == "__main__":
    main()
