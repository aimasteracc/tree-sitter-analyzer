#!/usr/bin/env python3
"""
Find duplicate test functions between unit/ and integration/ directories.

Uses AST extraction + difflib.SequenceMatcher to detect tests with >= 90% similarity.
"""

import ast
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def extract_test_functions(test_dir: Path) -> list[dict[str, Any]]:
    """Extract test function metadata from a directory."""
    results = []
    for test_file in sorted(test_dir.rglob("test_*.py")):
        try:
            source = test_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(test_file))
        except SyntaxError as e:
            print(f"Warning: Syntax error in {test_file}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"Warning: Error reading {test_file}: {e}", file=sys.stderr)
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                # Extract assertion bodies as text for comparison
                assertions = []
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Assert):
                        assertions.append(ast.unparse(stmt))

                # Get function body as text (simplified)
                try:
                    body_text = ast.unparse(node)
                except Exception:
                    body_text = node.name

                results.append(
                    {
                        "file": str(test_file.relative_to(test_dir.parent.parent)),
                        "function": node.name,
                        "assertions": assertions,
                        "body_text": body_text,
                        "num_assertions": len(assertions),
                    }
                )

    return results


def compute_similarity(a: dict, b: dict) -> float:
    """Compute similarity between two test functions."""
    # Compare body text
    body_sim = SequenceMatcher(None, a["body_text"], b["body_text"]).ratio()

    # Compare assertions
    a_assertions = "\n".join(a["assertions"])
    b_assertions = "\n".join(b["assertions"])
    if a_assertions or b_assertions:
        assert_sim = SequenceMatcher(None, a_assertions, b_assertions).ratio()
    else:
        assert_sim = 1.0 if not a_assertions and not b_assertions else 0.0

    # Weighted average: body similarity 60%, assertion similarity 40%
    return 0.6 * body_sim + 0.4 * assert_sim


def find_duplicate_pairs(
    unit_tests: list[dict],
    integration_tests: list[dict],
    threshold: float = 0.90,
) -> list[dict]:
    """Find test pairs with similarity >= threshold."""
    pairs = []

    # Index integration tests by function name for fast lookup
    integration_by_name: dict[str, list[dict]] = {}
    for t in integration_tests:
        integration_by_name.setdefault(t["function"], []).append(t)

    for unit_test in unit_tests:
        # First check name matches (most likely duplicates)
        name_matches = integration_by_name.get(unit_test["function"], [])

        for int_test in name_matches:
            sim = compute_similarity(unit_test, int_test)
            if sim >= threshold:
                pairs.append(
                    {
                        "unit": f"{unit_test['file']}::{unit_test['function']}",
                        "integration": f"{int_test['file']}::{int_test['function']}",
                        "similarity": round(sim, 3),
                    }
                )

    return sorted(pairs, key=lambda x: x["similarity"], reverse=True)


def main() -> None:
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    tests_root = project_root / "tests"

    unit_dir = tests_root / "unit"
    integration_dir = tests_root / "integration"

    if not unit_dir.exists():
        print(f"Error: {unit_dir} not found", file=sys.stderr)
        sys.exit(1)
    if not integration_dir.exists():
        print(f"Error: {integration_dir} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting unit tests from {unit_dir}...")
    unit_tests = extract_test_functions(unit_dir)
    print(f"  Found {len(unit_tests)} unit test functions")

    print(f"Extracting integration tests from {integration_dir}...")
    integration_tests = extract_test_functions(integration_dir)
    print(f"  Found {len(integration_tests)} integration test functions")

    print("Finding duplicate pairs (similarity >= 90%)...")
    pairs = find_duplicate_pairs(unit_tests, integration_tests, threshold=0.90)
    print(f"  Found {len(pairs)} duplicate pairs")

    output_path = project_root / "reports" / "duplicate-test-pairs.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(pairs, indent=2))
    print(f"Written to {output_path}")

    if pairs:
        print("\nTop duplicate pairs:")
        for pair in pairs[:10]:
            print(
                f"  [{pair['similarity']:.1%}] {pair['unit']} <-> {pair['integration']}"
            )


if __name__ == "__main__":
    main()
