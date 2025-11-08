#!/usr/bin/env python3
"""
Test SQL element extraction with our modified code
"""

import sys
from pathlib import Path

try:
    import tree_sitter_sql  # noqa: F401
    from tree_sitter import Language, Parser  # noqa: F401
except ImportError:
    print("Error: tree-sitter or tree-sitter-sql not available")
    sys.exit(1)

from tree_sitter_analyzer.languages.sql_plugin import SQLPlugin


def test_sql_extraction():
    """Test SQL element extraction"""

    # Read the sample SQL file
    sql_file = "examples/sample_database.sql"
    if not Path(sql_file).exists():
        print(f"Error: File '{sql_file}' not found")
        return

    with open(sql_file, encoding="utf-8") as f:
        content = f.read()

    print(f"Testing SQL extraction on {sql_file}")
    print("=" * 60)

    # Create plugin and test extraction
    plugin = SQLPlugin()

    # Set up parser
    try:
        language = plugin.get_tree_sitter_language()
        if language is None:
            print("Error: Could not load tree-sitter-sql language")
            return

        parser = Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(language)
        elif hasattr(parser, "language"):
            parser.language = language
        else:
            parser = Parser(language)

    except Exception as e:
        print(f"Error setting up parser: {e}")
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

    # Extract elements
    try:
        elements = plugin.extract_elements(tree, content)

        print("Extraction Results:")
        print(f"- Tables/Views (classes): {len(elements['classes'])}")
        for cls in elements["classes"]:
            print(f"  * {cls.name} (lines {cls.start_line}-{cls.end_line})")

        print(f"- Functions/Procedures/Triggers: {len(elements['functions'])}")
        for func in elements["functions"]:
            print(f"  * {func.name} (lines {func.start_line}-{func.end_line})")

        print(f"- Indexes (variables): {len(elements['variables'])}")
        for var in elements["variables"]:
            print(f"  * {var.name} (lines {var.start_line}-{var.end_line})")

        print(f"- Schema references (imports): {len(elements['imports'])}")
        for imp in elements["imports"]:
            print(f"  * {imp.name} (lines {imp.start_line}-{imp.end_line})")

    except Exception as e:
        print(f"Error during extraction: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_sql_extraction()
