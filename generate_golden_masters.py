"""
Generate Golden Master Reference Files

This script generates golden master reference files for format regression testing.
It analyzes sample files and creates reference outputs for each format type.

Supported formats:
- full: Full table format (Markdown)
- compact: Compact table format (Markdown)
- csv: CSV table format
- toon: TOON format (Token-Oriented Object Notation)
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
        # All formats now use --table command (including toon)
        output = run_analyzer(file_path, format_type)

        # Determine output directory and extension
        output_dir = Path("tests/golden_masters") / format_type
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine file extension
        if format_type == "csv":
            extension = "csv"
        elif format_type == "toon":
            extension = "toon"
        else:
            extension = "md"

        output_file = output_dir / f"{output_name}.{extension}"

        # Save the output
        output_file.write_text(output, encoding="utf-8")
        print(f"  [OK] Created: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Failed to analyze: {file_path}")
        print(f"    Error: {e}")
    except Exception as e:
        print(f"  [ERROR] Unexpected error: {e}")


def generate_all_formats(
    file_path: str, base_name: str, formats: list[str] | None = None
) -> None:
    """Generate golden masters for all specified formats"""
    if formats is None:
        formats = ["full", "compact", "csv", "toon"]

    for fmt in formats:
        output_name = f"{base_name}_{fmt}"
        generate_golden_master(file_path, fmt, output_name)


def main():
    """Generate all golden master files"""
    print("=" * 60)
    print("Golden Master Generation")
    print("=" * 60)

    # Define all test files with their base names
    test_files = [
        # Java
        ("examples/Sample.java", "java_sample"),
        ("examples/BigService.java", "java_bigservice"),
        # Python
        ("examples/sample.py", "python_sample"),
        # TypeScript/JavaScript
        ("tests/test_data/test_enum.ts", "typescript_enum"),
        ("tests/test_data/test_class.js", "javascript_class"),
        # Go
        ("examples/sample.go", "go_sample"),
        # Rust
        ("examples/sample.rs", "rust_sample"),
        # Kotlin
        ("examples/Sample.kt", "kotlin_sample"),
        # C#
        ("examples/Sample.cs", "csharp_sample"),
        # PHP
        ("examples/Sample.php", "php_sample"),
        # Ruby
        ("examples/Sample.rb", "ruby_sample"),
        # C/C++
        ("examples/sample.c", "c_sample"),
        ("examples/sample.cpp", "cpp_sample"),
        # YAML
        ("examples/sample_config.yaml", "yaml_sample_config"),
        # HTML/CSS
        ("examples/comprehensive_sample.html", "html_comprehensive_sample"),
        ("examples/comprehensive_sample.css", "css_comprehensive_sample"),
        # Markdown
        ("examples/test_markdown.md", "markdown_test"),
        # SQL
        ("examples/sample_database.sql", "sql_sample_database"),
    ]

    # Generate golden masters for all files
    for file_path, base_name in test_files:
        if Path(file_path).exists():
            print(f"\n--- {file_path} ---")
            generate_all_formats(file_path, base_name)
        else:
            print(f"  ⚠ {file_path} not found - skipping")

    print()
    print("=" * 60)
    print("Golden Master Generation Complete")
    print("=" * 60)
    print()
    print("Generated files are in: tests/golden_masters/")
    print("  - full/     : Full table format (Markdown)")
    print("  - compact/  : Compact table format (Markdown)")
    print("  - csv/      : CSV table format")
    print("  - toon/     : TOON format (Token-Oriented)")
    print()
    print("Next steps:")
    print("1. Review generated files to ensure they are correct")
    print("2. Run tests to validate: pytest tests/test_golden_master_regression.py")
    print("3. Commit golden master files to repository")


if __name__ == "__main__":
    main()
