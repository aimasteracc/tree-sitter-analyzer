#!/usr/bin/env python3
"""
Find over-split test groups: test classes/modules where each function tests
only 1 behavior but all share the same fixture setup code.

Detection criteria:
- Same class / file group with identical fixture setup
- Each function <= 2 assertions
- Total functions in group >= 5
"""

import ast
import json
import sys
from pathlib import Path
from typing import Any


def _extract_setup_code(class_node: ast.ClassDef) -> str | None:
    """Extract setUp/setup_method/fixture code from a test class."""
    for node in ast.walk(class_node):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "setUp",
            "setup_method",
            "setup",
            "setup_class",
        ):
            try:
                return ast.unparse(node)
            except Exception:
                return None
    return None


def _count_assertions(func_node: ast.FunctionDef) -> int:
    """Count assert statements in a function."""
    return sum(1 for n in ast.walk(func_node) if isinstance(n, ast.Assert))


def find_oversplit_in_class(
    class_node: ast.ClassDef,
    file_path: str,
    min_functions: int = 5,
    max_assertions: int = 2,
) -> dict[str, Any] | None:
    """Check if a test class is over-split."""
    test_functions = [
        n
        for n in class_node.body
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]

    if len(test_functions) < min_functions:
        return None

    # Check if each test function has <= max_assertions
    oversplit_funcs = []
    for func in test_functions:
        assertion_count = _count_assertions(func)
        if assertion_count <= max_assertions:
            oversplit_funcs.append(
                {
                    "name": func.name,
                    "line": func.lineno,
                    "assertions": assertion_count,
                }
            )

    # If 80%+ of functions are <= max_assertions, it's over-split
    ratio = len(oversplit_funcs) / len(test_functions) if test_functions else 0
    if ratio < 0.8:
        return None

    setup_code = _extract_setup_code(class_node)

    return {
        "file": file_path,
        "class": class_node.name,
        "total_functions": len(test_functions),
        "oversplit_functions": len(oversplit_funcs),
        "oversplit_ratio": round(ratio, 2),
        "has_shared_setup": setup_code is not None,
        "functions": oversplit_funcs,
    }


def find_oversplit_module_level(
    module_tree: ast.Module,
    file_path: str,
    min_functions: int = 5,
    max_assertions: int = 2,
) -> dict[str, Any] | None:
    """Check for over-split test functions at module level (not in a class)."""
    # Only check top-level functions (directly in module body, not inside classes)
    top_level_tests = [
        n
        for n in module_tree.body
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]

    if len(top_level_tests) < min_functions:
        return None

    oversplit_funcs = []
    for func in top_level_tests:
        assertion_count = _count_assertions(func)
        if assertion_count <= max_assertions:
            oversplit_funcs.append(
                {
                    "name": func.name,
                    "line": func.lineno,
                    "assertions": assertion_count,
                }
            )

    ratio = len(oversplit_funcs) / len(top_level_tests) if top_level_tests else 0
    if ratio < 0.8:
        return None

    # Check for shared fixture (conftest or same fixture names used)
    fixture_names = set()
    for func in top_level_tests:
        for arg in func.args.args:
            fixture_names.add(arg.arg)

    return {
        "file": file_path,
        "class": None,
        "total_functions": len(top_level_tests),
        "oversplit_functions": len(oversplit_funcs),
        "oversplit_ratio": round(ratio, 2),
        "has_shared_setup": len(fixture_names) > 0,
        "shared_fixtures": list(fixture_names),
        "functions": oversplit_funcs,
    }


def find_oversplit_tests(
    tests_root: Path,
    min_functions: int = 5,
    max_assertions: int = 2,
) -> list[dict[str, Any]]:
    """Find all over-split test groups in the test suite."""
    candidates = []

    for test_file in sorted(tests_root.rglob("test_*.py")):
        try:
            source = test_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(test_file))
        except SyntaxError as e:
            print(f"Warning: Syntax error in {test_file}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"Warning: Error processing {test_file}: {e}", file=sys.stderr)
            continue

        file_path = str(test_file.relative_to(tests_root.parent))

        # Check class-level over-splitting
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                result = find_oversplit_in_class(
                    node, file_path, min_functions, max_assertions
                )
                if result:
                    candidates.append(result)

        # Check module-level over-splitting
        module_result = find_oversplit_module_level(
            tree, file_path, min_functions, max_assertions
        )
        if module_result:
            candidates.append(module_result)

    return sorted(candidates, key=lambda x: x["total_functions"], reverse=True)


def main() -> None:
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    tests_root = project_root / "tests"

    if not tests_root.exists():
        print(f"Error: {tests_root} not found", file=sys.stderr)
        sys.exit(1)

    min_functions = 5
    max_assertions = 2

    print(
        f"Scanning for over-split tests (>= {min_functions} functions, <= {max_assertions} assertions each)..."
    )
    candidates = find_oversplit_tests(tests_root, min_functions, max_assertions)
    print(f"  Found {len(candidates)} over-split candidates")

    output_path = project_root / "reports" / "oversplit-candidates.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(candidates, indent=2))
    print(f"Written to {output_path}")

    if candidates:
        print("\nTop over-split candidates:")
        for c in candidates[:10]:
            class_info = f" (class {c['class']})" if c["class"] else ""
            print(
                f"  {c['file']}{class_info}: {c['total_functions']} functions, {c['oversplit_ratio']:.0%} oversplit"
            )

    # Check if test_scala_fixes is included
    scala_hits = [c for c in candidates if "test_scala_fixes" in c["file"]]
    if scala_hits:
        print(
            f"\ntest_scala_fixes.py: FOUND in candidates ({scala_hits[0]['total_functions']} functions)"
        )
    else:
        print("\ntest_scala_fixes.py: NOT in candidates (may have different structure)")


if __name__ == "__main__":
    main()
