#!/usr/bin/env python3
"""Diagnose Python plugin coverage gaps - sync version"""
from tree_sitter_analyzer.grammar_coverage.validator import (
    validate_plugin_coverage_sync,
)


def main():
    print("Running Python plugin coverage validation...\n")
    report = validate_plugin_coverage_sync("python")

    print(f"Total node types: {report.total_node_types}")
    print(f"Covered: {report.covered_node_types} ({report.coverage_percentage:.1f}%)")
    print(f"\nUncovered types ({len(report.uncovered_types)}):")
    for t in sorted(report.uncovered_types):
        print(f"  - {t}")

    # Categorize uncovered types
    print("\n=== Analysis ===")

    expressions = ["conditional_expression", "subscript", "list"]
    comprehensions = ["list_comprehension", "set_comprehension",
                     "dictionary_comprehension", "generator_expression",
                     "for_in_clause", "if_clause"]
    lambdas = ["lambda", "lambda_parameters"]
    params = ["default_parameter"]

    uncovered_set = set(report.uncovered_types)

    print("\nExpressions (not extracted):")
    for t in sorted(uncovered_set & set(expressions)):
        print(f"  - {t}")

    print("\nComprehensions (not extracted):")
    for t in sorted(uncovered_set & set(comprehensions)):
        print(f"  - {t}")

    print("\nLambdas (not extracted):")
    for t in sorted(uncovered_set & set(lambdas)):
        print(f"  - {t}")

    print("\nParameter types (visited but not tracked):")
    for t in sorted(uncovered_set & set(params)):
        print(f"  - {t}")

if __name__ == "__main__":
    main()
