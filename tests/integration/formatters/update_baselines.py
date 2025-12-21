#!/usr/bin/env python3
"""Update format baselines.

This script updates the baseline files for format testing.
It aligns with tests/test_golden_master_regression.py expectations.
"""

import subprocess
import sys
from pathlib import Path

# Test cases configuration from tests/test_golden_master_regression.py
# Format: (input_file, golden_name, table_format)
TEST_CASES = [
    # YAML tests
    ("examples/sample_config.yaml", "yaml_sample_config", "full"),
    ("examples/sample_config.yaml", "yaml_sample_config", "compact"),
    ("examples/sample_config.yaml", "yaml_sample_config", "csv"),
    # HTML tests
    ("examples/comprehensive_sample.html", "html_comprehensive_sample", "full"),
    ("examples/comprehensive_sample.html", "html_comprehensive_sample", "compact"),
    ("examples/comprehensive_sample.html", "html_comprehensive_sample", "csv"),
    # CSS tests
    ("examples/comprehensive_sample.css", "css_comprehensive_sample", "full"),
    ("examples/comprehensive_sample.css", "css_comprehensive_sample", "compact"),
    ("examples/comprehensive_sample.css", "css_comprehensive_sample", "csv"),
    # Markdown tests
    ("examples/test_markdown.md", "markdown_test", "full"),
    ("examples/test_markdown.md", "markdown_test", "compact"),
    ("examples/test_markdown.md", "markdown_test", "csv"),
    # Java tests
    ("examples/Sample.java", "java_sample", "full"),
    ("examples/Sample.java", "java_sample", "compact"),
    ("examples/Sample.java", "java_sample", "csv"),
    ("examples/BigService.java", "java_bigservice", "full"),
    ("examples/BigService.java", "java_bigservice", "compact"),
    ("examples/BigService.java", "java_bigservice", "csv"),
    # Python tests
    ("examples/sample.py", "python_sample", "full"),
    ("examples/sample.py", "python_sample", "compact"),
    ("examples/sample.py", "python_sample", "csv"),
    # TypeScript tests
    ("tests/test_data/test_enum.ts", "typescript_enum", "full"),
    ("tests/test_data/test_enum.ts", "typescript_enum", "compact"),
    ("tests/test_data/test_enum.ts", "typescript_enum", "csv"),
    # JavaScript tests
    ("tests/test_data/test_class.js", "javascript_class", "full"),
    ("tests/test_data/test_class.js", "javascript_class", "compact"),
    ("tests/test_data/test_class.js", "javascript_class", "csv"),
    # SQL tests
    ("examples/sample_database.sql", "sql_sample_database", "full"),
    ("examples/sample_database.sql", "sql_sample_database", "compact"),
    ("examples/sample_database.sql", "sql_sample_database", "csv"),
    # C# tests
    ("examples/Sample.cs", "csharp_sample", "full"),
    ("examples/Sample.cs", "csharp_sample", "compact"),
    ("examples/Sample.cs", "csharp_sample", "csv"),
    # PHP tests
    ("examples/Sample.php", "php_sample", "full"),
    ("examples/Sample.php", "php_sample", "compact"),
    ("examples/Sample.php", "php_sample", "csv"),
    # Ruby tests
    ("examples/Sample.rb", "ruby_sample", "full"),
    ("examples/Sample.rb", "ruby_sample", "compact"),
    ("examples/Sample.rb", "ruby_sample", "csv"),
    # Rust tests
    ("examples/sample.rs", "rust_sample", "full"),
    ("examples/sample.rs", "rust_sample", "compact"),
    ("examples/sample.rs", "rust_sample", "csv"),
    # Kotlin tests
    ("examples/Sample.kt", "kotlin_sample", "full"),
    ("examples/Sample.kt", "kotlin_sample", "compact"),
    ("examples/Sample.kt", "kotlin_sample", "csv"),
    # Go tests
    ("examples/sample.go", "go_sample", "full"),
    ("examples/sample.go", "go_sample", "compact"),
    ("examples/sample.go", "go_sample", "csv"),
    # C tests
    ("examples/sample.c", "c_sample", "full"),
    ("examples/sample.c", "c_sample", "compact"),
    ("examples/sample.c", "c_sample", "csv"),
    # C++ tests
    ("examples/sample.cpp", "cpp_sample", "full"),
    ("examples/sample.cpp", "cpp_sample", "compact"),
    ("examples/sample.cpp", "cpp_sample", "csv"),
]


def run_analyzer(input_file: str, table_format: str = "full") -> str:
    """Run analyzer and get output"""
    python_exe = sys.executable
    cmd = [
        python_exe,
        "-m",
        "tree_sitter_analyzer",
        input_file,
        "--table",
        table_format,
    ]
    # Run from project root (3 levels up from this script)
    project_root = Path(__file__).parent.parent.parent.parent
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        cwd=project_root,
    )
    return result.stdout


def main() -> int:
    """Update format baselines."""
    print("Updating Format Baselines")
    print("=" * 60)

    project_root = Path(__file__).parent.parent.parent.parent
    golden_masters_dir = project_root / "tests/golden_masters"

    if not golden_masters_dir.exists():
        print("Creating golden masters directory...")
        golden_masters_dir.mkdir(parents=True, exist_ok=True)

    updated_count = 0
    error_count = 0

    for input_file, golden_name, table_format in TEST_CASES:
        ext = "csv" if table_format == "csv" else "md"
        print(f"Updating {golden_name} ({table_format})...", end=" ", flush=True)

        try:
            output = run_analyzer(input_file, table_format)

            output_dir = golden_masters_dir / table_format
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f"{golden_name}_{table_format}.{ext}"
            with output_file.open("w", encoding="utf-8", newline="\n") as f:
                f.write(output)
            print("✓ Done")
            updated_count += 1

        except subprocess.CalledProcessError as e:
            print("✗ Failed")
            print(f"  Error: {e}")
            print(f"  Stderr: {e.stderr}")
            error_count += 1
        except Exception as e:
            print("✗ Failed")
            print(f"  Error: {e}")
            error_count += 1

    print("=" * 60)
    print(f"Update complete. Updated: {updated_count}, Failed: {error_count}")
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
