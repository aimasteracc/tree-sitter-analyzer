#!/usr/bin/env python3
"""
Test Generation CLI Command

Generates pytest test skeletons from Python functions:
- Extracts function information using tree-sitter
- Generates test cases (happy path, edge cases, exceptions)
- Renders pytest-compatible Python code
- Writes test files to disk with syntax validation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ...output_manager import output_data, output_error, output_info, set_output_mode
from ...test_gen.generator import TestGenerationEngine
from ...test_gen.renderer import render_test_file_to_path


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for test generation CLI."""
    parser = argparse.ArgumentParser(
        description="Generate pytest test skeletons from Python functions.",
        epilog="""
Examples:
  # Generate tests for a single file
  %(prog)s mymodule.py

  # Generate tests with custom output path
  %(prog)s mymodule.py --output tests/test_mymodule.py

  # Generate tests for multiple files
  %(prog)s file1.py file2.py

  # Generate tests in verbose mode
  %(prog)s mymodule.py --verbose

  # Dry run: show what would be generated without writing files
  %(prog)s mymodule.py --dry-run
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "files",
        nargs="+",
        help="Python file(s) to generate tests for",
    )

    parser.add_argument(
        "--output", "-o",
        help="Output file path (for single file input)",
    )

    parser.add_argument(
        "--output-dir",
        help="Output directory for test files (for multiple files)",
    )

    parser.add_argument(
        "--module-path",
        help="Module path for import generation (e.g., 'src.auth.auth')",
    )

    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory (default: current directory)",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without writing files",
    )

    return parser


def generate_tests_for_file(
    file_path: str,
    output_path: str | None,
    module_path: str | None,
    project_root: str,
    verbose: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Generate tests for a single Python file.

    Args:
        file_path: Path to the Python file
        output_path: Optional output file path
        module_path: Optional module path for imports
        project_root: Project root directory
        verbose: Enable verbose output
        dry_run: Show what would be generated without writing

    Returns:
        True if successful, False otherwise
    """
    try:
        if verbose:
            output_info(f"Analyzing {file_path}...")

        # Initialize test generation engine
        engine = TestGenerationEngine(project_root)

        # Extract functions
        func_infos = engine.extract_functions(file_path)

        if not func_infos:
            output_error(f"No functions found in {file_path}")
            return False

        if verbose:
            output_info(f"Found {len(func_infos)} function(s)")

        # Generate test cases
        test_cases: dict[str, list[Any]] = {}
        for func_info in func_infos:
            cases = engine.generate_test_cases(func_info)
            test_cases[func_info.name] = cases
            if verbose:
                output_info(f"  {func_info.name}: {len(cases)} test(s)")

        # Determine output path
        if not output_path:
            file_path_obj = Path(file_path)
            output_path = f"test_{file_path_obj.stem}.py"

        # Determine module path
        if not module_path:
            module_path = engine.get_module_path(file_path)

        # Render test file
        if dry_run:
            output_info(f"Would generate: {output_path}")
            from ...test_gen.renderer import PytestRenderer
            renderer = PytestRenderer(module_path)
            content = renderer.render_test_file(func_infos, test_cases)
            output_data(content)
            return True

        # Write test file
        render_test_file_to_path(func_infos, test_cases, module_path, output_path)

        if verbose:
            output_info(f"Generated {output_path}")

        return True

    except Exception as e:
        output_error(f"Failed to generate tests for {file_path}: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def main() -> int:
    """Main entry point for test generation CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    # Set output mode
    set_output_mode(quiet=False, json_output=False)

    # Validate inputs
    for file_path in args.files:
        if not Path(file_path).exists():
            output_error(f"File not found: {file_path}")
            return 1
        if not file_path.endswith(".py"):
            output_error(f"not a Python file: {file_path}")
            return 1

    # Handle multiple files
    if len(args.files) > 1:
        if args.output:
            output_error("--output can only be used with a single input file")
            return 1

        output_dir = args.output_dir or "tests"
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        success_count = 0
        for file_path in args.files:
            file_path_obj = Path(file_path)
            output_path = f"{output_dir}/test_{file_path_obj.stem}.py"

            if generate_tests_for_file(
                file_path=file_path,
                output_path=output_path,
                module_path=args.module_path,
                project_root=args.project_root,
                verbose=args.verbose,
                dry_run=args.dry_run,
            ):
                success_count += 1

        output_info(f"Generated tests for {success_count}/{len(args.files)} file(s)")
        return 0 if success_count == len(args.files) else 1

    # Handle single file
    if generate_tests_for_file(
        file_path=args.files[0],
        output_path=args.output,
        module_path=args.module_path,
        project_root=args.project_root,
        verbose=args.verbose,
        dry_run=args.dry_run,
    ):
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
