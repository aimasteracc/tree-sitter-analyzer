#!/usr/bin/env python3
"""
Generate expected.json files for golden corpus tests.

This script parses corpus files using tree-sitter and generates
expected.json files with accurate node type counts.

Usage:
    python scripts/generate_expected_counts.py rust
    python scripts/generate_expected_counts.py php
    python scripts/generate_expected_counts.py kotlin
    python scripts/generate_expected_counts.py all
"""

import json
import sys
from collections import Counter
from pathlib import Path

import tree_sitter


def get_language_config(language: str) -> dict:
    """Get configuration for a language."""
    configs = {
        "rust": {
            "module": "tree_sitter_rust",
            "language_func": "language",
            "extension": "rs",
            "critical_nodes": [
                "function_item",
                "impl_item",
                "trait_item",
                "struct_item",
                "enum_item",
                "type_item",
                "let_declaration",
                "const_item",
                "static_item",
                "macro_invocation",
                "macro_definition",
                "attribute_item",
                "closure_expression",
                "match_expression",
                "mod_item",
                "use_declaration",
            ],
        },
        "php": {
            "module": "tree_sitter_php",
            "language_func": "language_php",
            "extension": "php",
            "critical_nodes": [
                "function_definition",
                "method_declaration",
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
                "property_declaration",
                "const_declaration",
                "namespace_definition",
                "namespace_use_declaration",
                "anonymous_function_creation_expression",
                "arrow_function",
                "enum_declaration",
            ],
        },
        "kotlin": {
            "module": "tree_sitter_kotlin",
            "language_func": "language",
            "extension": "kt",
            "critical_nodes": [
                "function_declaration",
                "anonymous_function",
                "class_declaration",
                "object_declaration",
                "companion_object",
                "property_declaration",
                "variable_declaration",
                "annotation",
                "type_alias",
                "lambda_literal",
                "when_expression",
                "interface_declaration",
            ],
        },
        "css": {
            "module": "tree_sitter_css",
            "language_func": "language",
            "extension": "css",
            "critical_nodes": [
                "rule_set",
                "at_rule",
                "media_statement",
                "import_statement",
                "keyframes_statement",
                "supports_statement",
                "charset_statement",
                "namespace_statement",
                "declaration",
                "selectors",
                "class_selector",
                "id_selector",
                "pseudo_class_selector",
                "pseudo_element_selector",
                "attribute_selector",
                "descendant_selector",
                "child_selector",
                "sibling_selector",
                "adjacent_sibling_selector",
                "keyframe_block",
                "keyframe_block_list",
                "feature_query",
                "binary_query",
                "unary_query",
                "keyword_query",
                "call_expression",
                "comment",
            ],
        },
        "html": {
            "module": "tree_sitter_html",
            "language_func": "language",
            "extension": "html",
            "critical_nodes": [
                "element",
                "self_closing_tag",
                "script_element",
                "style_element",
                "start_tag",
                "end_tag",
                "attribute",
                "attribute_name",
                "quoted_attribute_value",
                "doctype",
                "comment",
                "text",
                "entity",
                "raw_text",
                "erroneous_end_tag",
            ],
        },
        "markdown": {
            "module": "tree_sitter_markdown",
            "language_func": "language",
            "extension": "md",
            "critical_nodes": [
                "atx_heading",
                "setext_heading",
                "fenced_code_block",
                "indented_code_block",
                "paragraph",
                "block_quote",
                "list",
                "list_item",
                "pipe_table",
                "link_reference_definition",
                "thematic_break",
                "html_block",
                "task_list_marker_checked",
                "task_list_marker_unchecked",
                "info_string",
                "code_fence_content",
                "minus_metadata",
                "atx_h1_marker",
                "atx_h2_marker",
                "atx_h3_marker",
            ],
        },
    }
    return configs.get(language, {})  # type: ignore[return-value]


def parse_corpus_file(corpus_path: Path, language: str) -> dict[str, int]:
    """
    Parse corpus file and count node types.

    Args:
        corpus_path: Path to corpus file
        language: Language name

    Returns:
        Dictionary mapping node types to counts
    """
    config = get_language_config(language)
    if not config:
        raise ValueError(f"Unknown language: {language}")

    module_name = config["module"]
    language_func_name = config["language_func"]

    # Import the tree-sitter language module
    try:
        ts_module = __import__(module_name)
    except ImportError:
        print(f"Error: {module_name} not installed")
        print(f"Install it with: uv pip install {module_name.replace('_', '-')}")
        sys.exit(1)

    # Get the language function
    language_func = getattr(ts_module, language_func_name)

    # Parse the file
    lang = tree_sitter.Language(language_func())
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

    # Filter to only critical node types
    critical_nodes = config["critical_nodes"]
    filtered_counts = {
        node_type: count
        for node_type, count in all_counts.items()
        if node_type in critical_nodes and count > 0
    }

    print(f"\n{language.upper()} - Found {len(all_counts)} total node types")
    print(f"Critical node types with counts > 0: {len(filtered_counts)}")
    print("\nCritical node type counts:")
    for node_type in sorted(filtered_counts.keys()):
        print(f"  {node_type}: {filtered_counts[node_type]}")

    return filtered_counts


def generate_expected_json(language: str, golden_dir: Path) -> None:
    """
    Generate expected.json file for a language.

    Args:
        language: Language name
        golden_dir: Golden directory path
    """
    config = get_language_config(language)
    if not config:
        print(f"Error: Unknown language '{language}'")
        return

    ext = config["extension"]
    corpus_path = golden_dir / f"corpus_{language}.{ext}"
    expected_path = golden_dir / f"corpus_{language}_expected.json"

    if not corpus_path.exists():
        print(f"Error: Corpus file not found: {corpus_path}")
        return

    print(f"\nProcessing {language}...")
    print(f"Corpus file: {corpus_path}")

    # Parse and count
    node_counts = parse_corpus_file(corpus_path, language)

    # Create expected.json structure
    expected_data = {"language": language, "node_types": dict(sorted(node_counts.items()))}

    # Write expected.json
    with open(expected_path, "w", encoding="utf-8") as f:
        json.dump(expected_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Generated: {expected_path}")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_expected_counts.py <language>")
        print("Languages: rust, php, kotlin, css, html, markdown, all")
        sys.exit(1)

    language_arg = sys.argv[1].lower()
    golden_dir = Path(__file__).parent.parent / "tests" / "golden"

    if language_arg == "all":
        languages = ["rust", "php", "kotlin", "css", "html", "markdown"]
        for lang in languages:
            generate_expected_json(lang, golden_dir)
    else:
        generate_expected_json(language_arg, golden_dir)

    print("\nDone!")


if __name__ == "__main__":
    main()
