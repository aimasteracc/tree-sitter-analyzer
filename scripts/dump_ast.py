#!/usr/bin/env python3
"""
Dump the Tree-sitter AST for a given file.
Useful for debugging platform-specific parsing differences.
"""

import argparse
import sys
from pathlib import Path

try:
    import tree_sitter
    import tree_sitter_sql

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


def main():
    parser = argparse.ArgumentParser(description="Dump Tree-sitter AST")
    parser.add_argument("file_path", type=str, help="Path to the file to parse")
    args = parser.parse_args()

    if not TREE_SITTER_AVAILABLE:
        print("Error: tree-sitter or tree-sitter-sql not installed.")
        sys.exit(1)

    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    try:
        with open(file_path, "rb") as f:
            source_code = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    language = tree_sitter.Language(tree_sitter_sql.language())
    parser = tree_sitter.Parser(language)
    tree = parser.parse(source_code)

    # Print the S-expression
    # The string representation of the root node is the S-expression
    print(tree.root_node)


if __name__ == "__main__":
    main()
