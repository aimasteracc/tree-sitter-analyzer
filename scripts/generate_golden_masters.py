#!/usr/bin/env python3
"""
Golden Master Generation Script

新しい言語のゴールデンマスターファイルを自動生成するスクリプト。

Usage:
    python scripts/generate_golden_masters.py <language> <sample_file>

Example:
    python scripts/generate_golden_masters.py csharp examples/Sample.cs
    python scripts/generate_golden_masters.py java examples/Sample.java
"""

import argparse
import subprocess  # nosec B404
import sys
from pathlib import Path


def run_analyzer(input_file: str, table_format: str) -> str:
    """Run tree-sitter-analyzer and return output"""
    cmd = ["uv", "run", "tree-sitter-analyzer", input_file, "--table", table_format]

    result = subprocess.run(  # nosec B603
        cmd, capture_output=True, text=True, encoding="utf-8", check=True
    )

    return result.stdout


def generate_golden_master(
    language: str, sample_file: str, output_base_name: str | None = None
) -> dict[str, Path]:
    """
    Generate golden master files for a language

    Args:
        language: Language name (e.g., 'csharp', 'java')
        sample_file: Path to sample file (e.g., 'examples/Sample.cs')
        output_base_name: Base name for output files (default: {language}_sample)

    Returns:
        Dictionary of format -> output file path
    """
    if output_base_name is None:
        output_base_name = f"{language}_sample"

    # Verify sample file exists
    sample_path = Path(sample_file)
    if not sample_path.exists():
        raise FileNotFoundError(f"Sample file not found: {sample_file}")

    # Create golden_masters directories if they don't exist
    base_dir = Path("tests/golden_masters")
    full_dir = base_dir / "full"
    compact_dir = base_dir / "compact"
    csv_dir = base_dir / "csv"

    for dir_path in [full_dir, compact_dir, csv_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    # Generate golden masters
    formats = {
        "full": (full_dir / f"{output_base_name}_full.md", "md"),
        "compact": (compact_dir / f"{output_base_name}_compact.md", "md"),
        "csv": (csv_dir / f"{output_base_name}_csv.csv", "csv"),
    }

    generated_files = {}

    for format_name, (output_path, _ext) in formats.items():
        print(f"Generating {format_name} format...")
        try:
            output = run_analyzer(sample_file, format_name)
            output_path.write_text(output, encoding="utf-8")
            generated_files[format_name] = output_path
            print(f"  ✓ Created: {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to generate {format_name}: {e}", file=sys.stderr)
            raise

    return generated_files


def verify_golden_masters(
    language: str, sample_file: str, output_base_name: str
) -> bool:
    """
    Verify that golden masters are consistent across multiple runs

    Args:
        language: Language name
        sample_file: Path to sample file
        output_base_name: Base name for output files

    Returns:
        True if all runs produce identical output
    """
    print("\nVerifying consistency (running 3 times)...")

    formats = ["full", "compact", "csv"]
    all_consistent = True

    for format_name in formats:
        outputs = []
        for i in range(3):
            try:
                output = run_analyzer(sample_file, format_name)
                outputs.append(output)
            except subprocess.CalledProcessError as e:
                print(f"  ✗ Run {i + 1} failed for {format_name}: {e}", file=sys.stderr)
                return False

        # Check if all outputs are identical
        if len(set(outputs)) == 1:
            print(f"  ✓ {format_name}: Consistent across all runs")
        else:
            print(f"  ✗ {format_name}: INCONSISTENT output detected!")
            all_consistent = False

            # Show differences
            for i in range(1, len(outputs)):
                if outputs[i] != outputs[0]:
                    print(f"    Difference between run 1 and run {i + 1}:")
                    lines1 = outputs[0].split("\n")
                    lines2 = outputs[i].split("\n")
                    for j, (line1, line2) in enumerate(
                        zip(lines1, lines2, strict=False)
                    ):
                        if line1 != line2:
                            print(f"      Line {j + 1}:")
                            print(f"        Run 1: {line1!r}")
                            print(f"        Run {i + 1}: {line2!r}")
                            break

    return all_consistent


def update_test_file(language: str, sample_file: str, output_base_name: str) -> None:
    """
    Print instructions for updating test_golden_master_regression.py

    Args:
        language: Language name
        sample_file: Path to sample file
        output_base_name: Base name for output files
    """
    print(f"\n{'=' * 60}")
    print("Next Steps:")
    print(f"{'=' * 60}")
    print("\n1. Add test cases to tests/test_golden_master_regression.py:")
    print(
        f"""
    # {language.capitalize()} tests
    ("{sample_file}", "{output_base_name}", "full"),
    ("{sample_file}", "{output_base_name}", "compact"),
    ("{sample_file}", "{output_base_name}", "csv"),
"""
    )
    print("\n2. Run the tests:")
    print(f'   uv run pytest tests/test_golden_master_regression.py -k "{language}" -v')
    print("\n3. If tests fail due to inconsistent output:")
    print("   - Fix the plugin to ensure deterministic output")
    print("   - Regenerate golden masters after fixing")
    print("   - Temporarily disable tests with TODO comment")
    print(f"\n{'=' * 60}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Generate golden master files for a new language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/generate_golden_masters.py csharp examples/Sample.cs
  python scripts/generate_golden_masters.py java examples/Sample.java --name java_bigservice
  python scripts/generate_golden_masters.py sql examples/sample_database.sql
        """,
    )

    parser.add_argument(
        "language",
        help="Language name (e.g., csharp, java, python)",
    )

    parser.add_argument(
        "sample_file",
        help="Path to sample file (e.g., examples/Sample.cs)",
    )

    parser.add_argument(
        "--name",
        help="Base name for output files (default: {language}_sample)",
        default=None,
    )

    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip consistency verification",
    )

    args = parser.parse_args()

    try:
        print(f"Generating golden masters for {args.language}...")
        print(f"Sample file: {args.sample_file}")
        print()

        output_base_name = args.name or f"{args.language}_sample"

        # Generate golden masters
        generated_files = generate_golden_master(
            args.language, args.sample_file, output_base_name
        )

        print(f"\n✓ Successfully generated {len(generated_files)} golden master files")

        # Verify consistency
        if not args.skip_verify:
            is_consistent = verify_golden_masters(
                args.language, args.sample_file, output_base_name
            )

            if is_consistent:
                print("\n✓ All outputs are consistent!")
            else:
                print("\n✗ WARNING: Inconsistent output detected!")
                print("   This may cause golden master tests to fail randomly.")
                print("   Consider fixing the plugin before adding tests.")
                sys.exit(1)

        # Print next steps
        update_test_file(args.language, args.sample_file, output_base_name)

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
