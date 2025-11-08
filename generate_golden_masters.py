"""
Generate Golden Master Reference Files

This script generates golden master reference files for format regression testing.
It analyzes sample files and creates reference outputs for each format type.
"""

import subprocess  # nosec B404
from pathlib import Path


def run_analyzer(input_file: str, table_format: str = "full") -> str:
    """アナライザーを実行して出力を取得"""
    cmd = ["uv", "run", "tree-sitter-analyzer", input_file, "--table", table_format]

    result = subprocess.run(  # nosec B603
        cmd, capture_output=True, text=True, encoding="utf-8", check=True
    )

    return result.stdout


def generate_golden_master(file_path: str, format_type: str, output_name: str) -> None:
    """Generate golden master for a specific format"""
    print(f"Generating golden master: {output_name} ({format_type} format)")

    try:
        # Run the actual CLI tool to get the output
        output = run_analyzer(file_path, format_type)

        # Determine output directory and extension
        output_dir = Path("tests/golden_masters") / format_type
        output_dir.mkdir(parents=True, exist_ok=True)

        extension = "csv" if format_type == "csv" else "md"
        output_file = output_dir / f"{output_name}.{extension}"

        # Save the output
        output_file.write_text(output, encoding="utf-8")
        print(f"  [OK] Created: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Failed to analyze: {file_path}")
        print(f"    Error: {e}")
    except Exception as e:
        print(f"  [ERROR] Unexpected error: {e}")


def main():
    """Generate all golden master files"""
    print("=" * 60)
    print("Golden Master Generation")
    print("=" * 60)

    # Sample.java - Multiple classes test case
    sample_java = "examples/Sample.java"

    # Generate golden masters for Sample.java
    generate_golden_master(sample_java, "full", "java_sample_full")
    generate_golden_master(sample_java, "compact", "java_sample_compact")
    generate_golden_master(sample_java, "csv", "java_sample_csv")

    # BigService.java - Large class test case
    big_service_java = "examples/BigService.java"
    if Path(big_service_java).exists():
        generate_golden_master(big_service_java, "full", "java_bigservice_full")
        generate_golden_master(big_service_java, "compact", "java_bigservice_compact")
        generate_golden_master(big_service_java, "csv", "java_bigservice_csv")
    else:
        print("  ⚠ BigService.java not found - skipping")

    # sample.py - Python sample
    sample_py = "examples/sample.py"
    if Path(sample_py).exists():
        generate_golden_master(sample_py, "full", "python_sample_full")
        generate_golden_master(sample_py, "compact", "python_sample_compact")
    else:
        print("  ⚠ sample.py not found - skipping")

    # test_enum.ts - TypeScript enum test
    test_enum_ts = "tests/test_data/test_enum.ts"
    if Path(test_enum_ts).exists():
        generate_golden_master(test_enum_ts, "full", "typescript_enum_full")
    else:
        print("  ⚠ test_enum.ts not found - skipping")

    # test_class.js - JavaScript class test
    test_class_js = "tests/test_data/test_class.js"
    if Path(test_class_js).exists():
        generate_golden_master(test_class_js, "full", "javascript_class_full")
    else:
        print("  ⚠ test_class.js not found - skipping")

    # sample_database.sql - SQL database schema test
    sample_sql = "examples/sample_database.sql"
    if Path(sample_sql).exists():
        generate_golden_master(sample_sql, "full", "sql_sample_database_full")
        generate_golden_master(sample_sql, "compact", "sql_sample_database_compact")
        generate_golden_master(sample_sql, "csv", "sql_sample_database_csv")
    else:
        print("  ⚠ sample_database.sql not found - skipping")

    print()
    print("=" * 60)
    print("Golden Master Generation Complete")
    print("=" * 60)
    print()
    print("Generated files are in: tests/golden_masters/")
    print()
    print("Next steps:")
    print("1. Review generated files to ensure they are correct")
    print("2. Run tests to validate: pytest tests/format_testing/")
    print("3. Commit golden master files to repository")


if __name__ == "__main__":
    main()
