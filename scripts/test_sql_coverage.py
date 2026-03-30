#!/usr/bin/env python3
"""Test script to identify SQL node types in corpus and verify coverage."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tree_sitter_analyzer.language_loader import create_parser_safely
import tree_sitter


def collect_node_types(node: "tree_sitter.Node", types_dict: dict[str, int]) -> None:
    """Recursively collect all node types and their counts."""
    types_dict[node.type] = types_dict.get(node.type, 0) + 1
    for child in node.children:
        collect_node_types(child, types_dict)


def main():
    # Read corpus file
    corpus_path = Path(__file__).parent.parent / "tests" / "golden" / "corpus_sql.sql"
    with open(corpus_path, encoding="utf-8") as f:
        source_code = f.read()

    # Create parser
    parser = create_parser_safely('sql')
    if not parser:
        print('Failed to create SQL parser')
        return 1

    tree = parser.parse(source_code.encode('utf-8'))

    # Collect node types
    node_types = {}
    collect_node_types(tree.root_node, node_types)

    print(f"Total unique node types in corpus: {len(node_types)}")
    print("\nNode types (sorted by frequency):")
    for node_type, count in sorted(node_types.items(), key=lambda x: -x[1]):
        print(f"  {node_type:40s} {count:5d}")

    # Check coverage
    from tree_sitter_analyzer.grammar_coverage.validator import validate_plugin_coverage_sync
    result = validate_plugin_coverage_sync('sql')

    print(f"\n{'='*70}")
    print(f"Coverage: {result.covered_node_types}/{result.total_node_types} ({result.coverage_percentage:.1f}%)")
    print(f"{'='*70}")

    if result.uncovered_types:
        print(f"\nUncovered ({len(result.uncovered_types)} node types):")
        for node_type in sorted(result.uncovered_types):
            count = node_types.get(node_type, 0)
            print(f"  {node_type:40s} {count:5d} occurrences")

    return 0


if __name__ == "__main__":
    sys.exit(main())
