#!/usr/bin/env python3
"""
Extract node type counts from corpus files using tree-sitter.

This script parses a source file and counts all named node types.
"""

import sys
import json
from pathlib import Path
from collections import Counter
import tree_sitter


def extract_node_counts(filepath: Path, language: str) -> dict[str, int]:
    """
    Extract node type counts from a file.

    Args:
        filepath: Path to source file
        language: Language name

    Returns:
        Dictionary mapping node types to counts
    """
    # Import language-specific tree-sitter module
    language_modules = {
        "python": "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "java": "tree_sitter_java",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "go": "tree_sitter_go",
        "ruby": "tree_sitter_ruby",
        "rust": "tree_sitter_rust",
        "php": "tree_sitter_php",
        "kotlin": "tree_sitter_kotlin",
        "swift": "tree_sitter_swift",
        "scala": "tree_sitter_scala",
        "bash": "tree_sitter_bash",
        "yaml": "tree_sitter_yaml",
        "json": "tree_sitter_json",
        "sql": "tree_sitter_sql",
    }

    module_name = language_modules.get(language)
    if not module_name:
        raise ValueError(f"No tree-sitter module for language: {language}")

    try:
        ts_module = __import__(module_name)
    except ImportError:
        raise ImportError(
            f"Tree-sitter module not available: {module_name}. "
            f"Install it with: uv pip install {module_name.replace('_', '-')}"
        ) from None

    # Parse the file
    lang = tree_sitter.Language(ts_module.language())
    parser = tree_sitter.Parser(lang)
    source_code = filepath.read_text(encoding="utf-8")
    tree = parser.parse(source_code.encode("utf-8"))

    # Count node types recursively
    def count_nodes(node: tree_sitter.Node) -> Counter[str]:
        counts: Counter[str] = Counter()
        if node.is_named:
            counts[node.type] += 1
        for child in node.children:
            counts.update(count_nodes(child))
        return counts

    actual_counts = count_nodes(tree.root_node)
    return dict(actual_counts)


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: python extract_node_counts.py <filepath> <language>")
        print("Example: python extract_node_counts.py corpus_cpp.cpp cpp")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    language = sys.argv[2]

    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    # Extract counts
    counts = extract_node_counts(filepath, language)

    # Sort by count (descending) then by name
    sorted_counts = dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))

    # Print all node types
    print(f"\n{'Node Type':<50} {'Count':>10}")
    print("=" * 62)
    for node_type, count in sorted_counts.items():
        print(f"{node_type:<50} {count:>10}")

    print("\n" + "=" * 62)
    print(f"{'Total unique node types:':<50} {len(sorted_counts):>10}")
    print(f"{'Total nodes:':<50} {sum(sorted_counts.values()):>10}")


if __name__ == "__main__":
    main()
