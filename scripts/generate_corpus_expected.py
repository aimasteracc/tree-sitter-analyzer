#!/usr/bin/env python3
"""
Generate expected.json files for golden corpus files.

This script parses corpus files using tree-sitter and generates
expected.json files with accurate node type counts.

Usage:
    python scripts/generate_corpus_expected.py swift
    python scripts/generate_corpus_expected.py scala
    python scripts/generate_corpus_expected.py bash
    python scripts/generate_corpus_expected.py --all
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import tree_sitter


def get_language_config(language: str) -> dict[str, Any]:
    """Get language configuration (module name and critical node types)."""
    configs = {
        "swift": {
            "module": "tree_sitter_swift",
            "extension": "swift",
            "critical_types": [
                "function_declaration",
                "computed_property",
                "subscript_declaration",
                "class_declaration",
                "struct_declaration",
                "protocol_declaration",
                "property_declaration",
                "typealias_declaration",
                "import_declaration",
                "extension_declaration",
                "closure_expression",
                "do_statement",
                "enum_declaration",
                "init_declaration",
                "deinit_declaration",
                "actor_declaration",
            ],
        },
        "scala": {
            "module": "tree_sitter_scala",
            "extension": "scala",
            "critical_types": [
                "function_definition",
                "function_declaration",
                "class_definition",
                "object_definition",
                "trait_definition",
                "val_definition",
                "var_definition",
                "type_definition",
                "import_declaration",
                "package_clause",
                "lambda_expression",
                "case_clause",
                "case_class_definition",
            ],
        },
        "bash": {
            "module": "tree_sitter_bash",
            "extension": "sh",
            "critical_types": [
                "function_definition",
                "command",
                "variable_assignment",
                "declaration_command",
                "if_statement",
                "while_statement",
                "for_statement",
                "case_statement",
                "pipeline",
                "redirected_statement",
                "command_substitution",
                "process_substitution",
            ],
        },
    }
    return configs[language]


def count_node_types(corpus_path: Path, language: str) -> dict[str, int]:
    """
    Count node types in corpus file using tree-sitter.

    Args:
        corpus_path: Path to corpus file
        language: Language name

    Returns:
        Dictionary mapping node types to counts
    """
    config = get_language_config(language)
    module_name = config["module"]

    # Import tree-sitter language module
    try:
        ts_module = __import__(module_name)
    except ImportError as e:
        print(f"Error: {module_name} not installed: {e}", file=sys.stderr)
        print(
            f"Install with: uv pip install {module_name.replace('_', '-')}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Parse the file
    lang = tree_sitter.Language(ts_module.language())
    parser = tree_sitter.Parser(lang)
    source_code = corpus_path.read_text(encoding="utf-8")
    tree = parser.parse(source_code.encode("utf-8"))

    # Count node types recursively
    def count_nodes(node: tree_sitter.Node) -> Counter[str]:
        counts: Counter[str] = Counter()
        if node.is_named:
            counts[node.type] += 1
        for child in node.children:
            counts.update(count_nodes(child))
        return counts

    all_counts = count_nodes(tree.root_node)
    return dict(all_counts)


def filter_critical_types(
    all_counts: dict[str, int], critical_types: list[str]
) -> dict[str, int]:
    """
    Filter node counts to only include critical types.

    Args:
        all_counts: All node type counts
        critical_types: List of critical node types to include

    Returns:
        Filtered counts containing only critical types
    """
    return {
        node_type: count
        for node_type, count in all_counts.items()
        if node_type in critical_types
    }


def generate_expected_json(language: str) -> None:
    """
    Generate expected.json for a language's corpus file.

    Args:
        language: Language name
    """
    config = get_language_config(language)
    ext = config["extension"]
    critical_types = config["critical_types"]

    # Paths
    golden_dir = Path(__file__).parent.parent / "tests" / "golden"
    corpus_path = golden_dir / f"corpus_{language}.{ext}"
    expected_path = golden_dir / f"corpus_{language}_expected.json"

    # Check corpus file exists
    if not corpus_path.exists():
        print(f"Error: Corpus file not found: {corpus_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {corpus_path}...")

    # Count node types
    all_counts = count_node_types(corpus_path, language)
    print(f"Found {len(all_counts)} unique node types")

    # Filter to critical types only
    critical_counts = filter_critical_types(all_counts, critical_types)
    print(f"Selected {len(critical_counts)} critical node types")

    # Show counts
    print("\nCritical node type counts:")
    for node_type in sorted(critical_counts.keys()):
        print(f"  {node_type}: {critical_counts[node_type]}")

    # Generate expected.json
    expected_data = {"language": language, "node_types": critical_counts}

    # Write to file
    with open(expected_path, "w", encoding="utf-8") as f:
        json.dump(expected_data, f, indent=2)
        f.write("\n")

    print(f"\nGenerated: {expected_path}")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_corpus_expected.py <language>")
        print("       python scripts/generate_corpus_expected.py --all")
        print("\nSupported languages: swift, scala, bash")
        sys.exit(1)

    arg = sys.argv[1].lower()

    if arg == "--all":
        for language in ["swift", "scala", "bash"]:
            print(f"\n{'=' * 60}")
            print(f"Generating expected.json for {language.upper()}")
            print("=" * 60)
            generate_expected_json(language)
    else:
        language = arg
        if language not in ["swift", "scala", "bash"]:
            print(f"Error: Unsupported language: {language}", file=sys.stderr)
            print("Supported languages: swift, scala, bash", file=sys.stderr)
            sys.exit(1)
        generate_expected_json(language)


if __name__ == "__main__":
    main()
