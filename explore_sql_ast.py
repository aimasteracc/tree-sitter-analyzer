#!/usr/bin/env python3
"""
Explore SQL AST using tree-sitter

This script parses a given SQL file and prints its Abstract Syntax Tree (AST)
to the console, showing the structure and node types. This is useful for
developing and debugging language plugins.
"""

import sys
from pathlib import Path

try:
    import tree_sitter_sql
    from tree_sitter import Language, Parser
except ImportError:
    print("Error: tree-sitter or tree-sitter-sql not available")
    print("Install with: pip install tree-sitter tree-sitter-sql")
    sys.exit(1)


def print_ast_node(node, indent=0, max_depth=10):
    """
    Print AST node information with indentation.

    Args:
        node: Tree-sitter node
        indent: Current indentation level
        max_depth: Maximum depth to traverse (prevent infinite recursion)
    """
    if indent > max_depth:
        print("  " * indent + "... (max depth reached)")
        return

    # Get node text (truncate if too long)
    node_text = node.text.decode("utf-8") if node.text else ""
    if len(node_text) > 100:
        node_text = node_text[:97] + "..."

    # Replace newlines with \n for readability
    node_text = node_text.replace("\n", "\\n").replace("\r", "\\r")

    # Print node information
    print(
        f"{'  ' * indent}{node.type} [{node.start_point[0]}:{node.start_point[1]}-{node.end_point[0]}:{node.end_point[1]}]"
    )
    if node_text.strip():
        print(f"{'  ' * indent}  Text: '{node_text}'")

    # Recursively print children
    for child in node.children:
        print_ast_node(child, indent + 1, max_depth)


def analyze_sql_file(file_path):
    """
    Analyze SQL file and print its AST structure.

    Args:
        file_path: Path to SQL file
    """
    print(f"Analyzing SQL file: {file_path}")
    print("=" * 80)

    # Read file content
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    print(f"File content ({len(content)} characters):")
    print("-" * 40)
    print(content[:500] + ("..." if len(content) > 500 else ""))
    print("-" * 40)
    print()

    # Set up parser
    try:
        language = Language(tree_sitter_sql.language())
        parser = Parser()

        # Try different ways to set language (API varies by version)
        if hasattr(parser, "set_language"):
            parser.set_language(language)
        elif hasattr(parser, "language"):
            parser.language = language
        else:
            # Try creating parser with language directly
            parser = Parser(language)

    except Exception as e:
        print(f"Error setting up parser: {e}")
        print(
            f"Available parser methods: {[m for m in dir(parser) if not m.startswith('_')]}"
        )
        return

    # Parse content
    try:
        tree = parser.parse(content.encode("utf-8"))
        if tree is None or tree.root_node is None:
            print("Error: Failed to parse SQL content")
            return
    except Exception as e:
        print(f"Error parsing content: {e}")
        return

    print("AST Structure:")
    print("=" * 80)
    print_ast_node(tree.root_node)
    print("=" * 80)

    # Print summary of top-level nodes
    print("\nTop-level node types:")
    for child in tree.root_node.children:
        if child.type != "comment":  # Skip comments for clarity
            print(f"  - {child.type}")


def main():
    """Main function"""
    # Default to sample_database.sql
    sql_file = "examples/sample_database.sql"

    if len(sys.argv) > 1:
        sql_file = sys.argv[1]

    if not Path(sql_file).exists():
        print(f"Error: File '{sql_file}' not found")
        sys.exit(1)

    analyze_sql_file(sql_file)


if __name__ == "__main__":
    main()
