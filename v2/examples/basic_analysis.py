#!/usr/bin/env python3
"""
Basic code analysis example.

Demonstrates how to use tree-sitter-analyzer v2 to analyze Python code.

Usage:
    cd v2
    uv run python examples/basic_analysis.py
"""

from pathlib import Path

from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI


def main() -> None:
    """Run basic analysis on a sample Python file."""
    project_root = Path(__file__).parent.parent
    api = TreeSitterAnalyzerAPI()

    # Analyze a Python file - raw (structured) output
    sample_file = str(project_root / "tests" / "fixtures" / "analyze_fixtures" / "sample.py")
    print(f"Analyzing: {sample_file}")
    print("=" * 60)

    try:
        data = api.analyze_file_raw(sample_file)
    except Exception as e:
        print(f"Error: {e}")
        return

    # Show classes
    classes = data.get("classes", [])
    print(f"\nClasses found: {len(classes)}")
    for cls in classes:
        name = cls.get("name", "unknown")
        methods = cls.get("methods", [])
        print(f"  - {name} ({len(methods)} methods)")
        for method in methods:
            mname = method.get("name", "unknown")
            ret = method.get("return_type", "")
            ret_str = f" -> {ret}" if ret else ""
            print(f"      .{mname}(){ret_str}")

    # Show top-level functions
    functions = data.get("functions", [])
    print(f"\nFunctions found: {len(functions)}")
    for func in functions:
        name = func.get("name", "unknown")
        ret = func.get("return_type", "")
        ret_str = f" -> {ret}" if ret else ""
        print(f"  - {name}(){ret_str}")

    # Show imports
    imports = data.get("imports", [])
    print(f"\nImports found: {len(imports)}")
    for imp in imports:
        if isinstance(imp, dict):
            mod = imp.get("module", "")
            names = imp.get("names", [])
            if names:
                print(f"  - from {mod} import {', '.join(names)}")
            else:
                print(f"  - import {mod}")
        else:
            print(f"  - {imp}")

    # Show formatted output (TOON)
    print("\n" + "=" * 60)
    print("TOON Formatted Output:")
    print("=" * 60)
    formatted = api.analyze_file(sample_file, output_format="toon")
    if formatted.get("success"):
        print(formatted["data"])

    print("\n" + "=" * 60)
    print("Analysis complete!")


if __name__ == "__main__":
    main()
